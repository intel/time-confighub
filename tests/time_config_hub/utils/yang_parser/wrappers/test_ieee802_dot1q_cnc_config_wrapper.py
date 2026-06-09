# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for Ieee8021QCncConfigWrapper using the I226-1-ES-IDEAL fixture.

Stream types in cnc_config_I226.xml:
  Type A – local talker, non-time-aware, transmission-selection=0: 00-11, 00-12
  Type B – local talker, non-time-aware, transmission-selection=1: 00-09, 00-0a
  Type C – local talker, time-aware,     transmission-selection=0: 00-01, 00-02
  Type D – local listener (remote talker, no talker iface-config): 00-0b, 00-0c
"""

from pathlib import Path

import pytest

from time_config_hub.utils.yang_parser.exceptions import InvalidInputDataError
from time_config_hub.utils.yang_parser.wrappers.ieee802_dot1q_cnc_config import (
    Ieee8021QCncConfigWrapper,
)

_FIXTURES = Path(__file__).parent / "fixtures"

_ALL_STREAM_IDS = [
    "de-ad-be-ef-00-01:00-11",  # Type A
    "de-ad-be-ef-00-01:00-12",  # Type A
    "de-ad-be-ef-00-01:00-09",  # Type B
    "de-ad-be-ef-00-01:00-0a",  # Type B
    "de-ad-be-ef-00-01:00-01",  # Type C
    "de-ad-be-ef-00-01:00-02",  # Type C
    "de-ad-be-ef-00-03:00-0b",  # Type D
    "de-ad-be-ef-00-04:00-0c",  # Type D
]

_TYPE_A_IDS = ["de-ad-be-ef-00-01:00-11", "de-ad-be-ef-00-01:00-12"]
_TYPE_B_IDS = ["de-ad-be-ef-00-01:00-09", "de-ad-be-ef-00-01:00-0a"]
_TYPE_C_IDS = ["de-ad-be-ef-00-01:00-01", "de-ad-be-ef-00-01:00-02"]
_TYPE_D_IDS = ["de-ad-be-ef-00-03:00-0b", "de-ad-be-ef-00-04:00-0c"]


@pytest.fixture(scope="module")
def raw_xml() -> str:
    """Load the full cnc_config_I226.xml fixture."""
    return (_FIXTURES / "cnc_config_I226.xml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def wrapper(raw_xml: str) -> Ieee8021QCncConfigWrapper:
    """Instantiate Ieee8021QCncConfigWrapper from the fixture XML."""
    return Ieee8021QCncConfigWrapper(raw_xml)


@pytest.fixture(scope="module")
def all_talker_info(wrapper: Ieee8021QCncConfigWrapper):
    """Pre-compute get_all_talker_stream_info() once for filter tests."""
    return wrapper.get_all_talker_stream_info()


# ---------------------------------------------------------------------------
# Class metadata
# ---------------------------------------------------------------------------


def test_yang_module_constant():
    assert Ieee8021QCncConfigWrapper.YANG_MODULE == "ieee802-dot1q-cnc-config"


def test_yang_namespace_constant():
    assert (
        Ieee8021QCncConfigWrapper.YANG_NAMESPACE
        == "urn:ieee:std:802.1Q:yang:ieee802-dot1q-cnc-config"
    )


# ---------------------------------------------------------------------------
# get_stream_ids
# ---------------------------------------------------------------------------


def test_get_stream_ids_count(wrapper: Ieee8021QCncConfigWrapper):
    assert len(wrapper.get_stream_ids()) == 8


def test_get_stream_ids_all_present(wrapper: Ieee8021QCncConfigWrapper):
    ids = wrapper.get_stream_ids()
    for sid in _ALL_STREAM_IDS:
        assert sid in ids, f"Expected stream ID {sid!r} not found"


def test_get_stream_ids_order(wrapper: Ieee8021QCncConfigWrapper):
    assert wrapper.get_stream_ids() == _ALL_STREAM_IDS


def test_get_stream_ids_raises_when_no_streams():
    xml = (
        '<cnc-config xmlns="urn:ieee:std:802.1Q:yang:ieee802-dot1q-cnc-config">'
        "<domain><domain-id>test</domain-id><cuc><cuc-id>test</cuc-id></cuc></domain>"
        "</cnc-config>"
    )
    w = Ieee8021QCncConfigWrapper(xml)
    with pytest.raises(InvalidInputDataError):
        w.get_stream_ids()


# ---------------------------------------------------------------------------
# get_talker_vlan_info
# ---------------------------------------------------------------------------


def test_get_talker_vlan_info_has_all_stream_keys(wrapper: Ieee8021QCncConfigWrapper):
    info = wrapper.get_talker_vlan_info()
    for sid in _ALL_STREAM_IDS:
        assert sid in info


def test_get_talker_vlan_info_type_a_first(wrapper: Ieee8021QCncConfigWrapper):
    info = wrapper.get_talker_vlan_info()
    talker = info["de-ad-be-ef-00-01:00-11"][0]
    assert talker["mac"] == "DE-AD-BE-EF-00-01"
    assert talker["interface"] == "enp170s0"
    assert talker["vlan"] == "18"
    assert talker["pcp"] == "1"


def test_get_talker_vlan_info_type_a_second(wrapper: Ieee8021QCncConfigWrapper):
    info = wrapper.get_talker_vlan_info()
    talker = info["de-ad-be-ef-00-01:00-12"][0]
    assert talker["vlan"] == "19"
    assert talker["pcp"] == "1"


def test_get_talker_vlan_info_type_b_pcp(wrapper: Ieee8021QCncConfigWrapper):
    info = wrapper.get_talker_vlan_info()
    for sid in _TYPE_B_IDS:
        assert info[sid][0]["pcp"] == "3"


def test_get_talker_vlan_info_type_c_pcp(wrapper: Ieee8021QCncConfigWrapper):
    info = wrapper.get_talker_vlan_info()
    for sid in _TYPE_C_IDS:
        assert info[sid][0]["pcp"] == "2"


def test_get_talker_vlan_info_type_d_no_interface_config(
    wrapper: Ieee8021QCncConfigWrapper,
):
    info = wrapper.get_talker_vlan_info()
    for sid in _TYPE_D_IDS:
        talker = info[sid][0]
        assert talker["interface"] is None
        assert talker["vlan"] is None
        assert talker["pcp"] is None


# ---------------------------------------------------------------------------
# get_talker_vlan_info_by_stream
# ---------------------------------------------------------------------------


def test_get_talker_vlan_info_by_stream_type_a(wrapper: Ieee8021QCncConfigWrapper):
    result = wrapper.get_talker_vlan_info_by_stream("de-ad-be-ef-00-01:00-11")
    assert result == ["MAC: DE-AD-BE-EF-00-01, IF: enp170s0, VLAN: 18, PCP: 1"]


def test_get_talker_vlan_info_by_stream_type_b(wrapper: Ieee8021QCncConfigWrapper):
    result = wrapper.get_talker_vlan_info_by_stream("de-ad-be-ef-00-01:00-09")
    assert result == ["MAC: DE-AD-BE-EF-00-01, IF: enp170s0, VLAN: 14, PCP: 3"]


def test_get_talker_vlan_info_by_stream_type_c(wrapper: Ieee8021QCncConfigWrapper):
    result = wrapper.get_talker_vlan_info_by_stream("de-ad-be-ef-00-01:00-01")
    assert result == ["MAC: DE-AD-BE-EF-00-01, IF: enp170s0, VLAN: 10, PCP: 2"]


def test_get_talker_vlan_info_by_stream_not_found(wrapper: Ieee8021QCncConfigWrapper):
    result = wrapper.get_talker_vlan_info_by_stream("missing-stream-id")
    assert result == ["Stream ID 'missing-stream-id' not found."]


# ---------------------------------------------------------------------------
# get_all_time_aware_talker_vlan_info
# ---------------------------------------------------------------------------


def test_get_all_time_aware_talker_vlan_info_only_type_c(
    wrapper: Ieee8021QCncConfigWrapper,
):
    info = wrapper.get_all_time_aware_talker_vlan_info()
    assert set(info.keys()) == set(_TYPE_C_IDS)


def test_get_all_time_aware_talker_vlan_info_stream_00_01(
    wrapper: Ieee8021QCncConfigWrapper,
):
    info = wrapper.get_all_time_aware_talker_vlan_info()
    entry = info["de-ad-be-ef-00-01:00-01"][0]
    assert entry["time-aware-offset"] == "192098"
    assert entry["vlan"] == "10"
    assert entry["pcp"] == "2"


def test_get_all_time_aware_talker_vlan_info_stream_00_02(
    wrapper: Ieee8021QCncConfigWrapper,
):
    info = wrapper.get_all_time_aware_talker_vlan_info()
    entry = info["de-ad-be-ef-00-01:00-02"][0]
    assert entry["time-aware-offset"] == "171924"
    assert entry["vlan"] == "11"
    assert entry["pcp"] == "2"


# ---------------------------------------------------------------------------
# get_time_aware_offsets_by_stream_id
# ---------------------------------------------------------------------------


def test_get_time_aware_offsets_stream_00_01(wrapper: Ieee8021QCncConfigWrapper):
    offsets = wrapper.get_time_aware_offsets_by_stream_id("de-ad-be-ef-00-01:00-01")
    assert offsets == ["192098"]


def test_get_time_aware_offsets_stream_00_02(wrapper: Ieee8021QCncConfigWrapper):
    offsets = wrapper.get_time_aware_offsets_by_stream_id("de-ad-be-ef-00-01:00-02")
    assert offsets == ["171924"]


def test_get_time_aware_offsets_non_time_aware_stream(
    wrapper: Ieee8021QCncConfigWrapper,
):
    offsets = wrapper.get_time_aware_offsets_by_stream_id("de-ad-be-ef-00-01:00-11")
    assert offsets == []


def test_get_time_aware_offsets_unknown_stream(wrapper: Ieee8021QCncConfigWrapper):
    offsets = wrapper.get_time_aware_offsets_by_stream_id("no-such-stream")
    assert offsets == []


# ---------------------------------------------------------------------------
# get_all_talker_stream_info
# ---------------------------------------------------------------------------


def test_get_all_talker_stream_info_has_all_streams(all_talker_info):
    assert set(all_talker_info.keys()) == set(_ALL_STREAM_IDS)


def test_get_all_talker_stream_info_type_c_time_aware(all_talker_info):
    for sid in _TYPE_C_IDS:
        talker = all_talker_info[sid][0]
        assert talker["time_aware"] is True
        assert talker["time_aware_offset"] is not None


def test_get_all_talker_stream_info_type_a_not_time_aware(all_talker_info):
    for sid in _TYPE_A_IDS:
        talker = all_talker_info[sid][0]
        assert talker["time_aware"] is False
        assert talker["vlan_tag"] is True


def test_get_all_talker_stream_info_type_b_not_time_aware(all_talker_info):
    for sid in _TYPE_B_IDS:
        talker = all_talker_info[sid][0]
        assert talker["time_aware"] is False
        assert talker["vlan_tag"] is True


def test_get_all_talker_stream_info_type_d_no_vlan(all_talker_info):
    for sid in _TYPE_D_IDS:
        talker = all_talker_info[sid][0]
        assert talker["vlan_tag"] is False
        assert talker["time_aware"] is False


def test_get_all_talker_stream_info_type_c_stream_00_01_offset(all_talker_info):
    talker = all_talker_info["de-ad-be-ef-00-01:00-01"][0]
    assert str(talker["time_aware_offset"]) == "192098"


def test_get_all_talker_stream_info_type_c_stream_00_02_offset(all_talker_info):
    talker = all_talker_info["de-ad-be-ef-00-01:00-02"][0]
    assert str(talker["time_aware_offset"]) == "171924"


def test_get_all_talker_stream_info_type_a_mac_addresses(all_talker_info):
    # The wrapper preserves the original casing from the XML, then replaces - with :
    talker = all_talker_info["de-ad-be-ef-00-01:00-11"][0]
    assert talker["source_mac"].upper() == "DE:AD:BE:EF:00:01"
    assert talker["destination_mac"].upper() == "01:00:5E:7F:00:11"


def test_get_all_talker_stream_info_type_a_interface(all_talker_info):
    talker = all_talker_info["de-ad-be-ef-00-01:00-11"][0]
    assert talker["interface_name"] == "enp170s0"


def test_get_all_talker_stream_info_type_a_vlan_details(all_talker_info):
    talker = all_talker_info["de-ad-be-ef-00-01:00-11"][0]
    assert talker["vlan_id"] == "18"
    assert talker["vlan_priority"] == "1"


def test_get_all_talker_stream_info_type_c_vlan_and_time_aware(all_talker_info):
    talker = all_talker_info["de-ad-be-ef-00-01:00-01"][0]
    assert talker["vlan_tag"] is True
    assert talker["vlan_id"] == "10"
    assert talker["vlan_priority"] == "2"
    assert talker["time_aware"] is True


# ---------------------------------------------------------------------------
# get_vlan_tagged_time_aware_talker_info
# ---------------------------------------------------------------------------


def test_get_vlan_tagged_time_aware_only_type_c(
    wrapper: Ieee8021QCncConfigWrapper, all_talker_info
):
    result = wrapper.get_vlan_tagged_time_aware_talker_info(all_talker_info)
    assert set(result.keys()) == set(_TYPE_C_IDS)


def test_get_vlan_tagged_time_aware_excludes_type_a_b_d(
    wrapper: Ieee8021QCncConfigWrapper, all_talker_info
):
    result = wrapper.get_vlan_tagged_time_aware_talker_info(all_talker_info)
    for sid in _TYPE_A_IDS + _TYPE_B_IDS + _TYPE_D_IDS:
        assert sid not in result


def test_get_vlan_tagged_time_aware_entries_are_time_aware(
    wrapper: Ieee8021QCncConfigWrapper, all_talker_info
):
    result = wrapper.get_vlan_tagged_time_aware_talker_info(all_talker_info)
    for talkers in result.values():
        for t in talkers:
            assert t["vlan_tag"] is True
            assert t["time_aware"] is True


# ---------------------------------------------------------------------------
# get_vlan_tagged_non_time_aware_talker_info
# ---------------------------------------------------------------------------


def test_get_vlan_tagged_non_time_aware_only_type_a_b(
    wrapper: Ieee8021QCncConfigWrapper, all_talker_info
):
    result = wrapper.get_vlan_tagged_non_time_aware_talker_info(all_talker_info)
    assert set(result.keys()) == set(_TYPE_A_IDS + _TYPE_B_IDS)


def test_get_vlan_tagged_non_time_aware_excludes_type_c_d(
    wrapper: Ieee8021QCncConfigWrapper, all_talker_info
):
    result = wrapper.get_vlan_tagged_non_time_aware_talker_info(all_talker_info)
    for sid in _TYPE_C_IDS + _TYPE_D_IDS:
        assert sid not in result


def test_get_vlan_tagged_non_time_aware_entries_not_time_aware(
    wrapper: Ieee8021QCncConfigWrapper, all_talker_info
):
    result = wrapper.get_vlan_tagged_non_time_aware_talker_info(all_talker_info)
    for talkers in result.values():
        for t in talkers:
            assert t["vlan_tag"] is True
            assert t["time_aware"] is False


# ---------------------------------------------------------------------------
# Base class properties
# ---------------------------------------------------------------------------


def test_raw_config_is_stored(wrapper: Ieee8021QCncConfigWrapper, raw_xml: str):
    assert wrapper.raw_config == raw_xml


def test_fmt_default_is_xml(wrapper: Ieee8021QCncConfigWrapper):
    assert wrapper.fmt == "xml"


def test_parsed_dict_is_dict(wrapper: Ieee8021QCncConfigWrapper):
    assert isinstance(wrapper.parsed_dict, dict)


def test_parsed_dict_has_cnc_config_key(wrapper: Ieee8021QCncConfigWrapper):
    assert "cnc-config" in wrapper.parsed_dict
