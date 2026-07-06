# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
time_config_hub.services.ai_workload.installer — setup phase, single-use installer.

Handles the **setup phase**: prepares the Python virtual environment, installs
dependencies, exports the AI model, and runs quantization.  This is a one-time
operation per target; the runtime phase (:class:`~.service.AIWorkloadService`)
assumes it has already completed successfully.

One :class:`AIWorkloadInstaller` instance handles one installation attempt.
The setup steps are built once at construction from the supplied
:class:`~.config.AIWorkloadConfig`, so a custom config drives the commands run
on the target.  Progress is persisted to
``~/.tch/installation_progress_ai_workload__<label>.json`` after each step so
the caller can poll it independently of instance lifetime.  The per-target
registry (at-most-one-active rule) is owned by the caller.

Public API
----------
AIWorkloadInstaller : Single-use installer class.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from time_config_hub.infra.execution_transport import ExecutionTransport
from time_config_hub.services.common.result import ServiceResult
from time_config_hub.utils.common.status_codes import TchStatusCode

from .config import AIWorkloadConfig
from .helper import _run_cmds
from .setup import build_setup_steps
from .state import (
    InstallProgress,
    StepProgress,
    StepStatus,
    WorkloadState,
    _InstallState,
)

_log = logging.getLogger("ai_workload.installer")

_STATE_DIR = Path.home() / ".tch"
_COMPONENT = "ai_workload"


class AIWorkloadInstaller:
    """Single-use AI workload installer for one transport target.

    Internal collaborator of :class:`~.service.AIWorkload` — not intended for
    direct use.  :class:`~.service.AIWorkload` creates one instance per DUT in
    its constructor and passes its bound :class:`~.config.AIWorkloadConfig`.

    Handles a single installation attempt: manages the worker thread, tracks
    per-step progress, and persists state to disk.  It has no knowledge of
    other installers or concurrent targets.

    To retry after completion or cancellation, the owning
    :class:`~.service.AIWorkload` must be replaced with a new instance —
    the same installer cannot be restarted.

    Thread safety
    -------------
    All public methods are safe to call from any thread concurrently.

    :param ExecutionTransport transport: Execution transport for the target.
    :param AIWorkloadConfig config: Configuration used to build the setup
        steps; always supplied by :class:`~.service.AIWorkload` from its bound
        config.
    :param _on_finish: Optional zero-argument callback invoked exactly once
        when the installation finishes (success, failure, or cancellation).
        Called from the worker thread's ``finally`` block, or from
        :meth:`start` if thread spawning fails.
    """

    def __init__(
        self,
        transport: ExecutionTransport,
        config: AIWorkloadConfig,
        _on_finish: Optional[Callable[[], None]] = None,
    ) -> None:
        self._transport = transport
        self._config = config
        self._setup_steps = build_setup_steps(self._config)
        self._on_finish = _on_finish
        self._state = _InstallState(
            target_label=transport.target_label,
            component=_COMPONENT,
        )
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> ServiceResult:
        """Spawn the installation worker thread and return immediately.

        :return: :class:`~.state.ServiceResult` with:

            * :attr:`~time_config_hub.utils.common.status_codes.TchStatusCode.SUCCESS`
              — installation thread started; ``data`` is the initial
              :class:`~.state.InstallProgress`.
            * :attr:`~time_config_hub.utils.common.status_codes.TchStatusCode.ALREADY_RUNNING`
              — another installation for this target is already active.
            * :attr:`~time_config_hub.utils.common.status_codes.TchStatusCode.ERROR`
              — this instance has already been used (single-use enforcement).
        :rtype: ServiceResult
        """
        # Single-use check
        with self._lock:
            if self._state.started:
                return ServiceResult(
                    status_code=TchStatusCode.ERROR,
                    error=(
                        "This AIWorkloadInstaller instance has already been used. "
                        "Create a new instance to retry."
                    ),
                )
            self._state.started = True
            self._state.state = WorkloadState.RUNNING
            self._state.overall_percent = 0
            self._state.start_time = time.monotonic()
            self._state.stop_event.clear()
            self._state.steps = [
                {"label": step["name"], "status": StepStatus.PENDING, "detail": ""}
                for step in self._setup_steps
            ]

        # Spawn worker — notify manager on any failure to start
        try:
            t = threading.Thread(
                target=self._install_worker,
                daemon=True,
                name=f"ai_installer_{self._transport.target_label}",
            )
            t.start()
        except Exception as exc:  # noqa: BLE001
            if self._on_finish:
                self._on_finish()
            return ServiceResult(
                status_code=TchStatusCode.ERROR,
                error=f"Failed to start installation thread: {exc}",
            )

        with self._lock:
            self._state.thread = t

        _log.info(
            "[installer] started installation for %s", self._transport.target_label
        )
        return ServiceResult(
            status_code=TchStatusCode.SUCCESS,
            output=f"Installation started for {self._transport.target_label}",
            data=self._build_progress(),
        )

    def cancel(self) -> ServiceResult:
        """Request cancellation of a running installation.

        Sets the internal stop event; the worker thread checks it between steps
        and terminates cleanly on the next check.  Returns immediately without
        waiting for the thread to finish.

        :return: :class:`~.state.ServiceResult` with:

            * :attr:`~time_config_hub.utils.common.status_codes.TchStatusCode.SUCCESS`
              — cancellation signal sent; ``data`` is the current
              :class:`~.state.InstallProgress`.
            * :attr:`~time_config_hub.utils.common.status_codes.TchStatusCode.NOT_RUNNING`
              — no installation was running.
        :rtype: ServiceResult
        """
        with self._lock:
            if self._state.state != WorkloadState.RUNNING:
                return ServiceResult(
                    status_code=TchStatusCode.NOT_RUNNING,
                    error="No installation is currently running.",
                    data=self._build_progress(),
                )
            self._state.stop_event.set()

        _log.info("[installer] cancel requested for %s", self._transport.target_label)
        return ServiceResult(
            status_code=TchStatusCode.SUCCESS,
            output=f"Cancellation requested for {self._transport.target_label}",
            data=self._build_progress(),
        )

    def get_progress(self) -> ServiceResult:
        """Return the current installation progress without blocking.

        Safe to call from any thread at any time, including before :meth:`start`
        is called (returns safe defaults in that case).

        :return: :class:`~.state.ServiceResult` with
            :attr:`~time_config_hub.utils.common.status_codes.TchStatusCode.SUCCESS`
            and ``data`` set to the current :class:`~.state.InstallProgress`.
        :rtype: ServiceResult
        """
        return ServiceResult(
            status_code=TchStatusCode.SUCCESS,
            data=self._build_progress(),
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_progress(self) -> InstallProgress:
        """Build a :class:`~.state.InstallProgress` snapshot from the current state.

        Acquires ``_lock`` internally; must **not** be called while the lock is
        already held by the calling thread.

        :return: Current progress snapshot.
        :rtype: InstallProgress
        """
        with self._lock:
            elapsed = (
                max(
                    0.0,
                    (self._state.end_time or time.monotonic()) - self._state.start_time,
                )
                if self._state.start_time > 0
                else 0.0
            )
            return InstallProgress(
                node_id=self._transport.target_label,
                component=_COMPONENT,
                state=self._state.state,
                overall_percent=self._state.overall_percent,
                steps=[StepProgress(**s) for s in self._state.steps],
                elapsed_s=elapsed,
            )

    def _snapshot_under_lock(self) -> dict:
        """Read state fields into a plain dict for persistence.

        **Must be called while** ``_lock`` **is held.**

        :return: Serialisable state dict.
        :rtype: dict
        """
        elapsed = (
            max(
                0.0,
                (self._state.end_time or time.monotonic()) - self._state.start_time,
            )
            if self._state.start_time > 0
            else 0.0
        )
        return {
            "node_id": self._transport.target_label,
            "component": _COMPONENT,
            "state": self._state.state,
            "overall_percent": self._state.overall_percent,
            "steps": [dict(s) for s in self._state.steps],
            "elapsed_s": elapsed,
            "start_time": self._state.start_time,
        }

    def _write_state(self, data: dict) -> None:
        """Atomically write *data* to the progress JSON file.

        Called **without** holding ``_lock`` to avoid blocking on I/O while the
        lock is held.

        :param dict data: Serialisable state dict produced by
            :meth:`_snapshot_under_lock`.
        """
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        key = f"{_COMPONENT}__{self._transport.target_label}"
        path = _STATE_DIR / f"installation_progress_{key}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)

    # ── Worker thread ─────────────────────────────────────────────────────────

    def _install_worker(self) -> None:
        """Worker thread target: iterate the configured setup steps and persist progress after each.

        Checks the stop event before every step.  On user cancellation the state
        is set to ``"cancelled"`` and all remaining steps (from the cancellation
        point onward) are marked :attr:`~.state.StepStatus.CANCELLED`.  On step
        failure the state is set to ``"error"``.  On success the state is set to
        ``"done"`` with ``overall_percent = 100``.

        The target label is removed from :attr:`_active_targets` in a ``finally``
        block regardless of outcome.
        """
        total = len(self._setup_steps)
        try:
            for idx, step in enumerate(self._setup_steps):
                # Cancellation check — happens before each step
                if self._state.stop_event.is_set():
                    with self._lock:
                        self._state.end_time = time.monotonic()
                        self._state.state = WorkloadState.CANCELLED
                        # Mark all remaining steps as cancelled
                        for cancel_idx in range(idx, len(self._state.steps)):
                            self._state.steps[cancel_idx][
                                "status"
                            ] = StepStatus.CANCELLED
                            self._state.steps[cancel_idx][
                                "detail"
                            ] = "Cancelled by stop signal"
                        snapshot = self._snapshot_under_lock()
                    self._write_state(snapshot)
                    _log.info(
                        "[installer] installation cancelled at step %d for %s",
                        idx,
                        self._transport.target_label,
                    )
                    return

                step_name = step["name"]
                _log.info("[installer] step %d/%d START: %s", idx + 1, total, step_name)

                # Mark step as running
                with self._lock:
                    if idx < len(self._state.steps):
                        self._state.steps[idx]["status"] = StepStatus.RUNNING
                    snapshot = self._snapshot_under_lock()
                self._write_state(snapshot)

                success, detail = _run_cmds(step["cmds"], transport=self._transport)

                # Record step result
                with self._lock:
                    if idx < len(self._state.steps):
                        self._state.steps[idx]["status"] = (
                            StepStatus.DONE if success else StepStatus.FAILED
                        )
                        self._state.steps[idx]["detail"] = detail
                    self._state.overall_percent = int((idx + 1) / total * 100)
                    if not success:
                        self._state.state = WorkloadState.ERROR
                    snapshot = self._snapshot_under_lock()
                self._write_state(snapshot)

                if not success:
                    _log.error(
                        "[installer] step FAILED: %s \u2014 %s",
                        step_name,
                        detail[:120],
                    )
                    return

                _log.info("[installer] step %d/%d OK: %s", idx + 1, total, step_name)

            # All steps completed successfully
            with self._lock:
                self._state.end_time = time.monotonic()
                self._state.state = WorkloadState.DONE
                self._state.overall_percent = 100
                snapshot = self._snapshot_under_lock()
            self._write_state(snapshot)
            _log.info(
                "[installer] installation complete for %s",
                self._transport.target_label,
            )

        except Exception:  # noqa: BLE001
            _log.exception(
                "[installer] unexpected error for %s", self._transport.target_label
            )
            with self._lock:
                self._state.end_time = time.monotonic()
                self._state.state = WorkloadState.ERROR
                snapshot = self._snapshot_under_lock()
            self._write_state(snapshot)

        finally:
            if self._on_finish:
                self._on_finish()


def _read_persisted_progress(target_label: str) -> Optional[InstallProgress]:
    """Read the last persisted progress for *target_label* from disk.

    Useful for consumers that outlive the :class:`AIWorkloadInstaller` instance
    (e.g. after a process restart).  Returns ``None`` if no file exists or the
    file is malformed.

    :param str target_label: Target label string (``transport.target_label``).
    :return: Last persisted :class:`~.state.InstallProgress`, or ``None``.
    :rtype: Optional[InstallProgress]
    """
    key = f"{_COMPONENT}__{target_label}"
    path = _STATE_DIR / f"installation_progress_{key}.json"
    try:
        data = json.loads(path.read_text())
        data["steps"] = [StepProgress(**s) for s in data.get("steps", [])]
        data["state"] = WorkloadState(data["state"])
        # Drop keys not accepted by InstallProgress (e.g. start_time written
        # by _snapshot_under_lock for internal bookkeeping only).
        valid_fields = {f.name for f in dataclasses.fields(InstallProgress)}
        return InstallProgress(**{k: v for k, v in data.items() if k in valid_fields})
    except Exception:  # noqa: BLE001
        return None
