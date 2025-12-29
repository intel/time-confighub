import pytest

from tsn_config_parser.GE_dictionary import GE_Dictionary


def build_docs_for_interfaces():
    return [
        {
            "interfaces": {
                "interface": [
                    {"name": {"#text": "eth0"}},
                    {"name": "eth1"},
                ]
            }
        }
    ]


def build_docs_for_streams():
    return [
        {
            "cnc-config": {
                "domain": {
                    "cuc": {
                        "stream": [
                            {"stream-id": {"#text": "sA"}},
                            {"stream-id": "sB"},
                        ]
                    }
                }
            }
        }
    ]


def build_docs_for_talkers():
    return [
        {
            "cnc-config": {
                "domain": {
                    "cuc": {
                        "stream": [
                            {
                                "stream-id": "s1",
                                "talker": {
                                    "end-station-interfaces": {
                                        "mac-address": "AA-BB-CC-00-11-22"
                                    },
                                    "interface-configuration": {
                                        "interface-list": {
                                            "interface-name": "eth0",
                                            "mac-address": "DE-AD-BE-EF-00-01",
                                            "config-list": [
                                                {
                                                    "ieee802-mac-addresses": {
                                                        "destination-mac-address": "11-22-33-44-55-66"
                                                    }
                                                },
                                                {
                                                    "ieee802-vlan-tag": {
                                                        "vlan-id": 22,
                                                        "priority-code-point": 3,
                                                    }
                                                },
                                                {
                                                    "ipv4-tuple": {
                                                        "source-ip-address": "10.0.0.1",
                                                        "destination-ip-address": "10.0.0.2",
                                                        "dscp": 16,
                                                        "protocol": 17,
                                                        "source-port": 1000,
                                                        "destination-port": 2000,
                                                    }
                                                },
                                            ],
                                        }
                                    },
                                },
                            },
                            {
                                "stream-id": "s2",
                                "talker": [
                                    {
                                        "end-station-interfaces": {
                                            "mac-address": "00-11-22-33-44-55"
                                        },
                                        "interface-configuration": {
                                            "interface-list": {
                                                "interface-name": "eth1",
                                                "mac-address": "66-77-88-99-AA-BB",
                                                "config-list": [
                                                    {"time-aware-offset": 12345},
                                                    {
                                                        "ieee802-vlan-tag": {
                                                            "vlan-id": 33,
                                                            "priority-code-point": 4,
                                                        }
                                                    },
                                                ],
                                            }
                                        },
                                    },
                                    {
                                        "end-station-interfaces": {
                                            "mac-address": "00-00-00-00-00-00"
                                        },
                                        "interface-configuration": {
                                            "interface-list": {
                                                "interface-name": "eth2",
                                                "mac-address": "00-00-00-00-00-01",
                                                "config-list": [
                                                    {
                                                        "time-aware": {
                                                            "earliest-transmit-offset": 1
                                                        }
                                                    }
                                                ],
                                            }
                                        },
                                    },
                                ],
                            },
                        ]
                    }
                }
            }
        }
    ]


def build_docs_for_gate_table():
    return [
        {
            "interfaces": {
                "interface": {
                    "name": "eth0",
                    "gate-parameter-table": {
                        "admin-control-list": {
                            "gate-control-entry": [
                                {
                                    "operation-name": "sched:set-gate-states",
                                    "gate-states-value": 15,
                                    "time-interval-value": 500000,
                                },
                                {
                                    "operation-name": "other-op",
                                    "gate-states-value": 3,
                                    "time-interval-value": 100,
                                },
                            ]
                        }
                    },
                }
            }
        }
    ]


def test_get_interface_names_collects_both_text_forms():
    ge = GE_Dictionary(build_docs_for_interfaces())
    assert ge.get_interface_names() == ["eth0", "eth1"]


def test_get_stream_ids_collects_strings_and_dict_text():
    ge = GE_Dictionary(build_docs_for_streams())
    assert set(ge.get_stream_ids()) == {"sA", "sB"}


def test_get_talker_vlan_info_and_by_stream():
    ge = GE_Dictionary(build_docs_for_talkers())

    vlan_info = ge.get_talker_vlan_info()
    assert set(vlan_info.keys()) == {"s1", "s2"}
    # s1 single talker values
    t0 = vlan_info["s1"][0]
    assert t0["mac"] == "AA-BB-CC-00-11-22"
    assert t0["interface"] == "eth0"
    assert t0["vlan"] == 22
    assert t0["pcp"] == 3

    # formatted by stream
    lines = ge.get_talker_vlan_info_by_stream("s1")
    assert any(
        "MAC: AA-BB-CC-00-11-22, IF: eth0, VLAN: 22, PCP: 3" in line for line in lines
    )

    # unknown stream
    assert ge.get_talker_vlan_info_by_stream("nope") == ["Stream ID 'nope' not found."]


def test_get_all_time_aware_talker_vlan_info_and_offsets(capsys):
    ge = GE_Dictionary(build_docs_for_talkers())

    info = ge.get_all_time_aware_talker_vlan_info()
    # s2 has two talkers with time-aware related data
    assert "s2" in info
    vals = info["s2"]
    # One entry from explicit time-aware-offset, one from time-aware block (interface eth2)
    assert any(v["time-aware-offset"] == "12345" for v in vals)

    # Stream not present in offsets
    offsets = ge.get_time_aware_offsets_by_stream_id("s1")
    assert offsets == []
    out = capsys.readouterr().out
    assert "No <time-aware-offset> found for stream 's1'." in out

    # Existing stream offsets
    offsets2 = ge.get_time_aware_offsets_by_stream_id("s2")
    assert offsets2 == ["12345"]


def test_get_gate_control_entries_and_formatted():
    ge = GE_Dictionary(build_docs_for_gate_table())
    entries = ge.get_gate_control_entries()
    assert len(entries) == 2
    formatted = ge.get_gate_control_entries_formatted()
    # 15 -> 0F hex
    assert "sched-entry S 0F 500000" in formatted
    assert "sched-entry ? 3 100" in formatted


def test_get_all_talker_stream_info_combines_expected_fields():
    ge = GE_Dictionary(build_docs_for_talkers())
    data = ge.get_all_talker_stream_info()

    assert set(data.keys()) == {"s1", "s2"}

    s1 = data["s1"][0]
    assert s1["interface_name"] == "eth0"
    assert s1["interface_mac"] == "DE:AD:BE:EF:00:01"
    assert s1["source_mac"] == "AA:BB:CC:00:11:22"
    assert s1["destination_mac"] == "11:22:33:44:55:66"
    assert s1["vlan_tag"] is True
    assert s1["vlan_id"] == 22
    assert s1["vlan_priority"] == 3
    assert s1["source_ip"] == "10.0.0.1"
    assert s1["destination_ip"] == "10.0.0.2"
    assert s1["ip_protocol"] == 17
    assert s1["source_port"] == 1000
    assert s1["destination_port"] == 2000
    assert s1["time_aware"] is False

    # s2 should include time-aware flags from either offset or time-aware block
    s2_all = data["s2"]
    assert any(t["time_aware"] for t in s2_all)


# -----------------------------
# VLAN filtering helpers (from previous tests, expanded)
# -----------------------------


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


def test_vlan_filters_exclude_streams_without_matches():
    ge = GE_Dictionary([])
    data = {
        "s1": [
            {"vlan_tag": False, "time_aware": True},
            {"vlan_tag": False, "time_aware": False},
        ],
        "s2": [
            {"other": 1},
        ],
    }

    assert ge.get_vlan_tagged_time_aware_talker_info(data) == {}
    assert ge.get_vlan_tagged_non_time_aware_talker_info(data) == {}


def test_vlan_filters_preserve_matching_entries_and_fields():
    ge = GE_Dictionary([])
    s1_talker1 = {
        "vlan_tag": True,
        "time_aware": True,
        "interface_name": "eth0",
        "vlan_id": 10,
        "extra": "keepme",
    }
    s1_talker2 = {
        "vlan_tag": True,
        "time_aware": False,
        "interface_name": "eth1",
        "vlan_id": 20,
        "extra": "keepme2",
    }
    s1_talker3 = {
        "vlan_tag": False,
        "time_aware": True,
        "interface_name": "eth2",
        "vlan_id": 30,
    }
    data = {"s1": [s1_talker1, s1_talker2, s1_talker3]}

    time_aware = ge.get_vlan_tagged_time_aware_talker_info(data)
    non_time_aware = ge.get_vlan_tagged_non_time_aware_talker_info(data)

    assert list(time_aware.keys()) == ["s1"]
    assert time_aware["s1"] == [s1_talker1]
    assert list(non_time_aware.keys()) == ["s1"]
    assert non_time_aware["s1"] == [s1_talker2]


def test_vlan_filters_do_not_mutate_input():
    ge = GE_Dictionary([])
    data = {
        "stream": [
            {"vlan_tag": True, "time_aware": True, "k": 1},
            {"vlan_tag": True, "time_aware": False, "k": 2},
        ]
    }
    original = {"stream": [dict(x) for x in data["stream"]]}

    _ = ge.get_vlan_tagged_time_aware_talker_info(data)
    _ = ge.get_vlan_tagged_non_time_aware_talker_info(data)

    assert data == original


def test_vlan_filters_truthy_values_like_ints():
    ge = GE_Dictionary([])
    data = {
        "s": [
            {"vlan_tag": 1, "time_aware": 1, "name": "ta"},
            {"vlan_tag": 1, "time_aware": 0, "name": "nonta"},
            {"vlan_tag": 0, "time_aware": 1, "name": "exclude"},
        ]
    }

    ta = ge.get_vlan_tagged_time_aware_talker_info(data)
    nonta = ge.get_vlan_tagged_non_time_aware_talker_info(data)

    assert [t["name"] for t in ta["s"]] == ["ta"]
    assert [t["name"] for t in nonta["s"]] == ["nonta"]


# Fixtures reused from previous file
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
