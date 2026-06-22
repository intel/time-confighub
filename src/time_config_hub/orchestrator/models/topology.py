# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""Topology and DUT target models for TCH Orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

__all__ = [
    "DeploymentTopologyType",
    "Target",
]


class DeploymentTopologyType(str, Enum):
    """Supported deployment topology strategy types."""

    SINGLE_LOCAL = "local"       # Single local target (Self-Hosted Orchestrator)
    B2B          = "back-to-back"  # Two DUTs (Orchestrator Hosted in Talker)
    MULTI_DUT    = "multi-dut"   # Dedicated Hosted Orchestrator, Many DUTs


@dataclass
class Target:
    """DUT target connection information for orchestration."""

    id: str                             # Unique identifier for the target
    ip_address: str                     # IP address of the target. For local mode, it can be 127.0.0.1
    role: Optional[str] = None          # Internally assigned based on topology detection (e.g., "talker", "listener"). For SINGLE_LOCAL, role will be None.
    ssh_user: Optional[str] = None      # SSH username for remote connection (None for local mode)
    ssh_password: Optional[str] = None  # SSH password for remote connection (if not using key-based auth)
    # TODO: ssh_key_path is not yet forwarded to sc.register (which only supports password-based
    # key exchange). Wire this up once system_controller.register() gains key_path support.
    ssh_key_path: Optional[str] = None  # Path to SSH private key for authentication (if not using password)
    ssh_port: int = 22                  # SSH port (default is 22)

    # Per-target PTP configuration.
    # These values are specific to each DUT: talker and listener are different
    # physical machines that may have different NIC names and different ptp4l
    # config files on-disk.  When None, TimeHubService falls back to the
    # [PTP] section of app_config, then to compiled-in defaults.
    ptp_interface: Optional[str] = None     # NIC used for ptp4l / phc2sys (e.g. "enp3s0")
    ptp_gm_config: Optional[str] = None     # Path to ptp4l grandmaster config on this DUT
    ptp_slave_config: Optional[str] = None  # Path to ptp4l slave config on this DUT

    @property
    def sc_target_id(self) -> Optional[str]:
        """Return the system_controller identity string, or None for local targets."""
        if self.ssh_user is None:
            return None
        return f"{self.ssh_user}@{self.ip_address}"

    def __post_init__(self):
        # SSH credential validation only applies when ssh_user is set (remote targets)
        if self.ssh_user:
            if self.ssh_password and self.ssh_key_path:
                raise ValueError(
                    f"Target '{self.id}': ssh_password and ssh_key_path are mutually exclusive. "
                    "Provide one, not both."
                )
            if not self.ssh_password and not self.ssh_key_path:
                raise ValueError(
                    f"Target '{self.id}': one of ssh_password or ssh_key_path must be provided."
                )
