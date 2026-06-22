# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

# TODO: Fill in the actual supported functions and steps for multi-target mode.
# TODO: Ensure that the step actions delegate to the appropriate composite methods on TimeHubService,
#       and that all internal sequencing lives inside the service, not in this registry.

"""
Multi-DUT Step Definitions for B2B and MULTI_DUT Orchestration

Defines the ordered sub-step sequences used by the orchestrator when
executing stages in B2B or MULTI_DUT topologies.

Each entry in ``FUNC_REQ_REGISTRY`` maps a stage name to a list of
sub-step tuples: ``(step_name, roles, action)``.

The orchestrator executes steps sequentially.  Within each step,
targets whose role matches ``roles`` run the ``action`` in parallel.
All matching targets must complete a step before the next step begins.

For parallel stages (install, apply_config), a single step targeting
both roles achieves the same effect as the original parallel dispatch.

For ordered stages (run, results), multiple steps enforce the required
talker/listener execution sequence.  Each step delegates to the
relevant composite method on ``TimeHubService`` (via the
``WorkflowStagePlugin`` interface); all internal sequencing lives
inside the service, not in this registry.

"""

from __future__ import annotations

import logging

from .models import StageContext, StageHandler

# Public API
__all__ = [
    "get_steps"
]

logger = logging.getLogger("orchestrator.multi_target")


# ==================================================================
# This core function retrieves the step list for a specified stage
# in multi-target mode, allowing execution under the orchestrator's control.
# ==================================================================
# Each tuple: (step_name, roles, action)
StepEntry = tuple[str, set[str | None], StageHandler]

# All known roles in multi-DUT topologies.
# Add new roles here; every role-omitted step() call picks them up automatically.
ALL_ROLES: frozenset[str] = frozenset({"reference", "mirror"})

def step(name: str, action: StageHandler, *roles: str) -> StepEntry:
    return (name, set(roles) if roles else set(ALL_ROLES), action)

def get_steps(stage_name: str) -> list[StepEntry]:
    """Return the ordered step list for a stage in multi-target mode."""

    try:
        return STAGE_STEP_REGISTRY[stage_name]
    except KeyError:
        raise KeyError(
            f"No steps defined for stage '{stage_name}'"
        ) from None


# ==================================================================
# Stage Handlers
# ==================================================================
def _install(ctx: StageContext) -> list[str]:
    return ctx.hub_service.stage_install(ctx)


def _apply_config(ctx: StageContext) -> list[str]:
    return ctx.hub_service.stage_apply_config(ctx)


def _verify_hw(ctx: StageContext) -> list[str]:
    return ctx.hub_service.stage_verify_hw(ctx)


def _start_ptp(ctx: StageContext) -> list[str]:
    return ctx.hub_service.stage_start_ptp(ctx)


def _validate_timesync(ctx: StageContext) -> list[str]:
    return ctx.hub_service.stage_validate_timesync(ctx)


def _run_workloads(ctx: StageContext) -> list[str]:
    return ctx.hub_service.stage_run_workloads(ctx)


def _results(ctx: StageContext) -> list[str]:
    return ctx.hub_service.stage_results(ctx)


# ==================================================================
# STEP REGISTRY — map stage_name to step list
# ==================================================================
# PTP run sequence for B2B / MULTI_DUT:
#
#  1. all:verify_hw          — verify HW on reference + mirror in parallel.
#                              Step join acts as barrier: neither side
#                              proceeds until both pass HW checks.
#
#  2. mirror:start_ptp     — start PTP slave on mirror(s) first so the
#                              slave is already listening when the GM starts
#                              advertising.
#
#  3. reference:start_ptp       — start PTP grandmaster on reference(s).
#                              Step join ensures mirror is up before this
#                              step begins.
#
#  4. all:validate_timesync  — both targets poll until offset < budget.
#                              A threading.Barrier(n) is injected into
#                              ctx.barrier so both rendezvous once their
#                              local sync is confirmed, guaranteeing the
#                              pipeline does not advance until *every*
#                              target has achieved the microsecond target
#                              simultaneously.
#
#  5. mirror:workloads    — mirror-side workloads (AI + receiver) start
#                              only after full timesync is established.
#
#  6. reference:workloads       — reference transmitter starts last.

STAGE_STEP_REGISTRY: dict[str, list[StepEntry]] = {

    "install": [
        step("all:install",         _install),
    ],
    "apply_config": [
        step("all:apply_config",    _apply_config),
    ],
    "run": [
        step("all:verify_hw",         _verify_hw),
        step("reference:start_ptp",    _start_ptp,         "reference"),
        step("mirror:start_ptp",      _start_ptp,         "mirror"),
        step("all:validate_timesync", _validate_timesync),
        step("reference:workloads",   _run_workloads,     "reference"),
        step("mirror:workloads",      _run_workloads,     "mirror"),
    ],
    "results": [
        step("reference:results",    _results, "reference"),
        step("mirror:results", _results, "mirror"),
    ],
}
