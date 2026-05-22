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
