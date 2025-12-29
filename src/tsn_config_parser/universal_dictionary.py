"""
Universal Dictionary Helpers
============================

Lightweight helpers for recursively searching nested dict/list structures.
Primarily used by the parsers to find values across parsed TSN configuration
documents.
"""

from typing import List, Any


class UniversalDictionary:
    """Base class for dictionary helpers.

    :param documents: Parsed configuration documents to operate on
    :type documents: List[dict]
    """

    def __init__(self, documents: List[dict]):
        self.documents = documents

    def find_all_by_key(self, node: Any, key: str) -> List[Any]:
        """Recursively find all values associated with a key.

        :param node: The dict or list to search recursively
        :type node: Any
        :param key: The key to match within nested structures
        :type key: str
        :return: All values associated with ``key`` found within ``node``
        :rtype: List[Any]
        """
        found = []
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key:
                    found.append(v)
                found.extend(self.find_all_by_key(v, key))
        elif isinstance(node, list):
            for item in node:
                found.extend(self.find_all_by_key(item, key))
        return found
