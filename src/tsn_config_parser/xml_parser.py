# File: xml_parser.py
"""
XML Parser with namespace stripping and helpers.

Usage:
    python xml_parser.py path/to/file.xml
"""

import xml.etree.ElementTree as ET
from typing import Any, Dict, List
import sys


class XMLParser:
    """XML parser that handles multiple root elements and strips namespaces."""

    def __init__(self):
        self.documents: List[Dict[str, Any]] = []

    def parse(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse an XML file into multiple documents."""
        self.documents = []

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Wrap multiple roots
        wrapped = f"<root>{content}</root>"
        root = ET.fromstring(wrapped)

        for child in root:
            self.documents.append(self._element_to_dict(child))

        return self.documents

    def _strip_namespace(self, tag: str) -> str:
        """Remove XML namespace from a tag."""
        return tag.split("}")[-1] if "}" in tag else tag

    def _element_to_dict(self, element: ET.Element) -> Dict[str, Any]:
        """Convert an XML element to a dictionary with namespace stripped."""
        node: Dict[str, Any] = {}
        tag = self._strip_namespace(element.tag)

        # Attributes
        if element.attrib:
            node.update({f"@{k}": v for k, v in element.attrib.items()})

        # Children
        children = list(element)
        if children:
            for child in children:
                child_dict = self._element_to_dict(child)
                child_tag = list(child_dict.keys())[0]
                child_value = child_dict[child_tag]

                if child_tag in node:
                    if not isinstance(node[child_tag], list):
                        node[child_tag] = [node[child_tag]]
                    node[child_tag].append(child_value)
                else:
                    node[child_tag] = child_value

        # Text
        text = element.text.strip() if element.text else ""
        if text:
            if children or element.attrib:
                node["#text"] = text
            else:
                return {tag: text}

        return {tag: node} if node else {tag: None}

    def has_chronos_domain(self) -> bool:
        """Check if any document contains 'chronos-domain'."""
        return any(self._contains_chronos(doc) for doc in self.documents)

    def _contains_chronos(self, node: Any) -> bool:
        """Recursive search for 'chronos-domain'."""
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


# -----------------------------
# CLI entry point
# -----------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python xml_parser.py <path-to-xml-file>")
        sys.exit(1)

    file_path = sys.argv[1]
    parser = XMLParser()
    try:
        docs = parser.parse(file_path)
    except ET.ParseError as e:
        print(f"❌ XML Parse Error: {e}")
        sys.exit(1)

    print(f"✅ Parsed {len(docs)} document(s) from {file_path}")
    for i, doc in enumerate(docs, 1):
        print(f"\nDocument #{i}:\n{doc}")

    if parser.has_chronos_domain():
        print("\n🔍 chronos-domain detected in file!")
    else:
        print("\n❌ chronos-domain not found")
