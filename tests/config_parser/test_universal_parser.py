"""Unit tests for universal_parser using a stubbed libyang context."""

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional

import pytest


def _make_libyang_stub():
    """Create a minimal libyang stub with controllable behaviors."""

    class DummyLibyangError(Exception):
        """Replacement for libyang.LibyangError."""

        pass

    class DummyModule:
        """Stub module that tracks its name."""

        def __init__(self, name):
            """Store the module name."""
            self.name = name

        def feature_enable_all(self):
            """No-op feature enablement for compatibility."""
            return None

    class DummyDNode:
        """Stub data node returning provided mapping."""

        def __init__(self, data):
            """Persist parsed data for retrieval."""
            self.data = data

        def print_dict(self):
            """Return stored data similar to libyang output."""
            return self.data

    class DummyContext:
        """Stub libyang context supporting parse and load hooks."""

        def __init__(self, search_path):
            """Initialize the context with search path and hook storage."""
            self.search_path = search_path
            self.loaded_modules = []
            self.parse_data_mem_behavior: Optional[Callable[..., Any]] = None

        def parse_data_mem(self, *args, **kwargs):
            """Delegate to custom behavior when callable, else return default."""
            behavior = self.parse_data_mem_behavior
            if callable(behavior):
                return behavior(*args, **kwargs)
            return DummyDNode({"default": True})

        def load_module(self, module_name):
            """Record requested modules and return a stub module."""
            self.loaded_modules.append(module_name)
            return DummyModule(module_name)

    return SimpleNamespace(
        Context=DummyContext,
        LibyangError=DummyLibyangError,
        DummyDNode=DummyDNode,
        Module=DummyModule,
    )


@pytest.fixture(autouse=True)
def add_src_to_path():
    """Ensure src/ is on sys.path for imports."""
    repo_root = Path(__file__).resolve().parents[2]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    yield


@pytest.fixture
def up_module(monkeypatch):
    """Load universal_parser with libyang monkeypatched to the stub."""
    stub = _make_libyang_stub()
    monkeypatch.setitem(sys.modules, "libyang", stub)
    import yang_modules

    importlib.reload(yang_modules)
    import tsn_config_parser.universal_parser as universal_parser

    importlib.reload(universal_parser)
    return universal_parser


@pytest.fixture
def parser(up_module):
    """Return a UniversalParser instance using the stubbed context."""
    return up_module.UniversalParser()


def test_init_uses_default_search_path(up_module):
    """UniversalParser defaults to the configured YANG directory."""
    parser = up_module.UniversalParser()

    assert parser.ctx.search_path == up_module.DEFAULT_YANG_DIR
    assert parser.documents == []


def test_init_accepts_custom_search_path(up_module):
    """Custom search path is respected when provided."""
    custom_path = "/tmp/custom_yang"
    parser = up_module.UniversalParser(yang_modules_path=custom_path)

    assert parser.ctx.search_path == custom_path


def test_json_multi_root_handler_splits_array(tmp_path, up_module):
    """JSON arrays are split into separate block strings."""
    data = [{"a": 1}, {"b": 2}]
    json_file = tmp_path / "array.json"
    json_file.write_text(json.dumps(data), encoding="utf-8")

    parser = up_module.UniversalParser()
    blocks = parser._json_multi_root_handler(str(json_file))

    assert len(blocks) == 2
    assert json.loads(blocks[0]) == {"a": 1}


def test_json_multi_root_handler_missing_file_raises(up_module):
    """Missing JSON files raise FileNotFoundError."""
    parser = up_module.UniversalParser()

    with pytest.raises(FileNotFoundError):
        parser._json_multi_root_handler("/nonexistent/file.json")


def test_xml_multi_root_handler_preserves_namespaces(tmp_path, up_module):
    """Namespaces persist when splitting multi-root XML."""
    xml_content = (
        '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">'
        "<name>eth0</name></interfaces>"
        '<ianaift:if xmlns:ianaift="urn:ietf:params:xml:ns:yang:iana-if-type">'
        "<ianaift:type>ianaift:ethernetCsmacd</ianaift:type></ianaift:if>"
    )
    xml_file = tmp_path / "multi.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    parser = up_module.UniversalParser()
    blocks = parser._xml_multi_root_handler(str(xml_file))

    assert len(blocks) == 2
    assert 'xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"' in blocks[0]
    assert 'xmlns:ianaift="urn:ietf:params:xml:ns:yang:iana-if-type"' in blocks[1]


def test_xml_multi_root_handler_invalid_xml_raises(tmp_path, up_module):
    """Malformed XML surfaces as a libyang preprocessing error."""
    xml_file = tmp_path / "bad.xml"
    xml_file.write_text("<interfaces><name>eth0", encoding="utf-8")

    parser = up_module.UniversalParser()

    with pytest.raises(up_module.libyang.LibyangError):
        parser._xml_multi_root_handler(str(xml_file))


def test_parse_libyang_block_auto_recovers(monkeypatch, up_module):
    """Auto mode retries with no_state after an initial failure."""
    parser = up_module.UniversalParser()
    call_state = {"count": 0}

    def behavior(*args, **kwargs):
        call_state["count"] += 1
        if call_state["count"] == 1:
            raise up_module.libyang.LibyangError("first failure")
        return up_module.libyang.DummyDNode({"attempt": call_state["count"]})

    parser.ctx.parse_data_mem_behavior = behavior
    result = parser._parse_libyang_block("<data/>", data_format="xml", no_state="auto")

    assert result == {"attempt": 2}


def test_parse_libyang_block_propagates_failure(up_module):
    """Raise libyang errors when parsing fails consistently."""
    parser = up_module.UniversalParser()

    def always_fail(*args, **kwargs):
        raise up_module.libyang.LibyangError("boom")

    parser.ctx.parse_data_mem_behavior = always_fail

    with pytest.raises(up_module.libyang.LibyangError):
        parser._parse_libyang_block("<data/>", data_format="xml", no_state="auto")


def test_extract_required_modules_from_block_xml(up_module):
    """Extract modules from a single XML block."""
    parser = up_module.UniversalParser()
    block = (
        '<if:interfaces xmlns:if="urn:ietf:params:xml:ns:yang:ietf-interfaces">'
        "</if:interfaces>"
    )

    modules = parser._extract_required_modules_from_block(block, "xml")

    assert modules == ["ietf-interfaces"]


def test_extract_required_modules_from_block_nested_xml(up_module):
    """Capture nested namespace modules from XML content."""
    parser = up_module.UniversalParser()
    block = (
        '<if:interfaces xmlns:if="urn:ietf:params:xml:ns:yang:ietf-interfaces">'
        "<if:interface>"
        '<if:type xmlns:ianaift="urn:ietf:params:xml:ns:yang:iana-if-type">'
        "ianaift:ethernetCsmacd"
        "</if:type>"
        "</if:interface>"
        "</if:interfaces>"
    )

    modules = parser._extract_required_modules_from_block(block, "xml")

    assert set(modules) == {"ietf-interfaces", "iana-if-type"}


def test_extract_required_modules_from_block_bad_json(up_module):
    """Return empty list for malformed JSON block content."""
    parser = up_module.UniversalParser()
    modules = parser._extract_required_modules_from_block("{not-json}", "json")

    assert modules == []


def test_parse_xml_happy_path(monkeypatch, up_module):
    """Parse XML blocks, load modules, and collect documents."""
    parser = up_module.UniversalParser()
    monkeypatch.setattr(
        parser, "_xml_multi_root_handler", lambda path: ["<a/>", "<b/>"]
    )
    monkeypatch.setattr(
        parser,
        "_extract_required_modules_from_block",
        lambda block, ftype: ["good", "bad"] if "a" in block else [],
    )

    load_calls = []

    def fake_load(ctx, module_name):
        load_calls.append(module_name)
        if module_name == "bad":
            raise up_module.libyang.LibyangError("skip")

    monkeypatch.setattr(up_module, "load_yang_module", fake_load)

    parsed_blocks = []
    monkeypatch.setattr(
        parser,
        "_parse_libyang_block",
        lambda block, data_format, no_state: parsed_blocks.append(block)
        or {block: True},
    )

    docs = parser.parse("dummy.xml", file_type="xml")

    assert docs == [{"<a/>": True}, {"<b/>": True}]
    assert set(load_calls) == {"good", "bad"}
    assert parsed_blocks == ["<a/>", "<b/>"]


def test_parse_json_branch(monkeypatch, up_module):
    """Exercise JSON parsing path with supplied blocks."""
    parser = up_module.UniversalParser()
    monkeypatch.setattr(parser, "_json_multi_root_handler", lambda path: ['{"k":1}'])
    monkeypatch.setattr(
        parser, "_extract_required_modules_from_block", lambda block, ftype: []
    )
    monkeypatch.setattr(
        parser,
        "_parse_libyang_block",
        lambda block, data_format, no_state: {"parsed": data_format},
    )

    docs = parser.parse("dummy.json", file_type="json", no_state=False)

    assert docs == [{"parsed": "json"}]


def test_parse_unsupported_type_raises(up_module):
    """Unsupported file extensions raise ValueError."""
    parser = up_module.UniversalParser()

    with pytest.raises(ValueError):
        parser.parse("file.yaml", file_type="yaml")


def test_parse_propagates_validation_error(monkeypatch, up_module):
    """Validation errors during parsing propagate to the caller."""
    parser = up_module.UniversalParser()
    monkeypatch.setattr(parser, "_xml_multi_root_handler", lambda path: ["<a/>"])
    monkeypatch.setattr(
        parser, "_extract_required_modules_from_block", lambda block, ftype: []
    )

    def raise_error(*args, **kwargs):
        raise up_module.libyang.LibyangError("fail")

    monkeypatch.setattr(parser, "_parse_libyang_block", raise_error)

    with pytest.raises(up_module.libyang.LibyangError):
        parser.parse("dummy.xml", file_type="xml")


def test_has_chronos_domain_detects_presence(up_module):
    """Detect chronos-domain key within parsed documents."""
    parser = up_module.UniversalParser()
    parser.documents = [{"config": {"chronos-domain": "present"}}]

    assert parser.has_chronos_domain() is True


def test_has_chronos_domain_absent(up_module):
    """Return False when chronos-domain is missing."""
    parser = up_module.UniversalParser()
    parser.documents = [{"config": {"other": "value"}}]

    assert parser.has_chronos_domain() is False


def test_contains_chronos_in_nested_list(up_module):
    """Search nested structures for chronos-domain occurrences."""
    parser = up_module.UniversalParser()
    data = [
        {"name": "something"},
        ["nope", {"nested": "chronos-domain"}],
    ]

    assert parser._contains_chronos(data) is True


def test_contains_chronos_negative(up_module):
    """Confirm chronos-domain is absent in simple structures."""
    parser = up_module.UniversalParser()
    data = {"name": "example", "values": [1, 2, 3]}

    assert parser._contains_chronos(data) is False


def test_refresh_calls_parse(monkeypatch, up_module):
    """Refresh delegates to parse with given arguments."""
    parser = up_module.UniversalParser()
    called = {}

    def fake_parse(path, file_type="xml"):
        called["path"] = path
        called["ftype"] = file_type
        return ["refreshed"]

    monkeypatch.setattr(parser, "parse", fake_parse)

    result = parser.refresh("config.xml", file_type="json")

    assert result == ["refreshed"]
    assert called == {"path": "config.xml", "ftype": "json"}


def test_get_dictionary_helper_returns_helper(up_module):
    """Return GE_Dictionary when chronos-domain exists."""
    parser = up_module.UniversalParser()
    parser.documents = [{"chronos-domain": "here"}]

    helper = parser.get_dictionary_helper()

    assert isinstance(helper, up_module.GE_Dictionary)


def test_get_dictionary_helper_none_when_absent(up_module):
    """Return None when chronos-domain is not found."""
    parser = up_module.UniversalParser()
    parser.documents = [{"other": "value"}]

    assert parser.get_dictionary_helper() is None
