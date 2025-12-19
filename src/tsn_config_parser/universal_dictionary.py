# File: universal_dictionary.py
from typing import List, Any


class UniversalDictionary:
    """
    Base class for dictionary helpers.
    """

    def __init__(self, documents: List[dict]):
        self.documents = documents

    def find_all_by_key(self, node: Any, key: str) -> List[Any]:
        """
        Recursively find all values associated with a key in nested dict/list.

        :param node: dict or list to search
        :param key: key to find
        :return: list of values
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
