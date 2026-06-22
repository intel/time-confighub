# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""Execution pipeline models: stage protocol, context, handler type, and results."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Protocol

from .topology import Target

__all__ = [
    "WorkflowStagePlugin",
    "StageContext",
    "StageHandler",
    "WORKFLOW_STAGES",
    "StageResult",
]


class WorkflowStagePlugin(Protocol):
    """Protocol that workflow-capable service backends must implement.

    The orchestrator calls these methods from stage step actions, passing
    the current :class:`StageContext`.  Each method maps to exactly one
    sub-step in the step registry, preserving all synchronisation barriers
    defined in the topology sequencers (``single_target.py`` /
    ``multi_target.py``).

    Implement this protocol on
    :class:`~.time_hub_service.TimeHubService` (or a test stub) and pass
    it as *hub_service* on the :class:`~.orchestrator.Orchestrator`.
    """

    # -- shared (single-target and multi-target) -----------------------

    def stage_install(self, ctx: StageContext) -> list[str]:
        """Install tools and dependencies on the target."""
        ...

    def stage_apply_config(self, ctx: StageContext) -> list[str]:
        """Apply TCC and TSN configurations on the target."""
        ...

    # -- single-target (role=None) -------------------------------------

    def stage_run(self, ctx: StageContext) -> list[str]:
        """Execute the full workflow on a single local target (all phases in one pass)."""
        ...

    def stage_results(self, ctx: StageContext) -> list[str]:
        """Collect results, stop workloads, and gather logs for this target's role.

        Dispatches on ``ctx.target.role``:

        - ``None`` (single local target) — stop all workloads and collect all logs
          in a single pass.
        - ``"talker"`` — stop testbench transmitter → collect testbench logs.
        - ``"listener"`` — stop testbench receiver → collect testbench logs
          → collect AI workload logs.

        Two sequential steps in the multi-target registry ensure the talker
        transmitter is stopped (and data delivery is complete) before the
        listener receivers are stopped.
        """
        ...

    # -- multi-target / run — PTP (role-dispatched, ordered steps) ------

    def stage_run_ptp_phase(self, ctx: StageContext) -> list[str]:
        """Run the full PTP setup phase for this target's role.

        Dispatches to the talker (GM) or listener (slave) path based on
        ``ctx.target.role``.  Both paths end with a verified lock, so the
        step barrier in the orchestrator is only crossed when all targets
        have confirmed PTP sync — no explicit ordering between talker and
        listener steps is needed in the registry.

        .. deprecated::
            Superseded by the three-step PTP sequence
            (``stage_verify_hw`` → ``stage_start_ptp`` → ``stage_validate_timesync``)
            which gives the orchestrator explicit control over listener-before-talker
            ordering and mutual rendezvous at sync validation.
        """
        ...

    def stage_verify_hw(self, ctx: StageContext) -> list[str]:
        """Verify hardware readiness on this target before PTP startup.

        Runs in parallel on all roles (talker and listener).  The step
        barrier in the orchestrator ensures both targets have passed HW
        verification before any PTP daemon is started.

        :param ctx: Runtime stage context (``ctx.target.role`` selects the path).
        :return: Log lines produced during verification.
        :rtype: list[str]
        """
        ...

    def stage_start_ptp(self, ctx: StageContext) -> list[str]:
        """Start the PTP daemon for this target's role.

        Dispatches on ``ctx.target.role``:

        - ``"listener"`` — start PTP slave (gPTP boundary/slave clock).
          Must complete before the talker step begins so the slave is
          already listening when the GM starts advertising.
        - ``"talker"`` — start PTP grandmaster clock.

        Two sequential steps in the multi-target registry enforce the
        listener-before-talker ordering; this method only starts the
        daemon for whichever role it is called with.

        :param ctx: Runtime stage context.
        :return: Log lines produced during startup.
        :rtype: list[str]
        """
        ...

    def stage_validate_timesync(self, ctx: StageContext) -> list[str]:
        """Poll for PTP lock and validate the sub-microsecond offset target.

        Each target independently polls until its clock offset is within the
        required budget (or until timeout).  When ``ctx.barrier`` is set, both
        targets call ``ctx.barrier.wait()`` once their local sync is confirmed,
        providing a mutual rendezvous before the step is declared complete.
        This guarantees the orchestrator does not advance to workload startup
        until *every* target in the topology has achieved the required sync
        quality simultaneously.

        :param ctx: Runtime stage context; ``ctx.barrier`` carries the
            :class:`threading.Barrier` shared across all targets in this step.
        :return: Log lines produced during validation.
        :rtype: list[str]
        :raises TimeoutError: If the microsecond offset target is not achieved
            within the configured deadline.
        :raises threading.BrokenBarrierError: If another target in the same
            step raises before reaching the barrier.
        """
        ...

    # -- multi-target / run — workloads (role-dispatched) --------------

    def stage_run_workloads(self, ctx: StageContext) -> list[str]:
        """Start workloads for this target's role.

        Dispatches on ``ctx.target.role``:

        - ``"listener"`` — start AI workload → start testbench receiver.
          Receiver must be ready before the talker transmits.
        - ``"talker"`` — start testbench transmitter (last to start).

        Two sequential steps in the multi-target registry enforce the
        listener-before-talker ordering; the service only handles what
        runs on each role, not the cross-target sequence.
        """
        ...


@dataclass
class StageContext:
    """Runtime context passed to every stage handler.

    :param target: The DUT target for this stage execution.
    :param dry_run: If True, simulate execution without side effects.
    :param hub_service: Bound :class:`WorkflowStagePlugin` implementation
        (typically :class:`~.time_hub_service.TimeHubService`).  Stage step
        actions delegate all business logic through this interface.
    :param tcc_config_path: Path to the TCC XML config file, sourced from OrchestratorConfig.
    :param tsn_config_path: Path to the TSN XML config file, sourced from OrchestratorConfig.
    """

    target: Target
    dry_run: bool
    hub_service: Optional[WorkflowStagePlugin] = None
    tcc_config_path: Optional[str] = None
    tsn_config_path: Optional[str] = None
    barrier: Optional[threading.Barrier] = field(default=None, repr=False)


# Type alias for a stage handler callable
StageHandler = Callable[["StageContext"], List[str]]

WORKFLOW_STAGES = (
    "install",       # install necessary tools and dependencies on targets (Testbench, AI Workloads)
    "apply_config",  # apply TCC and TSN configurations on targets
    "run",           # execute the defined workflow (e.g., start TCC, run test workloads)
    "results",       # collect results, logs, and any relevant data from targets after workflow execution
)


@dataclass
class StageResult:
    """Represents the result of executing a workflow stage."""

    target_id: str                    # ID of the target associated with this stage result
    success: bool                     # Indicates if the stage executed successfully
    output: List[str]                 # Output or logs generated by the stage
    duration_ms: Optional[int] = None  # Duration of stage execution in milliseconds
