# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Main Orchestrator Class

Entry point for executing deployment workflows, managing task execution,
and coordinating communication between workers.

Coordinates topology strategies, stage workflow and progress reporting.

Workflow execution is multi-threaded with one worker thread per target.
Each worker executes its assigned stages sequentially and reports results
back to the orchestrator, which aggregates logs and errors.

For SINGLE_LOCAL topology, a single worker runs all stages in one pass.
For B2B / MULTI_DUT topologies, the orchestrator synchronizes stage
progression: all targets must complete stage N before any target begins
stage N+1.  Within each stage, targets execute in parallel.

The workflow stages are designed for flexible control: the caller can
send multiple requests with different stages (e.g. run only "install"
first, then "apply_config" separately).  For CI/CD scenarios the full
pipeline (install → apply_config → run → results) is typically executed
in a single request.

The orchestrator runs within the existing TCH daemon (tch.service) as a
socket listener thread.  The CLI sends OrchestratorConfig via Unix socket,
the daemon runs the workflow, and returns OrchestratorResult.
"""

import logging
import threading
import time
from datetime import datetime, timezone

from .models import (
    DeploymentTopologyType,
    OrchestratorConfig,
    OrchestratorResult,
    StageHandler,
    StageResult,
    Target,
)

from .single_target import get_steps as get_single_target_steps
from .multi_target import get_steps as get_multi_target_steps

logger = logging.getLogger("orchestrator")

def _now_ms() -> int:
    return int(time.monotonic() * 1000)

def _timestamp() -> str:
    """Return a UTC timestamp string in HH:MM:SS.mmm format."""
    now = datetime.now(timezone.utc)
    return now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"

# ======================================================================
# Worker — runs stage pipeline for a single target on a dedicated thread
# ======================================================================

class _TargetWorker:
    """
    Runs the orchestration stage pipeline for a single target.

    Each worker executes the requested stages sequentially and collects
    per-stage results.  Thread-safe: results are written only by the
    owning thread and read after ``join()``.
    """

    def __init__(self, target: Target, stages: list[str], dry_run: bool):
        self.target = target
        self.stages = stages
        self.dry_run = dry_run
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
        self._thread = threading.Thread(
            target=self._run_pipeline,
            name=f"worker-{self.target.id}",
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
                msg = f"[{_timestamp()}] [{self.target.id}] Worker timed out after {timeout}s"
                self._errors.append(msg)
                logger.error(msg)

    def cancel(self):
        """Signal the worker to stop after the current stage completes."""
        self._cancel_event.set()

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- stage pipeline (runs inside worker thread) --------------------

    def _run_pipeline(self):
        logger.info("[%s] Starting stage pipeline", self.target.id)
        for stage_name in self.stages:
            if self._cancel_event.is_set():
                self.cancelled = True
                self.success = False
                msg = f"[{_timestamp()}] [{self.target.id}] Pipeline cancelled before stage '{stage_name}'"
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
        start_ms = _now_ms()
        try:
            steps = get_single_target_steps(stage_name)
            _, _, handler = steps[0]
            output = handler(self.target, self.dry_run)
            duration = _now_ms() - start_ms
            self.results[stage_name] = StageResult(
                success=True,
                output=output,
                duration_ms=duration,
                target_id=self.target.id,
            )
            self._logs.append(f"[{_timestamp()}] [{self.target.id}] Stage '{stage_name}' completed in {duration} ms")
            logger.info("[%s] Stage '%s' → SUCCESS (%d ms)", self.target.id, stage_name, duration)
        except Exception as exc:
            duration = _now_ms() - start_ms
            self.results[stage_name] = StageResult(
                success=False,
                output=[str(exc)],
                duration_ms=duration,
                target_id=self.target.id,
            )
            self.success = False
            error_msg = f"[{_timestamp()}] [{self.target.id}] Stage '{stage_name}' failed: {exc}"
            self._errors.append(error_msg)
            logger.error("%s", error_msg)

    def _skip_stage(self, stage_name: str, reason: str = "Prior failure"):
        logger.info("[%s] Stage '%s' → SKIPPED (%s)", self.target.id, stage_name, reason)
        self.results[stage_name] = StageResult(
            success=False,
            output=[f"Skipped: {reason}"],
            target_id=self.target.id,
        )


# ======================================================================
# Orchestrator — coordinates topology, workers, and result aggregation
# ======================================================================

class Orchestrator:
    """
    Coordinates deployment strategies, stage execution, and progress
    reporting for TCH workflows.

    Usage::

        result = Orchestrator(config).run()
    """

    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self._logs: list[str] = []
        self._errors: list[str] = []

    def run(self) -> OrchestratorResult:
        """Execute the deployment workflow and return an aggregated result."""
        try:
            self._log(f"Starting orchestration: topology={self.config.topology_type.value}, "
                       f"targets={len(self.config.targets)}, "
                       f"stages={self.config.stages_to_run}")

            if self.config.dry_run:
                self._log("DRY RUN MODE: No changes will be applied")

            self._execute_workflow()

            overall_success = len(self._errors) == 0
            self._log("Orchestration completed" + (" successfully" if overall_success else " with errors"))
            return OrchestratorResult(
                success=overall_success,
                logs=self._logs,
                errors=self._errors,
            )

        except Exception as exc:
            logger.exception("Orchestration failed")
            self._errors.append(str(exc))
            return OrchestratorResult(
                success=False,
                logs=self._logs,
                errors=self._errors,
            )

    # -- internal helpers ----------------------------------------------

    def _log(self, message: str):
        stamped = f"[{_timestamp()}] {message}"
        logger.info("%s", message)
        self._logs.append(stamped)

    def _resolve_targets(self) -> list[Target]:
        """
        Return the list of targets with roles assigned based on topology.

        SINGLE_LOCAL → 1 target  (role=None)
        B2B          → 2 targets (1 talker + 1 listener)
        MULTI_DUT    → N targets (1 talker + N-1 listeners)
        """
        topo = self.config.topology_type
        targets = list(self.config.targets)          # shallow copy to avoid mutating input

        if topo == DeploymentTopologyType.SINGLE_LOCAL:
            if not targets:
                raise ValueError("SINGLE_LOCAL topology requires exactly one target")
            targets[0].role = None
            return targets[:1]

        if topo == DeploymentTopologyType.B2B:
            if len(targets) < 2:
                raise ValueError("B2B topology requires at least two targets (Talker and Listener)")
            targets[0].role = "talker"
            targets[1].role = "listener"
            return targets[:2]

        # MULTI_DUT — first target is talker, rest are listeners
        if len(targets) < 2:
            raise ValueError("MULTI_DUT topology requires at least two targets (1 Talker + N Listeners)")
        targets[0].role = "talker"
        for t in targets[1:]:
            t.role = "listener"
        return targets

    # -- system_controller registration --------------------------------

    def _register_targets(self, targets: list[Target]) -> None:
        """Register remote targets with system_controller for SSH access.

        Skips local targets (ssh_user is None).  Raises on failure so
        the orchestration aborts before any stage runs.
        """
        for target in targets:
            # Local targets do not require registration
            if target.sc_target_id is None:
                self._log(f"Target '{target.id}' is local — skipping registration")
                continue

            # Check if already registered to avoid unnecessary SSH attempts
            if sc.is_registered(target.sc_target_id):
                self._log(f"Target '{target.sc_target_id}' already registered")
                continue

            # Register with system_controller for remote command execution
            result = sc.register(
                target.sc_target_id,
                password=target.ssh_password,
                port=target.ssh_port,
            )
            if result["status_code"] != TchStatusCode.SUCCESS:
                raise RuntimeError(
                    f"SSH registration failed for '{target.sc_target_id}': {result['error']}"
                )
            self._log(f"Registered target '{target.sc_target_id}'")

    # -- threaded workflow execution -----------------------------------

    def _execute_workflow(self):
        """
        Register remote targets with system_controller, then execute
        the stage pipeline.

        SINGLE_LOCAL: one worker runs all stages sequentially.
        B2B / MULTI_DUT: stages are executed one at a time across all
        targets — all targets must complete stage N before stage N+1
        begins.
        """
        targets = self._resolve_targets()
        self._register_targets(targets)

        is_multi_dut = self.config.topology_type in (
            DeploymentTopologyType.B2B,
            DeploymentTopologyType.MULTI_DUT,
        )

        if not is_multi_dut:
            # SINGLE_LOCAL — one worker, all stages at once
            self._log(f"Single target mode: stages={self.config.stages_to_run}")
            worker = _TargetWorker(
                target=targets[0],
                stages=self.config.stages_to_run,
                dry_run=self.config.dry_run,
            )
            worker.start()
            worker.join(timeout=self.config.timeout)
            self._aggregate_results([worker])
            return

        # Multi-DUT — execute one stage at a time, step by step
        self._log(f"Multi-DUT mode: synchronizing stages across {len(targets)} target(s)")

        for stage_name in self.config.stages_to_run:
            target_ids = [f"{t.id}({t.role})" for t in targets]
            steps = get_multi_target_steps(stage_name)

            self._log(f"Stage '{stage_name}' → {len(steps)} step(s) on {target_ids}")
            success = self._execute_stage_steps(stage_name, steps, targets)

            if not success:
                self._log(f"Stage '{stage_name}' failed — aborting pipeline")
                break

    def _execute_stage_steps(
        self,
        stage_name: str,
        steps: list[tuple[str, set[str], StageHandler]],
        targets: list[Target],
    ) -> bool:
        """Execute a stage as an ordered sequence of sub-steps.

        Each step dispatches to matching-role targets in parallel,
        then waits for all to complete before proceeding to the next step.
        Returns True if all steps succeeded.
        """
        for step_name, roles, action in steps:
            step_targets = [t for t in targets if t.role in roles]
            if not step_targets:
                self._log(f"  Step '{step_name}' — no matching targets, skipping")
                continue

            self._log(f"  Step '{step_name}' → {[t.id for t in step_targets]}")

            # Run this step on matching targets in parallel
            errors: list[str] = []
            lock = threading.Lock()

            def _run_step(target: Target, _action: StageHandler = action) -> None:
                try:
                    output = _action(target, self.config.dry_run)
                    self._log(f"  Step '{step_name}' [{target.id}] → done")
                    logger.debug("Step output [%s]: %s", target.id, output)
                except Exception as exc:
                    with lock:
                        errors.append(f"[{target.id}] Step '{step_name}' failed: {exc}")

            threads: list[threading.Thread] = []
            for target in step_targets:
                th = threading.Thread(
                    target=_run_step,
                    kwargs={"target": target},
                    name=f"step-{step_name}-{target.id}",
                    daemon=True,
                )
                threads.append(th)
                th.start()

            for th in threads:
                th.join(timeout=self.config.timeout)

            if errors:
                for err in errors:
                    self._errors.append(f"[{_timestamp()}] {err}")
                    logger.error(err)
                return False

        self._log(f"Stage '{stage_name}' → all steps completed")
        return True

    def _aggregate_results(self, workers: list[_TargetWorker]):
        """Merge per-worker logs, errors and results into orchestrator-level state."""
        for worker in workers:
            self._logs.extend(worker._logs)
            self._errors.extend(worker._errors)
            logger.info("Worker logs for target '%s': %s", worker.target.id, worker._logs)
            logger.info("Worker errors for target '%s': %s", worker.target.id, worker._errors)
            stages_label = ", ".join(worker.stages)
            if worker.timed_out:
                self._log(f"Target '{worker.target.id}' timed out during stage(s): {stages_label}")
            elif worker.cancelled:
                self._log(f"Target '{worker.target.id}' was cancelled during stage(s): {stages_label}")
            elif not worker.success:
                self._log(f"Target '{worker.target.id}' failed stage(s): {stages_label}")
            else:
                self._log(f"Target '{worker.target.id}' completed stage(s): {stages_label}")
