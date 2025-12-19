# File: universal_parser.py
"""
Universal Parser

Delegates parsing of files to either XMLParser or YAMLParser based on file extension.
Provides unified helpers (e.g., has_chronos_domain, find_value) that work regardless of format,
with caching to avoid reparsing unless explicitly refreshed.

Example usage:
    >>> parser = UniversalParser()
    >>> configs = parser.parse("config.yaml")
    >>> configs = parser.parse("config.xml")

Command-line usage:
    python universal_parser.py path/to/file.yaml
    python universal_parser.py path/to/file.xml

Dependencies:
    pip install pyyaml
"""

import json
import os
import sys

# from json_parser import JSONParser
from .GE_dictionary import GE_Dictionary
from .xml_parser import XMLParser
from .yaml_parser import YAMLParser


class UniversalParser:
    """
    Universal file parser that automatically detects and parses multiple file formats.

    Supports:
      - XML (.xml)
      - YAML (.yaml, .yml)
      - JSON (.json)

    Delegates parsing to the correct specialized parser based on file extension.
    """

    def __init__(self):
        self.parsers = {
            ".xml": XMLParser(),
            ".yaml": YAMLParser(),
            ".yml": YAMLParser(),
            # ".json": JSONParser(),
        }
        self.current_parser = None
        self.documents = []

    def parse(self, file_path: str):
        """
        Parse a file using the appropriate parser.

        :param file_path: Path to the file
        :return: List of parsed documents
        :raises ValueError: If file extension is not supported
        """
        _, ext = os.path.splitext(file_path.lower())
        parser = self.parsers.get(ext)
        if not parser:
            raise ValueError(f"Unsupported file extension: {ext}")

        self.current_parser = parser
        self.documents = parser.parse(file_path)
        return self.documents

    def get_parser(self):
        """
        Return the parser used for the last parsed file.

        :return: The parser instance (XMLParser, YAMLParser, JSONParser)
        """
        return self.current_parser

    def has_chronos_domain(self) -> bool:
        """
        Check if 'chronos-domain' exists in the parsed documents.

        :return: True if found, False otherwise
        """
        if self.current_parser is None:
            return False
        return self.current_parser.has_chronos_domain()

    def refresh(self, file_path: str):
        """
        Re-parse a file, refreshing the cached documents.

        :param file_path: Path to the file
        """
        return self.parse(file_path)

    def get_dictionary_helper(self):
        """
        Return a dictionary helper based on parsed documents.

        :return: GE_Dictionary if chronos-domain is found, else None
        """
        if self.has_chronos_domain():
            return GE_Dictionary(self.documents)
        return None

    def find_all_by_key(self, key: str):
        """
        Find all values for a given key across all parsed documents.

        :param key: Key to search for
        :return: List of matching values
        """
        results = []

        def _recursive_search(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == key:
                        results.append(v)
                    _recursive_search(v)
            elif isinstance(obj, list):
                for item in obj:
                    _recursive_search(item)

        for doc in self.documents:
            _recursive_search(doc)

        return results


# -----------------------------
# CLI entry point
# -----------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python universal_parser.py <path-to-file>")
        sys.exit(1)

    file_path = sys.argv[1]
    parser = UniversalParser()

    try:
        docs = parser.parse(file_path)
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    parser_type = type(parser.get_parser()).__name__
    print(f"✅ Parsed {len(docs)} document(s) from {file_path} using {parser_type}")
    print(json.dumps(docs, indent=2))
    print("Contains chronos-domain?", parser.has_chronos_domain())
