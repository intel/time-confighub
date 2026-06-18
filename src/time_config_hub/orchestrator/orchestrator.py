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

Related modules:
- worker.py         — _TargetWorker: per-target thread and stage pipeline
- target_manager.py — resolve_targets(), register_targets(): topology and SSH setup
- ipc.py            — Unix socket server and client helpers
"""

import logging
import threading
from typing import Any, Dict, Optional

from .models import (
    DeploymentTopologyType,
    OrchestratorConfig,
    OrchestratorResult,
    ServiceCommand,
    ServiceRequest,
    ServiceType,
    StageContext,
    StageHandler,
    StageResult,
    Target,
)

from .multi_target import get_steps as get_multi_target_steps
from .worker import TargetWorker, timestamp, set_role_log_context
from .target_manager import register_targets, resolve_targets
from .service_factory import ServiceFactory

logger = logging.getLogger("orchestrator")
logger.setLevel(logging.DEBUG)  # Orchestrator logs are always DEBUG level for maximum visibility

# ======================================================================
# Orchestrator — coordinates topology, workers, and result aggregation
# ======================================================================

# ======================================================================
# Orchestrator — coordinates topology, workers, and result aggregation
# ======================================================================

class Orchestrator:
    """
    Coordinates deployment strategies, stage execution, and progress
    reporting for TCH workflows.

    The Orchestrator owns and self-initialises its :class:`TimeHubService`
    backend from *app_config*.  Callers (CLI, GUI, tests) must not
    construct or inject a service directly — the backend is internal.

    Usage (normal)::

        orch = Orchestrator(app_config=app_config)
        result = orch.execute(ServiceRequest(...))

    Usage (workflow pipeline via IPC daemon)::

        result = Orchestrator(config=orch_config, app_config=app_config).run()
    """

    def __init__(
        self,
        app_config: Optional[Dict[str, Any]] = None,
        config: Optional[OrchestratorConfig] = None,
    ):
        """
        :param app_config: Application configuration dict used to
            self-initialise the internal :class:`TimeHubService`.  When
            omitted the configuration is loaded from the default paths.
        :param config: Optional :class:`OrchestratorConfig` for workflow
            pipeline runs (``run()`` / IPC daemon path).
        """
        from .time_hub_service import TimeHubService  # local import avoids circular

        self.config = config
        self._logs: list[str] = []
        self._errors: list[str] = []
        self._stage_results: dict[str, dict[str, StageResult]] = {}

        if app_config is not None:
            self._hub_service = TimeHubService(app_config)
            self._service_factory = ServiceFactory(app_config)
        else:
            self._hub_service = TimeHubService.from_default_config()
            self._service_factory = ServiceFactory(self._hub_service.app_config)

    # ------------------------------------------------------------------
    # Internal service access — NOT part of the public API
    # ------------------------------------------------------------------

    @property
    def service_manager(self):
        """Expose the underlying :class:`ServiceManager` for daemon lifecycle
        commands (start, stop, restart, status).  This is the only sanctioned
        path for CLI daemon commands to reach system-level service control.

        :rtype: ServiceManager
        """
        return self._hub_service.service_manager

    def run(self) -> OrchestratorResult:
        """Execute the deployment workflow and return an aggregated result.

        Called internally by :meth:`execute` when the command is
        ``ORCHESTRATE``, and directly by the IPC daemon path when a legacy
        ``OrchestratorConfig``-only payload is received.  New callers should
        use :meth:`execute` with a :class:`~.models.ServiceRequest` so all
        routing lives in one place; ``run()`` is kept as the shared
        implementation entry point.
        """
        if self.config is None:
            return OrchestratorResult(
                success=False,
                logs=[],
                errors=["run() called without a config — use execute(ServiceRequest) or pass config= at construction"],
            )
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
                stage_results=self._stage_results or None,
            )

        except Exception as exc:
            logger.exception("Orchestration failed")
            self._errors.append(str(exc))
            return OrchestratorResult(
                success=False,
                logs=self._logs,
                errors=self._errors,
                stage_results=self._stage_results or None,
            )

    # -- internal helpers ----------------------------------------------

    def _log(self, message: str):
        stamped = f"[{timestamp()}] {message}"
        logger.info("%s", message)
        self._logs.append(stamped)

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
        assert self.config is not None, "_execute_workflow requires config"
        targets = resolve_targets(self.config)
        register_targets(targets, log=self._log)

        is_multi_dut = self.config.topology_type in (
            DeploymentTopologyType.B2B,
            DeploymentTopologyType.MULTI_DUT,
        )

        if not is_multi_dut:
            # SINGLE_LOCAL — one worker, all stages at once
            self._log(f"Single target mode: stages={self.config.stages_to_run}")
            worker = TargetWorker(
                target=targets[0],
                stages=self.config.stages_to_run,
                dry_run=self.config.dry_run,
                service_factory=self._service_factory,
                tcc_config_path=self.config.tcc_config,
                tsn_config_path=self.config.tsn_config,
            )
            worker.start()
            worker.join(timeout=self.config.timeout)
            self._aggregate_results([worker])
            return

        # Multi-DUT — execute one stage at a time, step by step
        self._log(f"Multi-DUT mode: synchronizing stages across {len(targets)} target(s)")

        self._log(f"Executing stages in order: {', '.join(self.config.stages_to_run)}")
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
        assert self.config is not None, "_execute_stage_steps requires config"
        _config = self.config  # captured so closures see a non-Optional reference
        _BANNER = "─" * 60
        for step_name, roles, action in steps:
            step_targets = [t for t in targets if t.role in roles]
            if not step_targets:
                self._log(f"  Step '{step_name}' — no matching targets, skipping")
                continue

            role_labels = "/".join(sorted(roles))
            self._log(f"{_BANNER}")
            self._log(f"STEP  {stage_name} › {step_name}  [{role_labels}]  targets={[t.id for t in step_targets]}")
            self._log(f"{_BANNER}")

            # Run this step on matching targets in parallel.
            # A Barrier is created when more than one target participates so that
            # handlers (e.g. validate_timesync) can rendezvous mid-step via ctx.barrier.
            errors: list[str] = []
            lock = threading.Lock()
            n_targets = len(step_targets)
            barrier = threading.Barrier(n_targets) if n_targets > 1 else None
            if barrier is not None:
                logger.info(
                    "[barrier] created  step='%s'  parties=%d  targets=%s",
                    step_name,
                    n_targets,
                    [t.id for t in step_targets],
                )

            def _run_step(
                target: Target,
                _action: StageHandler = action,
                _barrier: threading.Barrier | None = barrier,
            ) -> None:
                set_role_log_context(target)
                tname = threading.current_thread().name
                logger.info("[thread] started  thread='%s'  step='%s'", tname, step_name)
                try:
                    ctx = StageContext(
                        target=target,
                        dry_run=_config.dry_run,
                        hub_service=self._service_factory.build(target),
                        tcc_config_path=_config.tcc_config,
                        tsn_config_path=_config.tsn_config,
                        barrier=_barrier,
                    )
                    output = _action(ctx)
                    self._log(f"  Step '{step_name}' [{target.id}] → done")
                    logger.debug("Step output [%s]: %s", target.id, output)
                except threading.BrokenBarrierError:
                    # Another thread already recorded a failure and broke the
                    # barrier; add a contextual note but avoid double-reporting.
                    logger.debug(
                        "[barrier] broken-error caught  thread='%s'  step='%s'",
                        threading.current_thread().name,
                        step_name,
                    )
                    with lock:
                        errors.append(
                            f"[{target.id}] Step '{step_name}' aborted: barrier broken by a peer"
                        )
                except Exception as exc:
                    if _barrier is not None:
                        logger.debug(
                            "[barrier] aborting  thread='%s'  step='%s'  reason=%r",
                            threading.current_thread().name,
                            step_name,
                            str(exc),
                        )
                        _barrier.abort()  # unblock any peer waiting at the barrier
                    with lock:
                        errors.append(f"[{target.id}] Step '{step_name}' failed: {exc}")

            threads: list[tuple[threading.Thread, Target]] = []
            for target in step_targets:
                role = target.role or "local"
                th = threading.Thread(
                    target=_run_step,
                    kwargs={"target": target},
                    name=f"{role}/{target.id}",
                    daemon=True,
                )
                threads.append((th, target))
                th.start()
                logger.info("[thread] dispatched  thread='%s'  step='%s'", th.name, step_name)

            for th, target in threads:
                logger.info(
                    "[thread] joining  thread='%s'  step='%s'  timeout=%ss",
                    th.name,
                    step_name,
                    _config.timeout,
                )
                th.join(timeout=_config.timeout)
                if th.is_alive():
                    logger.debug("[thread] timed out  thread='%s'  step='%s'", th.name, step_name)
                    with lock:
                        errors.append(
                            f"[{target.id}] Step '{step_name}' timed out after {_config.timeout}s"
                        )
                else:
                    logger.info("[thread] joined  thread='%s'  step='%s'", th.name, step_name)

            if errors:
                for err in errors:
                    self._errors.append(f"[{timestamp()}] {err}")
                    logger.error(err)
                return False

        self._log(f"Stage '{stage_name}' → all steps completed")
        self._log("═" * 60)
        return True

    def _aggregate_results(self, workers: list[TargetWorker]):
        """Merge per-worker logs, errors, and stage results into orchestrator-level state."""
        for worker in workers:
            self._logs.extend(worker.logs)
            self._errors.extend(worker.errors)
            logger.info("Worker logs for target '%s': %s", worker.target.id, worker.logs)
            logger.info("Worker errors for target '%s': %s", worker.target.id, worker.errors)
            if worker.results:
                self._stage_results[worker.target.id] = worker.results
            stages_label = ", ".join(worker.stages)
            if worker.timed_out:
                self._log(f"Target '{worker.target.id}' timed out during stage(s): {stages_label}")
            elif worker.cancelled:
                self._log(f"Target '{worker.target.id}' was cancelled during stage(s): {stages_label}")
            elif not worker.success:
                self._log(f"Target '{worker.target.id}' failed stage(s): {stages_label}")
            else:
                self._log(f"Target '{worker.target.id}' completed stage(s): {stages_label}")

    # ------------------------------------------------------------------
    # Service-based entry point (CLI → Orchestrator → TimeHubService)
    # ------------------------------------------------------------------

    def execute(self, request: ServiceRequest) -> OrchestratorResult:
        """Single entry point for all CLI-originated service commands.

        Routes :attr:`~.models.ServiceCommand.ORCHESTRATE` requests through
        the full multi-stage workflow pipeline (:meth:`run`).  All other
        commands (apply, status, reset, validate) are dispatched directly to
        the bound :class:`~.time_hub_service.TimeHubService`.

        :param ServiceRequest request: The service command to execute.
        :return: Aggregated result with success flag, logs, errors, and
            optional *data* payload for status/query commands.
        :rtype: OrchestratorResult
        """
        self._logs = []
        self._errors = []
        self._stage_results = {}

        if request.command == ServiceCommand.ORCHESTRATE:
            if request.orchestrator_config is None:
                return OrchestratorResult(
                    success=False,
                    logs=[],
                    errors=["ORCHESTRATE command requires orchestrator_config to be set on the ServiceRequest"],
                )
            self.config = request.orchestrator_config
            return self.run()

        return self._dispatch_service_command(request)

    def _dispatch_service_command(self, request: ServiceRequest) -> OrchestratorResult:
        """Dispatch a non-workflow command to the bound TimeHubService.

        :param ServiceRequest request: The command to dispatch.
        :return: Result with success flag and optional *data* for status/query
            commands.
        :rtype: OrchestratorResult
        """
        hub = self._hub_service
        svc_label = request.service_type.value
        data = None

        self._log(f"[Orchestrator]Received service command: {svc_label}/{request.command.value}")
        try:
            if request.service_type == ServiceType.TSN:
                if request.command == ServiceCommand.APPLY:
                    self._log(f"[tsn] apply: {request.config_path} (dry_run={request.dry_run})")
                    hub.apply_config(request.config_path or "", dry_run=request.dry_run)
                elif request.command == ServiceCommand.STATUS:
                    self._log(f"[tsn] status: interface={request.interface}")
                    data = hub.get_status(interface=request.interface or "")
                elif request.command == ServiceCommand.RESET:
                    self._log(f"[tsn] reset: interface={request.interface}")
                    hub.reset_config(interface=request.interface or "")
                elif request.command == ServiceCommand.VALIDATE:
                    self._log(f"[tsn] validate: {request.config_path}")
                    hub.validate_config(request.config_path or "")

            elif request.service_type == ServiceType.TCC:
                if request.command == ServiceCommand.APPLY:
                    self._log(f"[tcc] apply: {request.config_path} (dry_run={request.dry_run})")
                    hub.apply_tcc_config(request.config_path or "", dry_run=request.dry_run)
                elif request.command == ServiceCommand.STATUS:
                    self._log("[tcc] status")
                    data = hub.get_tcc_status()
                elif request.command == ServiceCommand.RESET:
                    self._log("[tcc] reset")
                    hub.reset_tcc_config()
                elif request.command == ServiceCommand.VALIDATE:
                    self._log(f"[tcc] validate: {request.config_path}")
                    hub.validate_tcc_config(request.config_path or "")

            # -- KPI service domains (implementation delegated to future service modules) --

            elif request.service_type == ServiceType.RTC:
                # TODO: Implement RTC testbench application configuration service
                #       Route to a dedicated RTCService (apply/status/reset/validate)
                raise NotImplementedError(
                    f"ServiceType.RTC command '{request.command.value}' is not yet implemented"
                )

            elif request.service_type == ServiceType.TIMESYNC:
                # TODO: Implement PTP timesync service
                #       Route to PtpService (start/stop/status)
                raise NotImplementedError(
                    f"ServiceType.TIMESYNC command '{request.command.value}' is not yet implemented"
                )

            elif request.service_type == ServiceType.WORKLOAD:
                # TODO: Implement workload service dispatcher
                #       Route to AIWorkloadService / TestbenchService based on role (interface field)
                raise NotImplementedError(
                    f"ServiceType.WORKLOAD command '{request.command.value}' is not yet implemented"
                )

            elif request.service_type == ServiceType.TEST:
                # TODO: Implement test lifecycle service
                #       Route to a TestService or query orchestration run state
                raise NotImplementedError(
                    f"ServiceType.TEST command '{request.command.value}' is not yet implemented"
                )

            elif request.service_type == ServiceType.REPORT:
                # TODO: Implement report collection and display service
                #       Route to a ReportService (collect logs, aggregate metrics, show results)
                raise NotImplementedError(
                    f"ServiceType.REPORT command '{request.command.value}' is not yet implemented"
                )

            self._log(f"[Orchestrator][{svc_label}] {request.command.value} completed successfully")
            return OrchestratorResult(
                success=True,
                logs=list(self._logs),
                errors=[],
                data=data,
            )

        except Exception as exc:
            logger.exception("Service command [%s/%s] failed", svc_label, request.command.value)
            self._errors.append(str(exc))
            return OrchestratorResult(
                success=False,
                logs=list(self._logs),
                errors=list(self._errors),
            )
