import pytest

from tsn_config_parser.GE_dictionary import GE_Dictionary


@pytest.fixture
def sample_all_talker_info():
    return {
        "stream1": [
            {"vlan_tag": True, "time_aware": True, "interface_name": "eth0"},
            {"vlan_tag": True, "time_aware": False, "interface_name": "eth1"},
            {"vlan_tag": False, "time_aware": True, "interface_name": "eth2"},
        ],
        "stream2": [
            {"vlan_tag": True, "time_aware": True, "interface_name": "enp1s0"},
            {"vlan_tag": False, "time_aware": False, "interface_name": "enp2s0"},
        ],
    }


def test_get_vlan_tagged_time_aware_talker_info(sample_all_talker_info):
    ge = GE_Dictionary([])
    result = ge.get_vlan_tagged_time_aware_talker_info(sample_all_talker_info)

    assert set(result.keys()) == {"stream1", "stream2"}
    assert len(result["stream1"]) == 1
    assert result["stream1"][0]["interface_name"] == "eth0"
    assert len(result["stream2"]) == 1
    assert result["stream2"][0]["interface_name"] == "enp1s0"

    for talkers in result.values():
        for talker in talkers:
            assert talker["vlan_tag"] is True
            assert talker["time_aware"] is True


def test_get_vlan_tagged_non_time_aware_talker_info(sample_all_talker_info):
    ge = GE_Dictionary([])
    result = ge.get_vlan_tagged_non_time_aware_talker_info(sample_all_talker_info)

    assert set(result.keys()) == {"stream1"}
    assert len(result["stream1"]) == 1
    assert result["stream1"][0]["interface_name"] == "eth1"

    for talkers in result.values():
        for talker in talkers:
            assert talker["vlan_tag"] is True
            assert talker["time_aware"] is False


def test_vlan_tag_filters_handle_empty_dataset():
    ge = GE_Dictionary([])

    assert ge.get_vlan_tagged_time_aware_talker_info({}) == {}
    assert ge.get_vlan_tagged_non_time_aware_talker_info({}) == {}
