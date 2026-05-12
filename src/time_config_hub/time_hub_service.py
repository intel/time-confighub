# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Real Time Service Facade for Time Config Hub. 

This module provides a single :class:`TimeHubService` class that serves as 
a unified facade over the independent TSN and TCC service implementations.

Example usage: 

from time_config_hub import TimeHubService

svc = TimeHubService.from_default_config()
svc.tsn.apply("/path/to/tsn.xml", dry_run=True)
svc.tcc.status()

"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .config_reader import load_app_config
from .service_interfaces import TCCServiceInterface, TSNServiceInterface
from .service_manager import ServiceManager
from .tcc_service import TCCService
from .tsn_service import TSNService

logger = logging.getLogger(__name__)


class TimeHubService:
    """
    Unified single service interface over TSN and TCC service implementations.

    :param app_config: Application configuration dictionary.
    :param tsn_service: Optional custom TSN service; defaults to
        :class:`~.tsn_service.TSNService`.
    :param tcc_service: Optional custom TCC service; defaults to
        :class:`~.tcc_service.TCCService`.
    """

    def __init__(
        self,
        app_config: Dict[str, Any],
        tsn_service: Optional[TSNServiceInterface] = None,
        tcc_service: Optional[TCCServiceInterface] = None,
    ):
        
        logger.debug("Initializing Time Config Hub Service...")
        self.app_config = app_config

        # config_dir suppose to store applied configuration backups
        self.config_dir = Path(app_config.get("General", {}).get("ConfigDirectory", ""))
        self.verbose = app_config.get("General", {}).get("Verbosity")
        self.service_manager = ServiceManager()

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self._tsn_service: TSNServiceInterface = tsn_service or TSNService(app_config)
        self._tcc_service: TCCServiceInterface = tcc_service or TCCService(app_config)

        logger.debug("TimeHubService initialised with config_dir: %s", self.config_dir)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_default_config(cls) -> "TimeHubService":
        """Create a facade using configuration loaded from default paths.

        :return: A new :class:`TimeHubService` instance.
        :rtype: TimeHubService
        """
        return cls(app_config=load_app_config())

    # ------------------------------------------------------------------
    # Typed property access (library API)
    # ------------------------------------------------------------------

    @property
    def tsn(self) -> TSNServiceInterface:
        """TSN service interface.

        :rtype: TSNServiceInterface
        """
        return self._tsn_service

    @property
    def tcc(self) -> TCCServiceInterface:
        """TCC service interface.

        :rtype: TCCServiceInterface
        """
        return self._tcc_service

    # ------------------------------------------------------------------
    # TSN convenience methods (used by CLI / watch_handler)
    # ------------------------------------------------------------------

    def apply_config(self, config_file: str, dry_run: bool = False) -> None:
        """Apply TSN configuration from a file.

        :param str config_file: Path to configuration file (XML or YAML).
        :param bool dry_run: If True, show generated commands without execution.
        """
        self._tsn_service.apply(config_file, dry_run=dry_run)

    def get_status(self, interface: str) -> Dict[str, Any]:
        """Return current TSN configuration status for an interface.

        :param str interface: Network interface name.
        :return: Status dictionary.
        :rtype: dict
        """
        return self._tsn_service.status(interface=interface)

    def reset_config(self, interface: str) -> bool:
        """Reset TSN configuration to defaults for an interface.

        :param str interface: Network interface name.
        :return: True on success.
        :rtype: bool
        """
        return self._tsn_service.reset(interface=interface)

    def validate_config(self, config_file: str) -> bool:
        """Validate a TSN configuration file without applying it.

        :param str config_file: Path to configuration file.
        :return: True if the file is valid.
        :rtype: bool
        """
        return self._tsn_service.validate(config_file)

    def file_event_handler(self, event_type: str, file_path: str) -> None:
        """Handle file-watcher events for TSN flows.

        :param str event_type: Event type string (e.g. ``"modified"``).
        :param str file_path: Path to the changed file.
        """
        self._tsn_service.file_event_handler(event_type, file_path)

    # ------------------------------------------------------------------
    # TCC convenience methods (used by CLI)
    # ------------------------------------------------------------------

    def apply_tcc_config(self, config_file: str, dry_run: bool = False) -> None:
        """Apply TCC configuration from a file.

        :param str config_file: Path to configuration file.
        :param bool dry_run: If True, validate without applying.
        """
        self._tcc_service.apply(config_file=config_file, dry_run=dry_run)

    def get_tcc_status(self) -> Dict[str, Any]:
        """Return current TCC configuration status.

        :return: Status dictionary.
        :rtype: dict
        """
        return self._tcc_service.status()

    def reset_tcc_config(self) -> bool:
        """Reset TCC configuration metadata to defaults.

        :return: True on success.
        :rtype: bool
        """
        return self._tcc_service.reset()

    def validate_tcc_config(self, config_file: str) -> bool:
        """Validate a TCC configuration file without applying it.

        :param str config_file: Path to configuration file.
        :return: True if the file is valid.
        :rtype: bool
        """
        return self._tcc_service.validate(config_file=config_file)
