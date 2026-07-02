# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
AI Workload — setup and runtime for a single DUT target.

:class:`AIWorkload` is the self-contained library entry point for AI workload
operations on one target.  It covers two distinct phases:

Setup phase (async)
-------------------
- :meth:`AIWorkload.install` — spawns a worker thread that runs all setup
  steps (venv, pip install, model export, quantization).  Returns immediately.
- :meth:`AIWorkload.get_install_progress` — step-level progress snapshot;
  safe to poll from any thread at any time.
- :meth:`AIWorkload.cancel_install` — signal the install thread to stop.

Runtime phase (async benchmark, sync log collection)
-----------------------------------------------------
- :meth:`AIWorkload.start` — verifies the installed environment, then starts
  the benchmark asynchronously via :class:`~.runner.AIWorkloadRunner`.
- :meth:`AIWorkload.get_run_progress` — live benchmark metrics snapshot.
- :meth:`AIWorkload.stop` — stop the running benchmark.
- :meth:`AIWorkload.collect_logs` — retrieve the benchmark report JSON.

The orchestrator creates one :class:`AIWorkload` instance per DUT target and
manages the collection externally.  This class has no knowledge of other
targets or concurrent installations.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from time_config_hub.infra.execution_transport import ExecutionTransport

from .config import AIWorkloadConfig
from .helper import _run_cmds
from .runner import AIWorkloadRunner
from .setup import SETUP_STEPS, VERIFY_STEPS
from .state import (
    BenchmarkProgress,
    InstallProgress,
    StepProgress,
    StepStatus,
    WorkloadState,
    _InstallState,
)

logger = logging.getLogger(__name__)

_COMPONENT = "ai_workload"
_DEFAULT_LOG_LOCAL_DIR = "results/"


class AIWorkload:
    """AI workload setup and runtime for a single DUT target.

    Bind one instance to one transport at construction time.  The orchestrator
    creates one :class:`AIWorkload` per DUT and calls the setup and runtime
    methods as needed.

    Thread safety
    -------------
    All public methods are safe to call from any thread concurrently.

    :param ExecutionTransport transport: Execution transport for the target.
    :param AIWorkloadConfig config: Configuration; uses defaults if omitted.
    :param str log_local_dir: Local directory for collected benchmark reports.
    """

    def __init__(
        self,
        transport: ExecutionTransport,
        config: AIWorkloadConfig | None = None,
        log_local_dir: str = _DEFAULT_LOG_LOCAL_DIR,
    ) -> None:
        self._transport = transport
        self._config = config or AIWorkloadConfig()
        self._log_local_dir = log_local_dir
        self._install_lock = threading.Lock()
        self._install_state = _InstallState(
            target_label=transport.target_label,
            component=_COMPONENT,
        )
        self._runner = AIWorkloadRunner(transport, config=self._config)

    # ------------------------------------------------------------------
    # Setup phase
    # ------------------------------------------------------------------

    def install(self) -> None:
        """Spawn the installation worker thread and return immediately.

        Runs all ``SETUP_STEPS`` sequentially in a daemon thread (venv
        creation, pip install, model export, quantization, etc.).

        :raises RuntimeError: If ``install()`` has already been called on
            this instance.  Create a new :class:`AIWorkload` to retry.
        """
        with self._install_lock:
            if self._install_state.started:
                raise RuntimeError(
                    f"install() already called for '{self._transport.target_label}'. "
                    "Create a new AIWorkload instance to retry."
                )
            self._install_state.started = True
            self._install_state.state = WorkloadState.RUNNING
            self._install_state.overall_percent = 0
            self._install_state.start_time = time.monotonic()
            self._install_state.stop_event.clear()
            self._install_state.steps = [
                {"label": step["name"], "status": StepStatus.PENDING, "detail": ""}
                for step in SETUP_STEPS
            ]

        try:
            t = threading.Thread(
                target=self._install_worker,
                daemon=True,
                name=f"ai_install_{self._transport.target_label}",
            )
            t.start()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to start install thread for '{self._transport.target_label}': {exc}"
            ) from exc

        with self._install_lock:
            self._install_state.thread = t

        logger.info("[ai_workload] install started for '%s'", self._transport.target_label)

    def get_install_progress(self) -> InstallProgress:
        """Return the current installation progress snapshot.

        Safe to call before :meth:`install` is called (returns safe defaults),
        during installation, and after completion.

        :return: Step-level progress snapshot.
        :rtype: InstallProgress
        """
        return self._build_install_progress()

    def cancel_install(self) -> None:
        """Signal the installation worker to stop before the next step.

        Returns immediately; the worker thread checks the signal between steps
        and terminates cleanly.  Has no effect if no installation is running.
        """
        with self._install_lock:
            if self._install_state.state == WorkloadState.RUNNING:
                self._install_state.stop_event.set()
        logger.info(
            "[ai_workload] install cancel requested for '%s'",
            self._transport.target_label,
        )

    # ------------------------------------------------------------------
    # Runtime phase
    # ------------------------------------------------------------------

    def start(
        self,
        duration_s: int | None = None,
        dry_run: bool = False,
    ) -> None:
        """Verify the AI environment, then start the benchmark asynchronously.

        Environment verification (``VERIFY_STEPS``) runs synchronously before
        spawning the benchmark thread; the method returns once the thread is
        started.

        :param int duration_s: Benchmark duration in seconds.
        :param bool dry_run: If True, log intent without executing.
        :raises RuntimeError: If environment verification fails or the benchmark
            is already running on this instance.
        """
        if duration_s is None:
            duration_s = self._config.bench_duration_s
        if dry_run:
            logger.info(
                "[ai_workload][DRY RUN] Would start benchmark on '%s' (duration=%ds)",
                self._transport.target_label,
                duration_s,
            )
            return

        for step in VERIFY_STEPS:
            success, detail = _run_cmds(step["cmds"], transport=self._transport)
            if not success:
                raise RuntimeError(
                    f"AI environment check failed on '{self._transport.target_label}' "
                    f"at step '{step['name']}': {detail}"
                )

        result = self._runner.start(duration_s=duration_s)
        if not result.success:
            raise RuntimeError(
                f"Failed to start AI benchmark on '{self._transport.target_label}': "
                f"{result.error}"
            )
        logger.info(
            "[ai_workload] benchmark started for '%s'", self._transport.target_label
        )

    def get_run_progress(self) -> BenchmarkProgress:
        """Return the current benchmark progress snapshot.

        Safe to call before :meth:`start`, during a run, and after stopping.

        :return: Live benchmark metrics snapshot.
        :rtype: BenchmarkProgress
        """
        return self._runner.get_progress().data

    def stop(self, dry_run: bool = False) -> None:
        """Stop the running benchmark.

        Sends a stop signal and a ``pkill`` to ``benchmark_app``.  Returns
        immediately without waiting for the worker thread to finish.

        :param bool dry_run: If True, log intent without executing.
        """
        if dry_run:
            logger.info(
                "[ai_workload][DRY RUN] Would stop benchmark on '%s'",
                self._transport.target_label,
            )
            return
        self._runner.stop()
        logger.info(
            "[ai_workload] benchmark stopped for '%s'", self._transport.target_label
        )

    def collect_logs(self, dry_run: bool = False) -> list[str]:
        """Retrieve the benchmark report JSON from the target.

        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[ai_workload] collect_logs from '{self._transport.target_label}'"]
        local_name = (
            self._transport.target_label.replace("@", "_") + "_ai_benchmark.json"
        )
        local_path = os.path.join(self._log_local_dir, local_name)

        if dry_run:
            output.append(
                f"[DRY RUN] Would retrieve '{self._config.report_json}' "
                f"from '{self._transport.target_label}' \u2192 '{local_path}'"
            )
            return output

        Path(self._log_local_dir).mkdir(parents=True, exist_ok=True)
        self._transport.get_file(str(self._config.report_json), local_path)

        logger.info(
            "[ai_workload] logs collected from '%s'", self._transport.target_label
        )
        output.append(f"[ai_workload] report saved to '{local_path}'")
        return output

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_install_progress(self) -> InstallProgress:
        with self._install_lock:
            elapsed = (
                max(
                    0.0,
                    (self._install_state.end_time or time.monotonic())
                    - self._install_state.start_time,
                )
                if self._install_state.start_time > 0
                else 0.0
            )
            return InstallProgress(
                node_id=self._transport.target_label,
                component=_COMPONENT,
                state=self._install_state.state,
                overall_percent=self._install_state.overall_percent,
                steps=[StepProgress(**s) for s in self._install_state.steps],
                elapsed_s=elapsed,
            )

    def _install_worker(self) -> None:
        """Worker thread: run SETUP_STEPS sequentially, update progress in-memory.

        On user cancellation the state is set to ``"cancelled"`` and all remaining
        steps (from the cancellation point onward) are marked
        :attr:`~.state.StepStatus.CANCELLED`.  On step failure the state is set to
        ``"error"``.  On success the state is set to ``"done"``.
        """
        total = len(SETUP_STEPS)
        try:
            for idx, step in enumerate(SETUP_STEPS):
                if self._install_state.stop_event.is_set():
                    with self._install_lock:
                        self._install_state.end_time = time.monotonic()
                        self._install_state.state = WorkloadState.CANCELLED
                        for cancel_idx in range(idx, len(self._install_state.steps)):
                            self._install_state.steps[cancel_idx][
                                "status"
                            ] = StepStatus.CANCELLED
                            self._install_state.steps[cancel_idx][
                                "detail"
                            ] = "Cancelled by user"
                    logger.info(
                        "[ai_workload] install cancelled at step %d for '%s'",
                        idx,
                        self._transport.target_label,
                    )
                    return

                step_name = step["name"]
                logger.info(
                    "[ai_workload] install step %d/%d START: %s",
                    idx + 1,
                    total,
                    step_name,
                )

                with self._install_lock:
                    if idx < len(self._install_state.steps):
                        self._install_state.steps[idx]["status"] = StepStatus.RUNNING

                success, detail = _run_cmds(step["cmds"], transport=self._transport)

                with self._install_lock:
                    if idx < len(self._install_state.steps):
                        self._install_state.steps[idx]["status"] = (
                            StepStatus.DONE if success else StepStatus.FAILED
                        )
                        self._install_state.steps[idx]["detail"] = detail
                    self._install_state.overall_percent = int((idx + 1) / total * 100)
                    if not success:
                        self._install_state.state = WorkloadState.ERROR
                        self._install_state.end_time = time.monotonic()

                if not success:
                    logger.error(
                        "[ai_workload] install step FAILED: %s \u2014 %s",
                        step_name,
                        detail[:120],
                    )
                    return

                logger.info(
                    "[ai_workload] install step %d/%d OK: %s", idx + 1, total, step_name
                )

            with self._install_lock:
                self._install_state.end_time = time.monotonic()
                self._install_state.state = WorkloadState.DONE
                self._install_state.overall_percent = 100

            logger.info(
                "[ai_workload] install complete for '%s'", self._transport.target_label
            )

        except Exception:
            logger.exception(
                "[ai_workload] unexpected install error for '%s'",
                self._transport.target_label,
            )
            with self._install_lock:
                self._install_state.end_time = time.monotonic()
                self._install_state.state = WorkloadState.ERROR
