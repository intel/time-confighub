from unittest.mock import MagicMock, patch

import pytest

from tsn_config_parser.tc_command import (
    _clsact_exists,
    create_tc_filter_commands_for_non_time_aware_talkers,
    create_tc_filter_commands_for_time_aware_talkers,
)


@pytest.fixture
def sample_vlan_time_aware_info():
    """Fixture simulating VLAN-tagged time-aware talker data."""
    return {
        "streamA": [
            {
                "interface_name": "enp170s0",
                "source_mac": "aa:bb:cc:dd:ee:ff",
                "destination_mac": "11:22:33:44:55:66",
                "source_ip": "192.168.1.10",
                "destination_ip": "192.168.1.20",
                "destination_port": 8080,
                "vlan_id": 22,
                "vlan_priority": 3,
            }
        ],
        "streamB": [
            {
                "interface_name": "enp170s1",
                "source_mac": "aa:bb:cc:dd:ee:00",
                "destination_mac": "11:22:33:44:55:77",
                "source_ip": "10.0.0.1",
                "destination_ip": "10.0.0.2",
                "destination_port": 5050,
                "vlan_id": 33,
                "vlan_priority": 4,
            }
        ],
    }


def test_clsact_exists_true(monkeypatch):
    """Verify _clsact_exists returns True when 'clsact' appears in tc output."""

    mock_run = MagicMock()
    mock_run.return_value.stdout = "qdisc clsact ffff: parent ffff:fff1"
    monkeypatch.setattr("subprocess.run", mock_run)

    assert _clsact_exists("enp170s0") is True
    mock_run.assert_called_once_with(
        ["tc", "qdisc", "show", "dev", "enp170s0"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_clsact_exists_false(monkeypatch):
    """Verify _clsact_exists returns False when no clsact is found."""

    mock_run = MagicMock()
    mock_run.return_value.stdout = "qdisc mq 0: root"
    monkeypatch.setattr("subprocess.run", mock_run)

    assert _clsact_exists("enp170s0") is False


@patch("tsn_config_parser.tc_command._clsact_exists", return_value=False)
def test_generate_tc_filter_commands_adds_clsact(
    mock_clsact, sample_vlan_time_aware_info
):
    """Ensure clsact is added when missing."""

    cmds = create_tc_filter_commands_for_time_aware_talkers(sample_vlan_time_aware_info)

    # Should contain two clsact commands (one per interface)
    clsact_cmds = [c for c in cmds if "clsact" in c]
    assert len(clsact_cmds) == 2

    # Verify expected command structure
    assert any("protocol ip" in c for c in cmds)
    assert any("protocol 802.1Q" in c for c in cmds)
    assert any("action vlan push id 22 protocol 802.1Q priority 3" in c for c in cmds)
    assert any("action skbedit priority 3" in c for c in cmds)
    assert any("enp170s0" in c for c in cmds)


@patch("tsn_config_parser.tc_command._clsact_exists", return_value=True)
def test_generate_tc_filter_commands_skips_clsact(
    mock_clsact, sample_vlan_time_aware_info
):
    """Ensure clsact is not added if it already exists."""

    cmds = create_tc_filter_commands_for_time_aware_talkers(sample_vlan_time_aware_info)

    # No clsact commands should be generated
    assert not any("clsact" in c for c in cmds)

    # Each stream should yield two tc rules (ip + vlan)
    assert sum("protocol ip" in c for c in cmds) == 2
    assert sum("protocol 802.1Q" in c for c in cmds) == 2


def test_time_aware_handles_empty_dataset():
    """Should return an empty list when no talker info is provided."""

    cmds = create_tc_filter_commands_for_time_aware_talkers({})
    assert cmds == []


@pytest.fixture
def sample_vlan_non_time_aware_info():
    """Fixture simulating VLAN-tagged non-time-aware talker data."""
    return {
        "streamX": [
            {
                "interface_name": "eth0",
                "source_mac": "aa:bb:cc:dd:ee:ff",
                "destination_mac": "11:22:33:44:55:66",
                "source_ip": "192.168.1.10",
                "destination_ip": "192.168.1.20",
                "destination_port": 8080,
                "vlan_id": 100,
                "vlan_priority": 3,
            }
        ],
        "streamY": [
            {
                "interface_name": "eth1",
                "source_mac": "00:11:22:33:44:55",
                "destination_mac": "66:77:88:99:aa:bb",
                "source_ip": "10.1.1.10",
                "destination_ip": "10.1.1.20",
                "destination_port": 9090,
                "vlan_id": 200,
                "vlan_priority": 5,
            }
        ],
    }


def test_generate_non_time_aware_vlan_push_commands(sample_vlan_non_time_aware_info):
    """Verify correct tc filter commands are generated for non-time-aware talkers."""

    cmds = create_tc_filter_commands_for_non_time_aware_talkers(
        sample_vlan_non_time_aware_info
    )

    # Expect one command per talker
    assert len(cmds) == 2

    # Command should include VLAN push syntax
    assert all("action vlan push" in c for c in cmds)
    # Filter protocol should be IP
    assert all("protocol ip flower" in c for c in cmds)
    # VLAN push action should include 802.1Q specification
    assert all("protocol 802.1Q" in c for c in cmds)

    # Validate that IDs and priorities appear correctly
    assert any("id 100 protocol 802.1Q priority 3" in c for c in cmds)
    assert any("id 200 protocol 802.1Q priority 5" in c for c in cmds)

    # Check that fields like src_mac and dst_ip are correctly included
    assert any("src_mac aa:bb:cc:dd:ee:ff" in c for c in cmds)
    assert any("dst_ip 192.168.1.20" in c for c in cmds)


def test_non_time_aware_vlan_handles_missing_fields():
    """Ensure missing optional fields do not break command generation."""

    minimal_data = {
        "streamZ": [
            {
                "interface_name": "eth0",
                "vlan_id": 300,
                "vlan_priority": 2,
            }
        ]
    }

    cmds = create_tc_filter_commands_for_non_time_aware_talkers(minimal_data)

    # Should still generate one valid command
    assert len(cmds) == 1
    cmd = cmds[0]

    # Should include VLAN push even with missing fields
    assert "action vlan push id 300 protocol 802.1Q priority 2" in cmd
    assert "protocol ip" in cmd
    # Ensure it doesn't include empty fields
    assert "src_mac None" not in cmd
    assert "dst_mac None" not in cmd
