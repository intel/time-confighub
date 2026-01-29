# File: universal_parser.py
"""
XML and JSON Parser using libyang for YANG-modeled configuration data.
"""

import io
import json
import os
import sys
import xml.etree.ElementTree as StdET
from typing import Any, Dict, List, Optional, Union

import defusedxml.ElementTree as SafeET
import libyang

from tsn_config_parser.GE_dictionary import GE_Dictionary
from yang_modules import DEFAULT_YANG_DIR, load_yang_module


class UniversalParser:
    """Parser that leverages libyang to parse and validate YANG-modeled data (XML/JSON)."""

    def __init__(self, search_path: Optional[str] = None):
        """Initialize the libyang context.

        :param str search_path: Optional path to YANG modules. Defaults to DEFAULT_YANG_DIR.
        """
        if search_path is None:
            search_path = DEFAULT_YANG_DIR

        # Initialize context with search path for automatic dependency resolution
        self.ctx = libyang.Context(search_path)
        self.documents: List[Dict[str, Any]] = []

    def _extract_required_modules(self, fpath: str, ftype: str) -> List[str]:
        """Scan the file to identify potential YANG module names.

        For XML, it extracts module names from namespace URIs (the last component
        of the colon-delimited string). For JSON, it extracts module prefixes
        from top-level keys (RFC 7951 format).

        :param str fpath: The path to the file to scan
        :param str ftype: The type of file ('xml' or 'json')
        :return: A list of discovered module names
        :rtype: List[str]
        """
        req_modules = set()
        ftype = ftype.lower()

        if ftype == "xml":
            try:
                # Wrap in dummy root to handle siblings, similar to _xml_multi_root_handler
                with open(fpath, "rb") as f:
                    raw_content = f.read()
                wrapped = b"<root>" + raw_content + b"</root>"
                for _, (_, uri) in SafeET.iterparse(
                    io.BytesIO(wrapped), events=("start-ns",)
                ):
                    # Standard YANG namespaces often end with the module name
                    # e.g., urn:ietf:params:xml:ns:yang:ietf-interfaces
                    module = uri.split(":")[-1]
                    req_modules.add(module)
            except SafeET.ParseError:
                pass
        elif ftype == "json":
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                def _walk_json(node: Any) -> None:
                    """Recursively find module prefixes in keys and identityrefs."""
                    keywords = ["ietf", "ieee", "iana"]
                    if isinstance(node, dict):
                        for k, v in node.items():
                            if isinstance(k, str) and ":" in k:
                                prefix = k.split(":")[0]
                                if any(kw in prefix.lower() for kw in keywords):
                                    req_modules.add(prefix)
                            _walk_json(v)
                    elif isinstance(node, list):
                        for item in node:
                            _walk_json(item)
                    elif isinstance(node, str) and ":" in node:
                        # Capture identityrefs like 'iana-if-type:ethernetCsmacd'
                        prefix = node.split(":")[0]
                        if any(kw in prefix.lower() for kw in keywords):
                            req_modules.add(prefix)

                _walk_json(data)
            except json.JSONDecodeError:
                pass

        return list(req_modules)

    def _json_multi_root_handler(self, fpath: str) -> List[str]:
        """Extract top-level JSON config_blocks.

        If the file contains a JSON array of objects, each object is treated
        as a separate config_block for parsing.

        :param str fpath: The path to the JSON file to split
        :return: A list of JSON strings for each top-level config_block
        :rtype: List[str]
        :raises FileNotFoundError: If the file does not exist
        """
        if not os.path.exists(fpath):
            raise FileNotFoundError(f"Configuration file not found: {fpath}")

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = json.load(f)

            if isinstance(content, list):
                return [json.dumps(item) for item in content]
            return [json.dumps(content)]
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to decode JSON file: {e}") from e

    def _xml_multi_root_handler(self, fpath: str) -> List[str]:
        """Extract top-level XML config_blocks and preserve namespaces for fragments.

        This method handles multi-root XML files by wrapping them in a temporary
        parent and re-applying all document namespaces to each fragment. This
        is necessary for libyang to resolve identityrefs in text nodes.

        :param str fpath: The path to the XML file to split
        :return: A list of XML strings for each top-level config_block
        :rtype: List[str]
        :raises FileNotFoundError: If the file does not exist
        :raises libyang.LibyangError: If XML pre-processing fails
        """
        if not os.path.exists(fpath):
            raise FileNotFoundError(f"Configuration file not found: {fpath}")

        try:
            with open(fpath, "rb") as f:
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
        no_state: Union[bool, str] = "auto",
    ) -> Optional[Dict[str, Any]]:
        """Parse a single data config_block using libyang with configurable state validation.

        :param str block_content: The XML or JSON string content to parse
        :param str data_format: The format of the content ("xml" or "json")
        :param Union[bool, str] no_state: Validation mode. Use True to ignore
            mandatory state nodes, False to enforce them, or "auto" to attempt
            enforcement first.
        :return: Dictionary representation of the config_block, or None
        :rtype: Optional[Dict[str, Any]]
        :raises libyang.LibyangError: If validation fails in the selected mode
        """
        is_json = data_format.lower() == "json"
        is_auto = isinstance(no_state, str) and no_state.lower() == "auto"

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
                no_state=bool(no_state),
                json_string_datatypes=is_json,
            )

        return dnode.print_dict() if dnode else None

    def _extract_required_modules_from_block(
        self, block_content: str, ftype: str
    ) -> List[str]:
        """Extract YANG module prefixes from a single config_block string.

        :param str block_content: The raw XML/JSON block content
        :param str ftype: The content type ('xml' or 'json')
        :return: A list of discovered module prefixes
        :rtype: List[str]
        """
        req_modules = set()
        keywords = ["ietf", "ieee", "iana"]
        ftype = ftype.lower()

        if ftype == "xml":
            try:
                for _, (_, uri) in SafeET.iterparse(
                    io.BytesIO(block_content.encode("utf-8")), events=("start-ns",)
                ):
                    module = uri.split(":")[-1]
                    if any(kw in module.lower() for kw in keywords):
                        req_modules.add(module)
            except SafeET.ParseError:
                pass
        elif ftype == "json":
            try:
                data = json.loads(block_content)

                def _walk(node: Any) -> None:
                    if isinstance(node, dict):
                        for k, v in node.items():
                            if isinstance(k, str) and ":" in k:
                                prefix = k.split(":")[0]
                                if any(kw in prefix.lower() for kw in keywords):
                                    req_modules.add(prefix)
                            _walk(v)
                    elif isinstance(node, list):
                        for item in node:
                            _walk(item)
                    elif isinstance(node, str) and ":" in node:
                        prefix = node.split(":")[0]
                        if any(kw in prefix.lower() for kw in keywords):
                            req_modules.add(prefix)

                _walk(data)
            except json.JSONDecodeError:
                pass

        return list(req_modules)

    def parse(
        self,
        fpath: str,
        ftype: str = "xml",
        no_state: Union[bool, str] = "auto",
    ) -> List[Dict[str, Any]]:
        """Parse a configuration file into a list of dictionaries using libyang.

        This method now splits the file into config_blocks first, then detects
        and loads required YANG modules from those blocks before validation.

        :param str fpath: The path to the file to parse
        :param str ftype: The type of file to parse ("xml" or "json")
        :param Union[bool, str] no_state: Validation mode. Use True to ignore
            mandatory state nodes, False to enforce them, or "auto" to attempt
            enforcement first.
        :return: A list containing the parsed dictionary representation
        :rtype: List[Dict[str, Any]]
        :raises FileNotFoundError: If the fpath does not exist
        :raises libyang.LibyangError: If any config_block fails validation
        :raises ValueError: If an unsupported ftype is provided
        """
        self.documents = []
        ftype = ftype.lower()

        # Split multi-root files into individual config_blocks first
        if ftype == "xml":
            config_blocks = self._xml_multi_root_handler(fpath)
        elif ftype == "json":
            config_blocks = self._json_multi_root_handler(fpath)
        else:
            raise ValueError(f"Unsupported file type: {ftype}")
        # Extract and load required modules from the blocks
        req_modules = set()
        for block in config_blocks:
            req_modules.update(self._extract_required_modules_from_block(block, ftype))

        for module in req_modules:
            try:
                load_yang_module(self.ctx, module)
            except libyang.LibyangError:
                continue

        # Parse each block
        for config_block in config_blocks:
            try:
                parsed_doc = self._parse_libyang_block(
                    config_block, data_format=ftype, no_state=no_state
                )
                if parsed_doc:
                    self.documents.append(parsed_doc)
            except libyang.LibyangError as e:
                raise libyang.LibyangError(
                    f"Validation failed for {ftype.upper()} config_block: {e}"
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

    def refresh(self, fpath: str, ftype: str = "xml"):
        """
        Re-parse a file, refreshing the cached documents.

        :param file_path: Path to the file
        """
        return self.parse(fpath, ftype=ftype)

    def get_dictionary_helper(self):
        """
        Return a dictionary helper based on parsed documents.

        :return: GE_Dictionary if chronos-domain is found, else None
        """
        if self.has_chronos_domain():
            return GE_Dictionary(self.documents)
        return None


# -----------------------------
# CLI entry point
# -----------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python universal_parser.py <path-to-file> [xml|json]")
        sys.exit(1)

    file_path = sys.argv[1]
    # Simple check for file type from extension if not provided
    INFERRED_FILE_TYPE = "json" if file_path.endswith(".json") else "xml"
    file_type = sys.argv[2] if len(sys.argv) > 2 else INFERRED_FILE_TYPE

    parser = UniversalParser()
    try:
        docs = parser.parse(file_path, ftype=file_type)
    except libyang.LibyangError as e:
        print(f"❌ libyang Parse/Validation Error: {e}")
        sys.exit(1)

    print(f"✅ Parsed {len(docs)} document(s) from {file_path}")
    for i, doc in enumerate(docs, 1):
        print(f"\nDocument #{i}:\n{doc}")

    if parser.has_chronos_domain():
        print("\n🔍 chronos-domain detected in file!")
    else:
        print("\n❌ chronos-domain not found")
