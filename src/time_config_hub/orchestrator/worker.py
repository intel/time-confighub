# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Target Worker

Runs the orchestration stage pipeline for a single target on a dedicated
thread.  Each worker executes the requested stages sequentially, collects
per-stage :class:`~.models.StageResult` objects, and exposes read-only
``logs`` and ``errors`` properties for consumption by the orchestrator
after ``join()``.

The utility functions :func:`_now_ms` and :func:`_timestamp` are defined
here and imported by ``orchestrator.py`` for consistent timestamping.
"""

import logging
import threading
import time
from datetime import datetime, timezone

from .models import (
    StageContext,
    StageResult,
    Target,
)
from .single_target import get_steps as get_single_target_steps
from .service_factory import ServiceFactory

__all__ = ["TargetWorker", "now_ms", "timestamp", "set_role_log_context"]

logger = logging.getLogger("orchestrator.worker")


# ======================================================================
# Role-aware logging — thread-local context + filter
# ======================================================================
#
# Problem: in multi-DUT runs, talker and listener threads emit log records
# concurrently.  Service-layer loggers (time_config_hub.services.*) have no
# knowledge of topology, so their records carry no role or target context.
#
# Solution: a single _RoleFilter is installed on both orchestrator and
# time_config_hub logger namespaces at module import time.  Each worker /
# step thread calls set_role_log_context(target) at its entry point, which
# stores a role prefix in threading.local().  The filter prepends that
# prefix to every log record emitted on that thread, regardless of which
# logger or service file produced it.
#
# Example output:
#   [talker/dut-1] STAGE START  start_ptp[dut-1/talker]
#   [listener/dut-2] STAGE START  start_ptp[dut-2/listener]
#   [listener/dut-2] [ptp] ptp4l slave started on 'dut-2'
#   [talker/dut-1] [ptp] ptp4l GM started on 'dut-1'
#   [listener/dut-2] STAGE DONE   start_ptp[dut-2/listener]  elapsed=0.501s
#   [talker/dut-1] STAGE DONE   start_ptp[dut-1/talker]  elapsed=0.612s

_role_ctx: threading.local = threading.local()


class _RoleFilter(logging.Filter):
    """Prepend the thread-local role prefix to every log record on this thread.

    Prepending directly to ``record.msg`` (the format string) works correctly
    with %-style format args: ``record.msg = "[role/id] " + record.msg`` still
    formats with the original ``record.args`` on the handler side.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        prefix = getattr(_role_ctx, "prefix", "")
        if prefix:
            record.msg = f"{prefix} {record.msg}"
        return True


def set_role_log_context(target: Target) -> None:
    """Set the thread-local role prefix for the calling thread.

    Must be called at the entry point of every worker thread and step
    thread before any logging is performed.  Subsequent log records
    emitted on the same thread will be prefixed with ``[role/target_id]``.

    :param target: The DUT target assigned to this thread.
    """
    role = target.role or "local"
    _role_ctx.prefix = f"[{role}/{target.id}]"


def _install_role_filter() -> None:
    """Install the role filter on orchestrator and service loggers (idempotent)."""
    _f = _RoleFilter()
    for name in ("orchestrator", "time_config_hub"):
        lg = logging.getLogger(name)
        # Guard against duplicate installation if module is re-imported
        if not any(isinstance(f, _RoleFilter) for f in lg.filters):
            lg.addFilter(_f)


_install_role_filter()


def now_ms() -> int:
    return int(time.monotonic() * 1000)


def timestamp() -> str:
    """Return a UTC timestamp string in HH:MM:SS.mmm format."""
    now = datetime.now(timezone.utc)
    return now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"


# ======================================================================
# Worker — runs stage pipeline for a single target on a dedicated thread
# ======================================================================

class TargetWorker:
    """
    Runs the orchestration stage pipeline for a single target.

    Each worker executes the requested stages sequentially and collects
    per-stage results.  Thread-safe: results are written only by the
    owning thread and read after ``join()``.
    """

    def __init__(self, target: Target, stages: list[str], dry_run: bool,
                 service_factory: ServiceFactory,
                 tcc_config_path: str = "",
                 tsn_config_path: str = ""):
        self.target = target
        self.stages = stages
        self.dry_run = dry_run
        self._service_factory = service_factory
        self._tcc_config_path = tcc_config_path
        self._tsn_config_path = tsn_config_path
        self.results: dict[str, StageResult] = {}
        self.success = True
        self.timed_out = False
        self.cancelled = False
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._logs: list[str] = []
        self._errors: list[str] = []

    # -- lifecycle -----------------------------------------------------

    def start(self):
        role = self.target.role or "local"
        self._thread = threading.Thread(
            target=self._run_pipeline,
            name=f"{role}/{self.target.id}",
            daemon=True,
        )
        self._thread.start()

    def join(self, timeout: int | None = None):
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                self.timed_out = True
                self.success = False
                self.cancel()
                msg = f"[{timestamp()}] [{self.target.id}] Worker timed out after {timeout}s"
                self._errors.append(msg)
                logger.error(msg)

    def cancel(self):
        """Signal the worker to stop after the current stage completes."""
        self._cancel_event.set()

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def logs(self) -> list[str]:
        """Read-only view of accumulated log lines (safe to read after join)."""
        return self._logs

    @property
    def errors(self) -> list[str]:
        """Read-only view of accumulated error lines (safe to read after join)."""
        return self._errors

    # -- stage pipeline (runs inside worker thread) --------------------

    def _run_pipeline(self):
        set_role_log_context(self.target)
        logger.info("[%s] Starting stage pipeline", self.target.id)
        for stage_name in self.stages:
            if self._cancel_event.is_set():
                self.cancelled = True
                self.success = False
                msg = f"[{timestamp()}] [{self.target.id}] Pipeline cancelled before stage '{stage_name}'"
                self._logs.append(msg)
                logger.info(msg)
                self._skip_stage(stage_name, reason="Cancelled")
                continue
            if not self.success:
                self._skip_stage(stage_name)
                continue
            self._execute_stage(stage_name)
        logger.info("[%s] Pipeline finished (success=%s)", self.target.id, self.success)

    def _execute_stage(self, stage_name: str):
        logger.info("[%s] Stage '%s' → RUNNING", self.target.id, stage_name)
        stage_start_ms = now_ms()
        ctx = StageContext(
            target=self.target,
            dry_run=self.dry_run,
            hub_service=self._service_factory.build(self.target),
            tcc_config_path=self._tcc_config_path,
            tsn_config_path=self._tsn_config_path,
        )
        all_output: list[str] = []
        try:
            steps = get_single_target_steps(stage_name)
            for step_name, _roles, handler in steps:
                logger.info("[%s] Stage '%s' / step '%s' → RUNNING", self.target.id, stage_name, step_name)
                step_start_ms = now_ms()
                step_output = handler(ctx)
                all_output.extend(step_output)
                logger.info(
                    "[%s] Stage '%s' / step '%s' → done (%d ms)",
                    self.target.id, stage_name, step_name, now_ms() - step_start_ms,
                )

            duration = now_ms() - stage_start_ms
            self.results[stage_name] = StageResult(
                success=True,
                output=all_output,
                duration_ms=duration,
                target_id=self.target.id,
            )
            self._logs.append(f"[{timestamp()}] [{self.target.id}] Stage '{stage_name}' completed in {duration} ms")
            logger.info("[%s] Stage '%s' → SUCCESS (%d ms)", self.target.id, stage_name, duration)
        except Exception as exc:
            duration = now_ms() - stage_start_ms
            self.results[stage_name] = StageResult(
                success=False,
                output=all_output + [str(exc)],
                duration_ms=duration,
                target_id=self.target.id,
            )
            self.success = False
            error_msg = f"[{timestamp()}] [{self.target.id}] Stage '{stage_name}' failed: {exc}"
            self._errors.append(error_msg)
            logger.error("%s", error_msg)

    def _skip_stage(self, stage_name: str, reason: str = "Prior failure"):
        logger.info("[%s] Stage '%s' → SKIPPED (%s)", self.target.id, stage_name, reason)
        self.results[stage_name] = StageResult(
            success=False,
            output=[f"Skipped: {reason}"],
            target_id=self.target.id,
        )
