# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Time Config Hub

A Python package for managing Time-Sensitive Networking (TSN) configurations
on Intel TSN-capable hardware platforms.

This package provides:

- Configuration file reading and writing (YAML/XML)
- TSN traffic control configuration management
- Command-line interface for configuration operations
- Daemon service for automatic configuration monitoring
- Error handling and validation
"""

__version__ = "1.0.0"
__author__ = "Intel"
__license__ = "BSD-3-Clause"

from .config.config_reader import ConfigReader
from .orchestrator.time_hub_service import TimeHubService
from .services.common.service_interfaces import TCCServiceInterface, TSNServiceInterface
from .services.tcc.service import TCCService
from .services.tsn.service import TSNService

__all__ = [
    "ConfigReader",
    "TimeHubService",
    "TSNServiceInterface",
    "TCCServiceInterface",
    "TSNService",
    "TCCService",
]
