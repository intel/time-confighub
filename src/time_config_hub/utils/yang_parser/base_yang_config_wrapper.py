# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""Base class for YANG schema-specific configuration wrappers."""

from abc import ABC
from typing import Any, ClassVar, Dict, List, Optional

import defusedxml.ElementTree as SafeET


class BaseYangConfigWrapper(ABC):
    """Abstract base for YANG schema config wrappers.

    Each subclass maps to exactly one YANG module / root element. The
    wrapper stores the raw config string and a parsed dict derived from it,
    and exposes protected helpers for traversing the nested dict structure.

    Subclass pattern::

        class MyModuleWrapper(BaseYangConfigWrapper):
            YANG_MODULE = "my-module"
            YANG_NAMESPACE = "urn:example:yang:my-module"

            def get_something(self) -> List[str]:
                ...

    :cvar YANG_MODULE: Short YANG module name (e.g. ``ietf-interfaces``).
    :cvar YANG_NAMESPACE: Full XML namespace URI for this YANG module.
    """

    YANG_MODULE: ClassVar[str] = ""
    YANG_NAMESPACE: ClassVar[str] = ""

    def __init__(
        self,
        raw_config: str,
        fmt: str = "xml",
    ) -> None:
        """Initialize the wrapper.

        The raw XML string is parsed internally into a nested dict accessible
        via :attr:`parsed_dict`.

        :param str raw_config: Raw XML string for this config block.
        :param str fmt: Config format — currently only ``"xml"`` is supported.
        """
        self._raw_config = raw_config
        self._fmt = fmt
        self._parsed_dict: Dict[str, Any] = self._xml_to_dict(raw_config)

    @staticmethod
    def _xml_to_dict(xml_str: str) -> Dict[str, Any]:
        """Parse a raw XML string into a nested dict for YANG schema traversal.

        Namespace URIs are stripped from tag names (local name only is kept).
        Multiple sibling elements sharing the same tag are coerced into a list.
        Text-only leaf elements are stored as plain strings; elements with
        neither text nor child elements are stored as empty strings.

        :param str xml_str: Raw XML string.
        :return: Nested dict representation of the XML document.
        :rtype: Dict[str, Any]
        """

        def _local(tag: str) -> str:
            return tag.split("}", 1)[1] if tag.startswith("{") else tag

        def _to_dict(elem: Any) -> Any:
            children = list(elem)
            if not children:
                return (elem.text or "").strip()
            child_dict: Dict[str, Any] = {}
            for child in children:
                tag = _local(child.tag)
                value = _to_dict(child)
                if tag in child_dict:
                    existing = child_dict[tag]
                    if isinstance(existing, list):
                        existing.append(value)
                    else:
                        child_dict[tag] = [existing, value]
                else:
                    child_dict[tag] = value
            return child_dict

        root = SafeET.fromstring(xml_str)
        return {_local(root.tag): _to_dict(root)}

    @property
    def parsed_dict(self) -> Dict[str, Any]:
        """Return the parsed dictionary for this config block.

        :return: Parsed configuration dictionary derived from the raw XML.
        :rtype: Dict[str, Any]
        """
        return self._parsed_dict

    @property
    def raw_config(self) -> str:
        """Return the raw config string for this block.

        :return: Raw XML or JSON string.
        :rtype: str
        """
        return self._raw_config

    @property
    def fmt(self) -> str:
        """Return the config format (``"xml"`` or ``"json"``).

        :return: Format string.
        :rtype: str
        """
        return self._fmt

    def _find_key(self, node: Any, key: str) -> Optional[Any]:
        """Recursively find the **first** occurrence of *key* in *node*.

        :param node: dict or list to search.
        :param str key: Key to locate.
        :return: First value found, or ``None`` if not present.
        """
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key:
                    return v
                found = self._find_key(v, key)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = self._find_key(item, key)
                if found is not None:
                    return found
        return None

    def _find_all_keys(self, node: Any, key: str) -> List[Any]:
        """Recursively find **all** occurrences of *key* in *node*.

        :param node: dict or list to search.
        :param str key: Key to locate.
        :return: List of all values found (empty list if none).
        :rtype: List[Any]
        """
        results: List[Any] = []
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key:
                    results.append(v)
                results.extend(self._find_all_keys(v, key))
        elif isinstance(node, list):
            for item in node:
                results.extend(self._find_all_keys(item, key))
        return results


class GenericYangConfigWrapper(BaseYangConfigWrapper):
    """Fallback wrapper for YANG modules without a dedicated subclass.

    Provides access to the raw config and parsed dict via the base-class
    properties and helper methods, but exposes no domain-specific API.
    Used by :class:`~time_config_hub.utils.yang_parser.universal_parser.UniversalParser`
    when no matching wrapper is found in the registry for a parsed block.
    """
