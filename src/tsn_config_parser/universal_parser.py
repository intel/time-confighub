# File: universal_parser.py
"""
XML and JSON Parser using libyang for YANG-modeled configuration data.
"""

import io
import json
import os
import xml.etree.ElementTree as StdET
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import defusedxml.ElementTree as SafeET
import libyang

from tsn_config_parser.GE_dictionary import GE_Dictionary
from yang_modules import DEFAULT_YANG_DIR, load_yang_module


def _collect_json_prefixes(node: Any, keywords: List[str]) -> Set[str]:
    """Recursively collect and return YANG module prefixes from JSON content."""
    prefixes = set()
    keywords_lower = [kw.lower() for kw in keywords]

    if isinstance(node, dict):
        for key, value in node.items():
            # Check the key for a prefix
            if isinstance(key, str) and ":" in key:
                prefix = key.split(":")[0]
                if any(kw in prefix.lower() for kw in keywords_lower):
                    prefixes.add(prefix)

            # Recurse and merge results from values
            prefixes |= _collect_json_prefixes(value, keywords)

    elif isinstance(node, list):
        for item in node:
            # Recurse and merge results from list items
            prefixes |= _collect_json_prefixes(item, keywords)

    elif isinstance(node, str) and ":" in node:
        # Check leaf string values for prefixes
        prefix = node.split(":")[0]
        if any(kw in prefix.lower() for kw in keywords_lower):
            prefixes.add(prefix)

    return prefixes


class UniversalParser:
    """Parser that leverages libyang to parse and validate YANG-modeled data (XML/JSON)."""

    def __init__(self, yang_modules_path: Optional[str] = None):
        """Initialize the libyang context.

        :param str yang_modules_path: Optional path to YANG modules. Defaults to DEFAULT_YANG_DIR.
        """
        if yang_modules_path is None:
            yang_modules_path = DEFAULT_YANG_DIR

        # Initialize context with search path for automatic dependency resolution
        self.ctx = libyang.Context(yang_modules_path)
        self.documents: List[Dict[str, Any]] = []

    def _json_multi_root_handler(self, file_path: str) -> List[str]:
        """Extract top-level JSON config_blocks.

        If the file contains a JSON array of objects, each object is treated
        as a separate config_block for parsing.

        :param str file_path: The path to the JSON file to split
        :return: A list of JSON strings for each top-level config_block
        :rtype: List[str]
        :raises FileNotFoundError: If the file does not exist
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)

            if isinstance(content, list):
                return [json.dumps(item) for item in content]
            return [json.dumps(content)]
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to decode JSON file: {e}") from e

    def _xml_multi_root_handler(self, file_path: str) -> List[str]:
        """Extract top-level XML config_blocks and preserve namespaces for fragments.

        This method handles multi-root XML files by wrapping them in a temporary
        parent and re-applying all document namespaces to each fragment. This
        is necessary for libyang to resolve identityrefs in text nodes.

        :param str file_path: The path to the XML file to split
        :return: A list of XML strings for each top-level config_block
        :rtype: List[str]
        :raises FileNotFoundError: If the file does not exist
        :raises libyang.LibyangError: If XML pre-processing fails
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        try:
            with open(file_path, "rb") as f:
                raw_content = f.read()

            # Wrap fragment in a dummy root to handle multiple top-level siblings
            wrapped_content = b"<root>" + raw_content + b"</root>"

            # Collect all namespaces from the wrapped document
            namespaces = {}
            for _, elem in SafeET.iterparse(
                io.BytesIO(wrapped_content), events=("start-ns",)
            ):
                prefix, uri = elem
                namespaces[prefix or "xmlns"] = uri

            # Parse the now-valid XML structure
            root_element = SafeET.fromstring(wrapped_content)

            config_blocks = []
            for child in root_element:
                # Re-inject namespaces into child
                for prefix, uri in namespaces.items():
                    attr = prefix if prefix == "xmlns" else f"xmlns:{prefix}"
                    if attr not in child.attrib:
                        child.set(attr, uri)

                # Format for readability
                StdET.indent(child, space="    ", level=0)
                config_blocks.append(SafeET.tostring(child, encoding="unicode"))

            return config_blocks
        except Exception as e:
            raise libyang.LibyangError(f"Failed to pre-process XML fragment: {e}")

    def _parse_libyang_block(
        self,
        block_content: str,
        data_format: str = "xml",
        no_state: str = "auto",
    ) -> Optional[Dict[str, Any]]:
        """Parse a single data config_block using libyang with configurable state validation.

        :param str block_content: The XML or JSON string content to parse
        :param str data_format: The format of the content ("xml" or "json")
        :param str no_state: Validation mode. Use
            - "ignore" to ignore mandatory state nodes
            - "enforce" to enforce them
            - "auto" to attempt enforcement first.
        :return: Dictionary representation of the config_block, or None
        :rtype: Optional[Dict[str, Any]]
        :raises libyang.LibyangError: If validation fails in the selected mode
        """
        is_json = data_format.lower() == "json"
        is_auto = isinstance(no_state, str) and no_state.lower() == "auto"

        if no_state not in ["auto", "ignore", "enforce"]:
            raise ValueError(
                f"Invalid no_state value: {no_state}. Must be 'auto', 'ignore', or 'enforce'."
            )

        no_state_bool = False  # standard enforcement by default

        if no_state == "ignore":
            no_state_bool = True
        elif no_state == "enforce":
            no_state_bool = False

        if is_auto:
            try:
                # Attempt 1: standard parsing (no_state=False)
                dnode = self.ctx.parse_data_mem(
                    block_content,
                    data_format,
                    validate_present=True,
                    no_state=False,
                    json_string_datatypes=is_json,
                )
            except libyang.LibyangError:
                # Attempt 2: retry with no_state=True to ignore mandatory state nodes
                dnode = self.ctx.parse_data_mem(
                    block_content,
                    data_format,
                    validate_present=True,
                    no_state=True,
                    json_string_datatypes=is_json,
                )
        else:
            dnode = self.ctx.parse_data_mem(
                block_content,
                data_format,
                validate_present=True,
                no_state=no_state_bool,
                json_string_datatypes=is_json,
            )

        return dnode.print_dict() if dnode else None

    def _extract_required_modules_from_block(
        self, block_content: str, file_type: str
    ) -> List[str]:
        """Extract YANG module prefixes from a single config_block string.

        :param str block_content: The raw XML/JSON block content
        :param str file_type: The content type ('xml' or 'json')
        :return: A list of discovered module prefixes
        :rtype: List[str]
        """
        req_modules = set()
        keywords = ["ietf", "ieee", "iana"]
        file_type = file_type.lower()

        if file_type == "xml":
            try:
                for _, (_, uri) in SafeET.iterparse(
                    io.BytesIO(block_content.encode("utf-8")), events=("start-ns",)
                ):
                    module = uri.split(":")[-1]
                    if any(kw in module.lower() for kw in keywords):
                        req_modules.add(module)
            except SafeET.ParseError:
                pass
        elif file_type == "json":
            try:
                data = json.loads(block_content)
                req_modules = _collect_json_prefixes(data, keywords)
            except json.JSONDecodeError:
                pass

        return list(req_modules)

    def parse(
        self,
        file_path: str,
        file_type: str = "auto",
        no_state: str = "auto",
    ) -> List[Dict[str, Any]]:
        """Parse a configuration file into a list of dictionaries using libyang.

        This method now splits the file into config_blocks first, then detects
        and loads required YANG modules from those blocks before validation.

        :param str file_path: The path to the file to parse
        :param str file_type: The type of file to parse ("xml", "json", or "auto")
        :param str no_state: Validation mode. Use
            - "ignore" to ignore mandatory state nodes
            - "enforce" to enforce them
            - "auto" to attempt enforcement first.
        :return: A list containing the parsed dictionary representation
        :rtype: List[Dict[str, Any]]
        :raises FileNotFoundError: If the file_path does not exist
        :raises libyang.LibyangError: If any config_block fails validation
        :raises ValueError: If an unsupported file_type is provided
        """
        self.documents = []
        file_type = (file_type or "auto").lower()

        # Determine file type based on extension if set to auto
        if file_type == "auto":
            suffix = Path(file_path).suffix.lower()
            file_type = "json" if suffix == ".json" else "xml"

        # Split multi-root files into individual config_blocks first
        if file_type == "xml":
            config_blocks = self._xml_multi_root_handler(file_path)
        elif file_type == "json":
            config_blocks = self._json_multi_root_handler(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
        # Extract and load required modules from the blocks
        req_modules = set()
        for block in config_blocks:
            req_modules.update(
                self._extract_required_modules_from_block(block, file_type)
            )

        for module in req_modules:
            try:
                load_yang_module(self.ctx, module)
            except libyang.LibyangError:
                continue

        # Parse each block
        for config_block in config_blocks:
            try:
                parsed_doc = self._parse_libyang_block(
                    config_block, data_format=file_type, no_state=no_state
                )
                if parsed_doc:
                    self.documents.append(parsed_doc)
            except libyang.LibyangError as e:
                raise libyang.LibyangError(
                    f"Validation failed for {file_type.upper()} config_block: {e}"
                )

        return self.documents

    def has_chronos_domain(self) -> bool:
        """Check if any document contains 'chronos-domain'.

        :return: True if 'chronos-domain' is found in keys or values, False otherwise
        :rtype: bool
        """
        return any(self._contains_chronos(doc) for doc in self.documents)

    def _contains_chronos(self, node: Any) -> bool:
        """Recursive search for 'chronos-domain' within a data structure.

        :param Any node: The current dictionary or list node to search
        :return: True if the search term is found
        :rtype: bool
        """
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

    def refresh(self, file_path: str, file_type: str = "xml"):
        """
        Re-parse a file, refreshing the cached documents.

        :param file_path: Path to the file
        """
        return self.parse(file_path, file_type=file_type)

    def get_dictionary_helper(self):
        """
        Return a dictionary helper based on parsed documents.

        :return: GE_Dictionary if chronos-domain is found, else None
        """
        if self.has_chronos_domain():
            return GE_Dictionary(self.documents)
        return None
