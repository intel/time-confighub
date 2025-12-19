"""
TSN Configuration Parser

A collection of parsers for handling TSN configuration files in multiple formats.

This package provides:

- Universal parser that auto-detects file format based on extension
- YAML parser for .yaml and .yml files with multi-document support
- XML parser for .xml files with multi-root element support
- Comprehensive test suite for all parser functionality

The parsers are designed to handle configuration files used in
Time-Sensitive Networking (TSN) applications and can parse files
containing multiple configuration documents or root elements.
"""

from .universal_parser import UniversalParser
from .yaml_parser import YAMLParser
from .xml_parser import XMLParser

__all__ = [
    "UniversalParser",
    "YAMLParser",
    "XMLParser",
]
