# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Single-target execution of all stages. This is the default mode when no topology is specified.
In default mode, the following features are available through CLI Flags.

Just support the following CLI flags in all modes (single and multi-target).
Benefit:Reduced complexity for users who only need single-target orchestration,
while still allowing multi-target users to use the same flags for consistency.

  --install         Run the install stage to set up tools and dependencies.
  --apply-config    Run the apply_config stage to apply TCC and TSN configurations.
  --run             Run the run stage to execute the defined workflow.
  --results         Run the results stage to collect results and logs.

Commands: tch {}
  config-show     Show current CLI configuration settings.
  daemon-restart  Restart the daemon service.
  daemon-start    Start the daemon service.
  daemon-status   Show the status of the daemon.
  daemon-stop     Stop the daemon service.
  orchestrate     Run an orchestrated TIME deployment across one or more...
  tcc             Commands for managing TCC configurations.
  tsn             Commands for managing TSN configurations.

Commands: tch tsn {}
  apply     Apply TSN configuration from XML/YAML file.
  reset     Reset TSN configuration to defaults.
  status    Show current TSN configuration status.
  validate  Validate TSN configuration file.

Commands: tch tcc {}
  apply     Apply TCC configuration from XML/YAML file.
  reset     Reset TCC configuration to defaults.
  status    Show current TCC configuration status.
  validate  Validate TCC configuration file.

Stage Implementations for Single-Target (Local) Orchestration

Each stage is a callable that receives a Target and a dry_run flag,
and returns a list of output lines.  Replace the sample logic in each
stage with real operations when ready.

Stages are registered in STAGE_REGISTRY keyed by stage_name.
This file only handles SINGLE_LOCAL topology (role=None).
Multi-target topologies (B2B, MULTI_DUT) use multi_target.py.
"""

from __future__ import annotations

# TODO: Fill in the actual supported functions and steps for single-target mode.
# TODO: Ensure that the step actions delegate to the appropriate composite methods on TimeHubService,
#       and that all internal sequencing lives inside the service, not in this registry.

import logging

from .models import StageContext, StageHandler

__all__ = [
    "get_steps"
]

logger = logging.getLogger("orchestrator.single_target")


# ==================================================================
# This core function retrieves the step list for a specified stage
# in single-target mode, allowing execution under the orchestrator's control.
# ==================================================================
# Each tuple: (step_name, roles, action)
StepEntry = tuple[str, set[str | None], StageHandler]

def get_steps(stage_name: str) -> list[StepEntry]:
    """Return the step list for a stage in single-target mode.

    Each stage maps to exactly one step targeting role=None.

    :raises KeyError: If no handler is registered for the stage.
    """
    try:
        handler = STAGE_REGISTRY[stage_name]
    except KeyError:
        raise KeyError(
            f"No handler registered for stage '{stage_name}'"
        ) from None

    return [(stage_name, {None}, handler)]


# ==================================================================
# Stage Handlers
# ==================================================================

def _install_default(ctx: StageContext) -> list[str]:
    return ctx.hub_service.stage_install(ctx)


def _apply_config_default(ctx: StageContext) -> list[str]:
    return ctx.hub_service.stage_apply_config(ctx)


def _run_default(ctx: StageContext) -> list[str]:
    return ctx.hub_service.stage_run(ctx)


def _results_default(ctx: StageContext) -> list[str]:
    return ctx.hub_service.stage_results(ctx)


# ==================================================================
# STAGE REGISTRY — map stage_name to handler function
# ==================================================================

STAGE_REGISTRY: dict[str, StageHandler] = {
    "install":      _install_default,
    "apply_config": _apply_config_default,
    "run":          _run_default,
    "results":      _results_default,
}

