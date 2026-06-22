# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Single-target execution of all stages. This is the default mode when no topology is specified.

TODO: This mode is still just a placeholder and won't be needed until
        RTC testbench supports single-target topology.

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

