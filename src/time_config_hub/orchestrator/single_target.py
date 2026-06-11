# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""Stage Implementations for Single-Target (Local) Orchestration

Each stage is a callable that receives a Target and a dry_run flag,
and returns a list of output lines.  Replace the sample logic in each
stage with real operations when ready.

Stages are registered in STAGE_REGISTRY keyed by stage_name.
This file only handles SINGLE_LOCAL topology (role=None).
Multi-target topologies (B2B, MULTI_DUT) use multi_target.py.
"""

from __future__ import annotations

import logging

from .models import ORCHESTRATION_STAGES, StageHandler, Target

__all__ = [
    "get_steps",
    "StageHandler",
    "STAGE_REGISTRY",
]

logger = logging.getLogger("orchestrator.single_target")


# ==================================================================
# DEFAULT stage implementations (role=None / local)
# ==================================================================

def _install_default(target: Target, dry_run: bool) -> list[str]:
    """Install necessary tools and dependencies on the target."""
    logger.info("[%s] >> install (dry_run=%s)", target.id, dry_run)
    output: list[str] = []
    output.append(f"Installing tools and dependencies on '{target.id}' ({target.ip_address})")

    if dry_run:
        output.append(f"[DRY RUN] Would install tools and dependencies on '{target.id}'")
        return output

    tid = target.sc_target_id

    # Verify connectivity
    result = sc.run(["echo", "connection-ok"], target_id=tid)
    if result["status_code"] != TchStatusCode.SUCCESS:
        raise RuntimeError(f"Cannot reach '{target.id}': {result['error']}")
    output.append(f"Connectivity verified on '{target.id}'")

    # TODO: Replace with real install logic
    #  - Install/verify required packages (Testbench, AI Workloads, etc.)
    #  - Validate installed versions
    #  Example:
    #    sc.run(["apt-get", "install", "-y", "package-name"], target_id=tid)
    #    sc.put_file("local/config", "/remote/path/config", target_id=tid)

    output.append(f"Installation complete on '{target.id}'")
    logger.info("[%s] << install completed", target.id)
    return output


def _apply_config_default(target: Target, dry_run: bool) -> list[str]:
    """Apply TCC and TSN configurations on the target."""
    logger.info("[%s] >> apply_config (dry_run=%s)", target.id, dry_run)
    output: list[str] = []
    output.append(f"Applying configuration on '{target.id}' ({target.ip_address})")

    if dry_run:
        output.append(f"[DRY RUN] Would apply TCC/TSN config on '{target.id}'")
        return output

    # TODO: Replace with real config logic
    #  - Apply TCC config XML file using TCH config library 
    #  - Apply TSN config XML file using TCH config library
    #  - Verify applied configuration matches expected state
    output.append(f"Configuration applied on '{target.id}'")
    logger.info("[%s] << apply_config completed", target.id)
    return output


def _run_default(target: Target, dry_run: bool) -> list[str]:
    """Execute the defined workflow (e.g. start TCC, run test workloads)."""
    logger.info("[%s] >> run (dry_run=%s)", target.id, dry_run)
    output: list[str] = []
    output.append(f"Executing workflow on '{target.id}' ({target.ip_address})")

    if dry_run:
        output.append(f"[DRY RUN] Would execute workflow on '{target.id}'")
        return output

    # TODO: Replace with real run logic
    #  - Start AI workloads and testbench applications
    #  - Monitor execution progress
    output.append(f"Workflow executed on '{target.id}'")
    logger.info("[%s] << run completed", target.id)
    return output


def _results_default(target: Target, dry_run: bool) -> list[str]:
    """Collect results, logs, and relevant data from the target."""
    logger.info("[%s] >> results (dry_run=%s)", target.id, dry_run)
    output: list[str] = []
    output.append(f"Collecting results from '{target.id}' ({target.ip_address})")

    if dry_run:
        output.append(f"[DRY RUN] Would collect results from '{target.id}'")
        return output

    # TODO: Replace with real results collection logic
    #  - Gather logs and test output
    #  - Parse and summarize results
    #  - Store results for reporting
    output.append(f"Results collected from '{target.id}'")
    logger.info("[%s] << results completed", target.id)
    return output


# ==================================================================
# STAGE REGISTRY — map stage_name to handler function
# ==================================================================

STAGE_REGISTRY: dict[str, StageHandler] = {
    "install":      _install_default,
    "apply_config": _apply_config_default,
    "run":          _run_default,
    "results":      _results_default,
}

# Guard: ensure every stage has a handler registered
_expected: set[str] = set(ORCHESTRATION_STAGES)
_registered = set(STAGE_REGISTRY)
if _expected != _registered:
    _missing = _expected - _registered
    _extra = _registered - _expected
    raise AssertionError(
        f"STAGE_REGISTRY / ORCHESTRATION_STAGES mismatch — "
        f"missing: {sorted(_missing) or 'none'}, "
        f"extra: {sorted(_extra) or 'none'}"
    )


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
