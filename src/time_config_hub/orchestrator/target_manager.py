# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Target Manager

Resolves topology-based DUT roles and registers remote targets with
system_controller for SSH access.

These are pure data-transformation and infrastructure-setup functions
with no dependency on the Orchestrator class; extracted here to keep
orchestrator.py focused on coordination logic.
"""

import logging
from typing import Callable

import time_config_hub.utils.system_controller as sc
from time_config_hub.utils.common import TchStatusCode

from .models import (
    DeploymentTopologyType,
    OrchestratorConfig,
    Target,
)

__all__ = ["resolve_targets", "register_targets"]

logger = logging.getLogger("orchestrator.target_manager")


def resolve_targets(config: OrchestratorConfig) -> list[Target]:
    """Return the list of targets with roles assigned based on topology.

    SINGLE_LOCAL → 1 target  (role=None)
    B2B          → 2 targets (1 talker + 1 listener)
    MULTI_DUT    → N targets (1 talker + N-1 listeners)

    :param OrchestratorConfig config: The orchestration configuration.
    :return: Shallow copy of targets with roles assigned.
    :rtype: list[Target]
    :raises ValueError: If the target count is insufficient for the topology.
    """
    topo = config.topology_type
    targets = list(config.targets)          # shallow copy to avoid mutating input

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


def register_targets(targets: list[Target], log: Callable[[str], None]) -> None:
    """Register remote targets with system_controller for SSH access.

    Skips local targets (ssh_user is None).  Raises on failure so the
    orchestration aborts before any stage runs.

    :param list[Target] targets: Targets to register.
    :param Callable[[str], None] log: Stamped-log callback (e.g. ``Orchestrator._log``).
    :raises RuntimeError: If SSH registration fails for any remote target.
    """
    for target in targets:
        # Local targets do not require registration
        if target.sc_target_id is None:
            log(f"Target '{target.id}' is local — skipping registration")
            continue

        # Check if already registered to avoid unnecessary SSH attempts
        if sc.is_registered(target.sc_target_id):
            log(f"Target '{target.sc_target_id}' already registered")
            continue

        # Key-based auth (ssh_key_path) is not yet forwarded to sc.register.
        # Until system_controller.register() gains key_path support, password is required.
        if target.ssh_password is None:
            raise RuntimeError(
                f"Target '{target.id}': ssh_password is required for automated SSH registration. "
                "Key-based registration (ssh_key_path) is not yet supported."
            )

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
        log(f"Registered target '{target.sc_target_id}'")
