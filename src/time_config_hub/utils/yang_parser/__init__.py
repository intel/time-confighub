# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Configuration Parser

A collection of parsers for handling real time (TCC, TSN) configuration files in multiple formats.

This package provides:

- Universal parser that auto-detects file format based on extension
- YAML parser for .yaml and .yml files with multi-document support
- XML parser for .xml files with multi-root element support
- Comprehensive test suite for all parser functionality

The parsers are designed to handle configuration files used in
real-time applications and can parse files
containing multiple configuration documents or root elements.
"""

from time_config_hub.utils.yang_parser.universal_parser import UniversalParser

__all__ = [
    "UniversalParser",
]
