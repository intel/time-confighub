# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Time Config TCC Service API Implementation 

This service class provides methods to apply, validate, reset and 
check the status of Intel TCC configurations. 

It uses the ConfigParserService for parsing configuration files and 
the TCCStateStore for tracking applied configurations and status. 
The TCCService implements the TCCServiceInterface protocol, allowing 
it to be used interchangeably with other implementations if needed.

"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from .config_parser_service import ConfigParserService
from .exceptions import ConfigParseError, TCCConfigError
from .service_interfaces import TCCServiceInterface
from .tcc_state_store import TCCStateStore


logger = logging.getLogger(__name__)


class TCCService(TCCServiceInterface):
    """Default TCC service implementation."""

    def __init__(self, app_config: Dict[str, Any]):
        self._app_config = app_config
        self.config_dir = Path(app_config.get("General", {}).get("ConfigDirectory"))
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._parser = ConfigParserService(app_config)
        self._state_store = TCCStateStore(self.config_dir)

    def apply(self, config_file: str, dry_run: bool = False) -> None:
        try:
            logger.info(f"Applying TCC configuration from {config_file}")
            self._parser.parse_config(config_file)

            if dry_run:
                logger.info("Dry-run enabled; TCC configuration was validated only.")
                return

            self._state_store.save_applied_config(config_file)
            logger.info(f"TCC configuration applied successfully: {config_file}")

        except ConfigParseError as exc:
            logger.error(f"TCC configuration file {config_file} is invalid: {exc}")
            raise TCCConfigError("TCC configuration file is invalid") from exc

        except Exception as exc:
            logger.exception("Failed to apply TCC configuration")
            raise TCCConfigError("Failed to apply TCC configuration") from exc

    def status(self) -> Dict[str, Any]:
        return self._state_store.load_status()

    def reset(self) -> bool:
        return self._state_store.reset()

    def validate(self, config_file: str) -> bool:
        try:
            self._parser.parse_config(config_file)
            logger.info(f"TCC configuration file {config_file} is valid.")
            return True
        except ConfigParseError as exc:
            logger.error(f"TCC configuration file {config_file} is invalid: {exc}")
            return False
        except Exception:
            logger.exception(
                f"Unexpected error validating TCC configuration: {config_file}"
            )
            return False
