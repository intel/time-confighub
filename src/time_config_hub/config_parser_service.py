# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Configuration Parser Service for Time Config Hub

This module defines the ConfigParserService class, which provides methods for 
parsing and validating real time configuration files (YAML/XML) using the UniversalParser 
from the tsn_config_parser library. 

The ConfigParserService is designed to be used by both the TSN and TCC service implementations, 
providing a shared utility for handling configuration files in a consistent manner across the Time Config Hub library.

"""

from __future__ import annotations

import logging
from typing import Any, Dict

from config_parser.common.exceptions import InvalidInputDataError, UniversalParserError
from config_parser.common.universal_parser import UniversalParser
from yang_modules import DEFAULT_YANG_DIR

from .exceptions import ConfigParseError

logger = logging.getLogger(__name__)

class ConfigParserService:
    """Parse and validate real time configuration files."""

    def __init__(self, app_config: Dict[str, Any]):
        self._app_config = app_config

    def parse_config(self, config_file: str) -> UniversalParser:
        """Parse a configuration file and return the parser.

        :param str config_file: Path to configuration file (XML or YAML)
        :return: UniversalParser instance
        :rtype: UniversalParser
        :raises ConfigParseError: If parsing fails or yields no documents
        """
        yang_dir = self._app_config.get("General", {}).get(
            "YangModuleDirectory", DEFAULT_YANG_DIR
        )
        uparser = UniversalParser(yang_dir)
        try:
            docs = uparser.parse(file_path=config_file, file_type="auto")
        except InvalidInputDataError as exc:
            raise ConfigParseError(
                f"Invalid configuration file {config_file}: {exc}"
            ) from exc
        except UniversalParserError as exc:
            raise ConfigParseError(
                f"Failed to parse configuration {config_file}: {exc}"
            ) from exc

        if not docs:
            raise ConfigParseError(
                f"No valid configuration documents found in {config_file}"
            )

        return uparser

    def validate_config(self, config_file: str) -> bool:
        """Validate a configuration file without applying it.

        :param str config_file: Path to configuration file (XML or YAML)
        :return: True if configuration is valid, False otherwise
        :rtype: bool
        """
        try:
            self.parse_config(config_file)
            logger.info(f"Configuration file {config_file} is valid.")
            return True
        
        except ConfigParseError:
            logger.error(f"Configuration file {config_file} is invalid.")
            return False

        except Exception:
            logger.exception(
                f"Unexpected error validating configuration: {config_file}"
            )
            return False
