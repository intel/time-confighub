# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Protocol interfaces for Time Config Hub library services.

This module defines the base protocol interfaces for the real time services 
used by the Time Config Hub library. 

These interfaces specify the expected methods and signatures for TCC and TSN 
service implementations, enabling consistent interaction with different 
service implementations.
"""

from __future__ import annotations

from typing import Any, Dict, Protocol

from time_config_hub.infra.execution_transport import ExecutionTransport


class TSNServiceInterface(Protocol):
    """Protocol for TSN service operations."""

    def apply(self, config_file: str, dry_run: bool = False) -> None:
        """Apply TSN configuration."""

    def status(self, interface: str) -> Dict[str, Any]:
        """Get TSN configuration status."""

    def reset(self, interface: str) -> bool:
        """Reset TSN configuration."""

    def validate(self, config_file: str) -> bool:
        """Validate TSN configuration."""

    def file_event_handler(self, event_type: str, file_path: str) -> None:
        """Handle file-watcher events for TSN flows."""


class TCCServiceInterface(Protocol):
    """Protocol for TCC service operations."""

    def apply(self, config_file: str, dry_run: bool = False) -> None:
        """Apply TCC configuration."""

    def status(self) -> Dict[str, Any]:
        """Get TCC configuration status."""

    def reset(self) -> bool:
        """Reset TCC configuration."""

    def validate(self, config_file: str) -> bool:
        """Validate TCC configuration."""


# ======================================================================
# Workflow service interfaces
# ======================================================================

class PtpServiceInterface(Protocol):
    """Protocol for PTP daemon lifecycle operations."""

    def run_ptp_phase(self, transport: ExecutionTransport, role: str | None, dry_run: bool = False) -> list[str]:
        """Run the full PTP setup phase for the given role (talker or listener)."""

    def start_grandmaster(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Start ptp4l in grandmaster mode."""

    def verify_grandmaster_status(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Poll until ptp4l reports MASTER portState."""

    def start_slave(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Start ptp4l in slave mode."""

    def verify_slave_lock(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Poll until ptp4l reports SLAVE portState and offset is within threshold."""

    def start_phc2sys(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Start phc2sys to synchronise system clock from PHC."""


class TestbenchServiceInterface(Protocol):
    """Protocol for testbench application lifecycle operations."""

    def start_transmitter(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Start testbench in transmit mode."""

    def stop_transmitter(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Stop testbench transmitter process."""

    def start_receiver(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Start testbench in receive mode."""

    def stop_receiver(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Stop testbench receiver process."""

    def collect_logs(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Retrieve testbench log from the target."""


class AIWorkloadServiceInterface(Protocol):
    """Protocol for AI workload application lifecycle operations."""

    def start(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Start the AI workload."""

    def stop(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Stop the AI workload."""

    def collect_logs(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Retrieve AI workload log from the target."""


class InstallerServiceInterface(Protocol):
    """Protocol for target installation and connectivity operations."""

    def verify_connectivity(self, transport: ExecutionTransport) -> bool:
        """Check that the target is reachable."""

    def install(self, transport: ExecutionTransport, dry_run: bool = False) -> list[str]:
        """Install required packages and push configuration files."""
