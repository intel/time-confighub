# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for IetfInterfacesWrapper using the I226-1-ES-IDEAL fixture."""

from pathlib import Path

import pytest

from time_config_hub.utils.yang_parser.exceptions import InvalidInputDataError
from time_config_hub.utils.yang_parser.wrappers.ietf_interfaces import (
    IetfInterfacesWrapper,
)

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def raw_xml() -> str:
    """Load the full interfaces_I226.xml fixture."""
    return (_FIXTURES / "interfaces_I226.xml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def wrapper(raw_xml: str) -> IetfInterfacesWrapper:
    """Instantiate IetfInterfacesWrapper from the fixture XML."""
    return IetfInterfacesWrapper(raw_xml)


# ---------------------------------------------------------------------------
# Class metadata
# ---------------------------------------------------------------------------


def test_yang_module_constant():
    assert IetfInterfacesWrapper.YANG_MODULE == "ietf-interfaces"


def test_yang_namespace_constant():
    assert (
        IetfInterfacesWrapper.YANG_NAMESPACE
        == "urn:ietf:params:xml:ns:yang:ietf-interfaces"
    )


# ---------------------------------------------------------------------------
# get_interface_names
# ---------------------------------------------------------------------------


def test_get_interface_names_returns_list(wrapper: IetfInterfacesWrapper):
    names = wrapper.get_interface_names()
    assert isinstance(names, list)
    assert len(names) == 1


def test_get_interface_names_value(wrapper: IetfInterfacesWrapper):
    assert wrapper.get_interface_names() == ["enp170s0"]


def test_get_interface_names_raises_when_empty():
    # Interface element present but has no <name> child — names list stays empty
    xml = (
        '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">'
        "<interface><enabled>true</enabled></interface>"
        "</interfaces>"
    )
    w = IetfInterfacesWrapper(xml)
    with pytest.raises(InvalidInputDataError):
        w.get_interface_names()


# ---------------------------------------------------------------------------
# get_gate_control_entries
# ---------------------------------------------------------------------------


def test_get_gate_control_entries_count(wrapper: IetfInterfacesWrapper):
    entries = wrapper.get_gate_control_entries()
    assert len(entries) == 18


def test_get_gate_control_entries_keys(wrapper: IetfInterfacesWrapper):
    for entry in wrapper.get_gate_control_entries():
        assert "index" in entry
        assert "operation-name" in entry
        assert "gate-states-value" in entry
        assert "time-interval-value" in entry


def test_get_gate_control_entries_first_entry(wrapper: IetfInterfacesWrapper):
    first = wrapper.get_gate_control_entries()[0]
    assert first["index"] == "0"
    assert first["gate-states-value"] == "11"
    assert first["time-interval-value"] == "78600"


def test_get_gate_control_entries_second_entry(wrapper: IetfInterfacesWrapper):
    second = wrapper.get_gate_control_entries()[1]
    assert second["index"] == "1"
    assert second["gate-states-value"] == "4"
    assert second["time-interval-value"] == "8736"


def test_get_gate_control_entries_last_entry(wrapper: IetfInterfacesWrapper):
    last = wrapper.get_gate_control_entries()[-1]
    assert last["index"] == "17"
    assert last["gate-states-value"] == "11"
    assert last["time-interval-value"] == "362056"


def test_get_gate_control_entries_all_use_set_gate_states(
    wrapper: IetfInterfacesWrapper,
):
    for entry in wrapper.get_gate_control_entries():
        assert "sched:set-gate-states" in entry["operation-name"]


def test_get_gate_control_entries_raises_when_no_gate_entries():
    xml = (
        '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">'
        "<interface><name>eth0</name></interface>"
        "</interfaces>"
    )
    w = IetfInterfacesWrapper(xml)
    with pytest.raises(InvalidInputDataError):
        w.get_gate_control_entries()


# ---------------------------------------------------------------------------
# get_gate_control_entries_formatted
# ---------------------------------------------------------------------------


def test_get_gate_control_entries_formatted_count(wrapper: IetfInterfacesWrapper):
    assert len(wrapper.get_gate_control_entries_formatted()) == 18


def test_get_gate_control_entries_formatted_first(wrapper: IetfInterfacesWrapper):
    formatted = wrapper.get_gate_control_entries_formatted()
    # gate-states-value=11 (decimal) → 0x0B hex
    assert formatted[0] == "sched-entry S 0B 78600"


def test_get_gate_control_entries_formatted_second(wrapper: IetfInterfacesWrapper):
    formatted = wrapper.get_gate_control_entries_formatted()
    # gate-states-value=4 (decimal) → 0x04 hex
    assert formatted[1] == "sched-entry S 04 8736"


def test_get_gate_control_entries_formatted_all_start_with_sched_entry(
    wrapper: IetfInterfacesWrapper,
):
    for line in wrapper.get_gate_control_entries_formatted():
        assert line.startswith("sched-entry S ")


# ---------------------------------------------------------------------------
# get_gcl_list (alias for get_gate_control_entries_formatted)
# ---------------------------------------------------------------------------


def test_get_gcl_list_equals_formatted(wrapper: IetfInterfacesWrapper):
    assert wrapper.get_gcl_list() == wrapper.get_gate_control_entries_formatted()


# ---------------------------------------------------------------------------
# get_cbsa_params
# ---------------------------------------------------------------------------


def test_get_cbsa_params_returns_one_entry(wrapper: IetfInterfacesWrapper):
    params = wrapper.get_cbsa_params()
    assert isinstance(params, list)
    assert len(params) == 1


def test_get_cbsa_params_traffic_class(wrapper: IetfInterfacesWrapper):
    assert wrapper.get_cbsa_params()[0]["traffic-class"] == "3"


def test_get_cbsa_params_admin_idle_slope(wrapper: IetfInterfacesWrapper):
    assert wrapper.get_cbsa_params()[0]["admin-idle-slope"] == "4229179"


def test_get_cbsa_params_empty_when_no_cbsa():
    xml = (
        '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">'
        "<interface><name>eth0</name></interface>"
        "</interfaces>"
    )
    w = IetfInterfacesWrapper(xml)
    assert w.get_cbsa_params() == []


# ---------------------------------------------------------------------------
# get_admin_cycle_time
# ---------------------------------------------------------------------------


def test_get_admin_cycle_time_count(wrapper: IetfInterfacesWrapper):
    result = wrapper.get_admin_cycle_time()
    assert isinstance(result, list)
    assert len(result) == 1


def test_get_admin_cycle_time_numerator(wrapper: IetfInterfacesWrapper):
    assert wrapper.get_admin_cycle_time()[0]["numerator"] == "10000000"


def test_get_admin_cycle_time_denominator(wrapper: IetfInterfacesWrapper):
    assert wrapper.get_admin_cycle_time()[0]["denominator"] == "1000000000"


def test_get_admin_cycle_time_empty_when_no_gate_table():
    xml = (
        '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">'
        "<interface><name>eth0</name></interface>"
        "</interfaces>"
    )
    w = IetfInterfacesWrapper(xml)
    assert w.get_admin_cycle_time() == []


# ---------------------------------------------------------------------------
# Base class properties
# ---------------------------------------------------------------------------


def test_raw_config_is_stored(wrapper: IetfInterfacesWrapper, raw_xml: str):
    assert wrapper.raw_config == raw_xml


def test_fmt_default_is_xml(wrapper: IetfInterfacesWrapper):
    assert wrapper.fmt == "xml"


def test_parsed_dict_is_dict(wrapper: IetfInterfacesWrapper):
    assert isinstance(wrapper.parsed_dict, dict)


def test_parsed_dict_has_interfaces_key(wrapper: IetfInterfacesWrapper):
    assert "interfaces" in wrapper.parsed_dict
