# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Request interface models: CLI→Orchestrator commands and orchestration config/result.

The orchestrator manages two primary types of requests:
1. Individual service commands (cmd>tch tsn apply ...), which are sent to the relevant service domain (TSN or TCC) for execution.

2. Multi-stage pipeline requests (cmd>tch pipeline ...), which initiate a workflow pipeline with multiple stages,
    where each stage may involve one or more service commands.

"""

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
    "PipelineConfig",
    "ServiceResult",
    "StageResult",
]


# ======================================================================
# Individual Service Request Command
# ======================================================================
class ServiceCommand(str, Enum):
    """Commands that can be routed through the Orchestrator."""

    APPLY       = "apply"
    STATUS      = "status"
    RESET       = "reset"
    VALIDATE    = "validate"
    PIPELINE    = "pipeline"  # triggers the full multi-stage workflow pipeline


class ServiceType(str, Enum):
    """Service domain targeted by a command."""

    TSN      = "tsn"
    TCC      = "tcc"
    BOTH     = "both"


@dataclass
class ServiceRequest:
    """A CLI-originated command routed through :class:`Orchestrator.execute`.

    :param command: The operation to perform.
    :param service_type: Which service domain the command targets.  ``None``
        when *command* is ``PIPELINE`` — the pipeline operates across all
        relevant services internally and does not target a single domain.
    :param config_path: Path to XML/YAML config file (for apply/validate commands).
    :param interface: Network interface name (for TSN status/reset commands).
    :param dry_run: If True, simulate without side effects.
    :param pipeline_config: Required when *command* is ``PIPELINE``.
    """

    command: ServiceCommand
    service_type: Optional[ServiceType] = None          # Required for service commands (APPLY, STATUS, RESET, VALIDATE); None for PIPELINE
    config_path: Optional[str] = None
    interface: Optional[str] = None
    dry_run: bool = False
    pipeline_config: Optional["PipelineConfig"] = None  # Required for Pipeline Orchestration Requests (PIPELINE command)


# ======================================================================
# Pipeline Orchestration Request for Multi-Stage Workflow
# ======================================================================
@dataclass
class PipelineConfig:
    """Configuration for the Orchestrator."""

    topology_type: DeploymentTopologyType  # Deployment topology strategy to use
    targets: List[Target]                  # List of deployment targets (DUTs)
    tcc_config: str                        # TCC config file path
    tsn_config: str                        # TSN config file path
    stages_to_run: List[str]               # List of stages to execute in the workflow
    dry_run: bool = False                  # If true, simulate execution without performing actual operations
    test_duration: Optional[int] = None    # Optional expected duration of the test in seconds (for progress reporting)
    timeout: Optional[int] = None          # Optional maximum allowed duration for the entire workflow in seconds (for timeout handling)


# ======================================================================
# Common Result Model for Service Commands and Workflows
# ======================================================================
@dataclass
class ServiceResult:
    """Result of executing a service command or workflow."""

    success: bool                   # True if all stages completed without error
    logs: List[str]                 # Informational log messages from the workflow
    errors: List[str]               # Error messages if any stage failed
    data: Optional[Any] = None      # Optional payload for status/query commands; None for workflow results
    stage_results: Optional[Dict[str, Dict[str, StageResult]]] = None
