# File: yaml_parser.py
"""
YAML Parser with Helpers

This parser handles YAML files with multiple documents.
It provides helper functions similar to XMLParser/JSONParser.

Example usage
-------------
>>> parser = YAMLParser()
>>> docs = parser.parse("config.yaml")
>>> if parser.has_chronos_domain():
...     print("✅ chronos-domain found")
... else:
...     print("❌ chronos-domain not found")
"""

import yaml
from typing import Any, Dict, List


class YAMLParser:
    """
    YAML file parser with helper methods to check for chronos-domain
    and find values by key.
    """

    def __init__(self) -> None:
        self.documents: List[Dict[str, Any]] = []

    def parse(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Parse a YAML file into multiple documents if present.

        :param file_path: Path to YAML file
        :return: List of parsed YAML documents (dicts)
        """
        self.documents = []

        with open(file_path, "r", encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
            for doc in docs:
                if doc is not None:
                    self.documents.append(doc)

        return self.documents

    def refresh(self, file_path: str) -> None:
        """Re-parse the YAML file."""
        self.parse(file_path)

    def has_chronos_domain(self) -> bool:
        """Check if any document contains 'chronos-domain'."""
        for doc in self.documents:
            if self._contains_chronos(doc):
                return True
        return False

    def _contains_chronos(self, node: Any) -> bool:
        """Recursive helper to search for 'chronos-domain'."""
        if isinstance(node, dict):
            for k, v in node.items():
                if (
                    "chronos-domain" in str(k).lower()
                    or "chronos-domain" in str(v).lower()
                ):
                    return True
                if self._contains_chronos(v):
                    return True
        elif isinstance(node, list):
            return any(self._contains_chronos(item) for item in node)
        return False

    def find_all_by_key(self, key: str) -> List[Any]:
        """
        Find all values matching a key across all documents.

        :param key: Key to search for
        :return: List of values
        """
        results: List[Any] = []

        def _recursive_search(node: Any):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == key:
                        results.append(v)
                    _recursive_search(v)
            elif isinstance(node, list):
                for item in node:
                    _recursive_search(item)

        for doc in self.documents:
            _recursive_search(doc)

        return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python yaml_parser.py <file-path>")
        sys.exit(1)

    file_path = sys.argv[1]
    parser = YAMLParser()
    docs = parser.parse(file_path)

    print(f"Parsed {len(docs)} YAML document(s).")
    print("Contains chronos-domain?", parser.has_chronos_domain())

    # Example: find all 'name' keys
    names = parser.find_all_by_key("name")
    print("All 'name' keys found:", names)
