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
__license__ = "BSD"

from .config_reader import ConfigReader
from .core import TIMEConfigHub

__all__ = [
    "TIMEConfigHub",
    "ConfigReader",
]
