# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""Request interface models: CLI→Orchestrator commands and orchestration config/result."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from .pipeline import WORKFLOW_STAGES, StageResult
from .topology import DeploymentTopologyType, Target

__all__ = [
    "ServiceCommand",
    "ServiceType",
    "ServiceRequest",
    "OrchestratorConfig",
    "OrchestratorResult",
    "StageResult",
]


class ServiceCommand(str, Enum):
    """Commands that can be routed through the Orchestrator."""

    APPLY       = "apply"
    STATUS      = "status"
    RESET       = "reset"
    VALIDATE    = "validate"
    ORCHESTRATE = "orchestrate"  # triggers the full multi-stage workflow pipeline
    # -- operational commands (KPI pipeline) --
    START       = "start"    # start a service (timesync, workload)
    STOP        = "stop"     # stop a service  (timesync, workload)
    COLLECT     = "collect"  # collect results/logs (report)


class ServiceType(str, Enum):
    """Service domain targeted by a command."""

    TSN      = "tsn"
    TCC      = "tcc"
    BOTH     = "both"
    # -- KPI-specific service domains --
    RTC      = "rtc"       # RTC testbench application configuration
    TIMESYNC = "timesync"  # PTP / time synchronisation
    WORKLOAD = "workload"  # AI workload and testbench transmitter/receiver
    TEST     = "test"      # test execution lifecycle
    REPORT   = "report"    # result collection and display


@dataclass
class ServiceRequest:
    """A CLI-originated command routed through :class:`Orchestrator.execute`.

    :param command: The operation to perform.
    :param service_type: Which service domain the command targets.
    :param config_path: Path to XML/YAML config file (for apply/validate commands).
    :param interface: Network interface name (for TSN status/reset commands).
    :param dry_run: If True, simulate without side effects.
    :param orchestrator_config: Required when *command* is ``ORCHESTRATE``.
    """

    command: ServiceCommand
    service_type: ServiceType
    config_path: Optional[str] = None
    interface: Optional[str] = None
    dry_run: bool = False
    orchestrator_config: Optional["OrchestratorConfig"] = None


@dataclass
class OrchestratorConfig:
    """Configuration for the Orchestrator."""

    topology_type: DeploymentTopologyType  # Deployment topology strategy to use
    targets: List[Target]                  # List of deployment targets (DUTs)
    tcc_config: str                        # TCC config file path
    tsn_config: str                        # TSN config file path
    stages_to_run: List[str]               # List of stages to execute in the workflow
    dry_run: bool = False                  # If true, simulate execution without performing actual operations
    test_duration: Optional[int] = None    # Optional expected duration of the test in seconds (for progress reporting)
    timeout: Optional[int] = None          # Optional maximum allowed duration for the entire workflow in seconds (for timeout handling)
    # TODO: Plugins configuration (AI workload and validation plugins)

    def __post_init__(self):
        invalid = set(self.stages_to_run) - set(WORKFLOW_STAGES)
        if invalid:
            raise ValueError(
                f"Unknown stages: {sorted(invalid)}. Valid stages: {list(WORKFLOW_STAGES)}"
            )


@dataclass
class OrchestratorResult:
    """Result returned by the Orchestrator after workflow execution."""

    success: bool                   # True if all stages completed without error
    logs: List[str]                 # Informational log messages from the workflow
    errors: List[str]               # Error messages if any stage failed
    data: Optional[Any] = None      # Optional payload for status/query commands; None for workflow results
    stage_results: Optional[Dict[str, Dict[str, StageResult]]] = None
    # Per-target stage results: {target_id: {stage_name: StageResult}}
    # Populated for workflow (ORCHESTRATE) runs; None for direct service commands.
