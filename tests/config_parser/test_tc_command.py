from unittest.mock import MagicMock, patch

import pytest
import socket

import tsn_config_parser.tc_command as tc
from tsn_config_parser.tc_command import (
    _clsact_exists,
    create_tc_filter_commands_for_non_time_aware_talkers,
    create_tc_filter_commands_for_time_aware_talkers,
)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Avoid delays during tests by disabling sleep and setting zero delay."""
    monkeypatch.setattr(tc, "safety_delay", 0)
    monkeypatch.setattr(tc.time, "sleep", lambda *_args, **_kwargs: None)


class Proc:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


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
    monkeypatch.setattr(tc.subprocess, "run", mock_run)

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
    monkeypatch.setattr(tc.subprocess, "run", mock_run)

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


# -----------------------------
# run_tc_command / simple helpers
# -----------------------------


def test_run_tc_command_invokes_sudo_and_returns_trimmed(monkeypatch):
    captured = {}

    def fake_run(cmd, shell, capture_output, text):
        captured.update(
            {"cmd": cmd, "shell": shell, "capture_output": capture_output, "text": text}
        )
        return Proc(stdout=" ok\n", stderr=" warn \n", returncode=0)

    monkeypatch.setattr(tc.subprocess, "run", fake_run)

    res = tc.run_tc_command("tc qdisc show dev eth0")
    assert res == {"stdout": "ok", "stderr": "warn", "returncode": 0}
    assert captured["cmd"].startswith("sudo ")
    assert "tc qdisc show dev eth0" in captured["cmd"]


def test_show_qdisc_calls_run_tc_command(monkeypatch):
    calls = []

    def fake_run(cmd: str):
        calls.append(cmd)
        return {"stdout": "qdisc info", "stderr": "", "returncode": 0}

    monkeypatch.setattr(tc, "run_tc_command", fake_run)
    out = tc.show_qdisc("enp0s3")
    assert out["stdout"] == "qdisc info"
    assert calls == ["tc qdisc show dev enp0s3"]


def test_show_tc_egress_filters_calls_run_tc_command(monkeypatch):
    calls = []

    def fake_run(cmd: str):
        calls.append(cmd)
        return {"stdout": "filters", "stderr": "", "returncode": 0}

    monkeypatch.setattr(tc, "run_tc_command", fake_run)
    out = tc.show_tc_egress_filters("eth0")
    assert out["stdout"] == "filters"
    assert calls == ["tc filter show dev eth0 egress"]


# -----------------------------
# reset_* idempotent wrappers
# -----------------------------


def test_reset_root_qdisc_interface_calls_del_when_present_but_returns_success(
    monkeypatch,
):
    called = {"del": False}

    monkeypatch.setattr(
        tc,
        "show_qdisc",
        lambda iface: {"stdout": "root qdisc", "stderr": "", "returncode": 0},
    )
    monkeypatch.setattr(
        tc,
        "run_tc_command",
        lambda cmd: called.update({"del": True})
        or {"stdout": "", "stderr": "", "returncode": 0},
    )

    res = tc.reset_root_qdisc_interface("eth0")
    assert res == {"stdout": "", "stderr": "", "returncode": 0}
    assert called["del"] is True


def test_reset_root_qdisc_interface_returns_success_when_absent(monkeypatch):
    monkeypatch.setattr(
        tc,
        "show_qdisc",
        lambda iface: {"stdout": "noop", "stderr": "", "returncode": 0},
    )
    res = tc.reset_root_qdisc_interface("eth1")
    assert res == {"stdout": "", "stderr": "", "returncode": 0}


def test_reset_clsact_qdisc_interface_calls_del_when_present_but_returns_success(
    monkeypatch,
):
    called = {"del": False}

    monkeypatch.setattr(
        tc,
        "show_qdisc",
        lambda iface: {"stdout": "clsact present", "stderr": "", "returncode": 0},
    )
    monkeypatch.setattr(
        tc,
        "run_tc_command",
        lambda cmd: called.update({"del": True})
        or {"stdout": "", "stderr": "", "returncode": 0},
    )

    res = tc.reset_clsact_qdisc_interface("eth0")
    assert res == {"stdout": "", "stderr": "", "returncode": 0}
    assert called["del"] is True


def test_reset_egress_filter_interface_calls_del_when_present_but_returns_success(
    monkeypatch,
):
    called = {"del": False}

    monkeypatch.setattr(
        tc,
        "show_tc_egress_filters",
        lambda iface: {"stdout": "filter X", "stderr": "", "returncode": 0},
    )
    monkeypatch.setattr(
        tc,
        "run_tc_command",
        lambda cmd: called.update({"del": True})
        or {"stdout": "", "stderr": "", "returncode": 0},
    )

    res = tc.reset_egress_filter_interface("eth0")
    assert res == {"stdout": "", "stderr": "", "returncode": 0}
    assert called["del"] is True


# -----------------------------
# reset_qdisc_interface combined workflow
# -----------------------------


def test_reset_qdisc_interface_deletes_all_when_present(monkeypatch):
    def fake_show_filters(_iface):
        return {"stdout": "filter present", "stderr": "", "returncode": 0}

    # First call (clsact check) returns clsact; second call (root check) returns root
    qdisc_calls = {"n": 0}

    def fake_show_qdisc_seq(_iface):
        qdisc_calls["n"] += 1
        if qdisc_calls["n"] == 1:
            return {"stdout": "clsact", "stderr": "", "returncode": 0}
        return {"stdout": "root", "stderr": "", "returncode": 0}

    run_calls = []

    def fake_run(cmd: str):
        run_calls.append(cmd)
        return {"stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(tc, "show_tc_egress_filters", fake_show_filters)
    monkeypatch.setattr(tc, "show_qdisc", fake_show_qdisc_seq)
    monkeypatch.setattr(tc, "run_tc_command", fake_run)

    res = tc.reset_qdisc_interface("eth0")

    assert res["interface"] == "eth0"
    assert res["egress_filters"]["returncode"] == 0
    assert res["clsact"]["returncode"] == 0
    assert res["root"]["returncode"] == 0

    assert "tc filter del dev eth0 egress" in run_calls
    assert "tc qdisc del dev eth0 clsact" in run_calls
    assert "tc qdisc del dev eth0 root" in run_calls


def test_reset_qdisc_interface_handles_exceptions(monkeypatch):
    monkeypatch.setattr(
        tc,
        "show_tc_egress_filters",
        lambda _iface: (_ for _ in ()).throw(RuntimeError("boom1")),
    )
    monkeypatch.setattr(
        tc, "show_qdisc", lambda _iface: (_ for _ in ()).throw(RuntimeError("boom2"))
    )

    res = tc.reset_qdisc_interface("eth9")
    assert res["egress_filters"]["returncode"] == 1
    assert "boom1" in res["egress_filters"]["stderr"]
    assert res["clsact"]["returncode"] == 1
    assert "boom2" in res["clsact"]["stderr"]
    assert res["root"]["returncode"] == 1
    assert "boom2" in res["root"]["stderr"]


# -----------------------------
# delete_tc_egress_filters
# -----------------------------


def test_delete_tc_egress_filters_for_specific_interface_returns_none(
    monkeypatch, capsys
):
    def fake_check_output(cmd, stderr, text):
        return ""

    monkeypatch.setattr(tc.subprocess, "check_output", fake_check_output)

    res = tc.delete_tc_egress_filters("eth0")
    captured = capsys.readouterr()
    assert res is None
    assert "Deleting tc filters for interface: eth0" in captured.out


def test_delete_tc_egress_filters_for_all_interfaces_calls_run_once(
    monkeypatch, capsys
):
    def fake_check_output(cmd, stderr, text):
        if cmd == ["ip", "-o", "link", "show"]:
            return "1: lo: <LOOPBACK> mtu 65536\n2: eth0: <BROADCAST> mtu 1500\n3: eth1: <BROADCAST> mtu 1500\n"
        return ""

    run_calls = []

    def fake_run(cmd: str):
        run_calls.append(cmd)
        return {"stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(tc.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(tc, "run_tc_command", fake_run)

    res = tc.delete_tc_egress_filters()
    assert res == {"stdout": "", "stderr": "", "returncode": 0}
    assert run_calls and run_calls[0].startswith("tc filter del dev ")
    captured = capsys.readouterr()
    assert "Deleting tc egress filters on all interfaces" in captured.out


# -----------------------------
# _is_port_in_range
# -----------------------------


def test__is_port_in_range_boundaries_and_outside():
    assert tc._is_port_in_range(1)
    assert tc._is_port_in_range(65535)
    assert not tc._is_port_in_range(0)
    assert not tc._is_port_in_range(70000)


# -----------------------------
# _get_ip_protocol_and_ports_filter_configuration
# -----------------------------


def test__get_ip_protocol_and_ports_filter_configuration_special_all_ones():
    assert tc._get_ip_protocol_and_ports_filter_configuration(65535, 1234, 5678) == ""


def test__get_ip_protocol_and_ports_filter_configuration_known_protocols_with_ports():
    out_tcp = tc._get_ip_protocol_and_ports_filter_configuration(
        socket.IPPROTO_TCP, 80, 12345
    )
    assert "ip_proto tcp" in out_tcp
    assert "dst_port 80" in out_tcp
    assert "src_port 12345" in out_tcp

    out_udp = tc._get_ip_protocol_and_ports_filter_configuration(
        socket.IPPROTO_UDP, 53, 0
    )
    assert "ip_proto udp" in out_udp
    assert "dst_port 53" in out_udp
    assert "src_port" not in out_udp

    out_sctp = tc._get_ip_protocol_and_ports_filter_configuration(
        socket.IPPROTO_SCTP, 5000, 6000
    )
    assert "ip_proto sctp" in out_sctp


def test__get_ip_protocol_and_ports_filter_configuration_other_8bit_protocol_hex_and_no_ports():
    out = tc._get_ip_protocol_and_ports_filter_configuration(0x01, 1234, 5678)
    assert "ip_proto 0x1" in out
    assert "dst_port" not in out
    assert "src_port" not in out


def test__get_ip_protocol_and_ports_filter_configuration_invalid_protocol_over_8bit_returns_empty():
    assert tc._get_ip_protocol_and_ports_filter_configuration(0x1FF, 1234, 5678) == ""


# -----------------------------
# create_tc_qdisc_gcl_command
# -----------------------------


def test_create_tc_qdisc_gcl_command_defaults_and_content(monkeypatch):
    fixed_now = 1234567890
    monkeypatch.setattr(tc.time, "time_ns", lambda: fixed_now)

    cmds = tc.create_tc_qdisc_gcl_command(
        interfaces=["eth0"],
        gcl=["sched-entry S 0F 500000", "sched-entry S 0E 500000"],
    )

    first = cmds[0]
    assert "tc qdisc replace dev eth0 parent root handle 100 taprio" in first
    assert "num_tc 4" in first
    assert "map 0 1 2 3 0 0 0 0 0 0 0 0 0 0 0 0" in first
    assert "queues 1@0 1@1 1@2 1@3" in first
    assert f"base-time {fixed_now}" in first
    assert "sched-entry S 0F 500000" in first
    assert "flags 0x1" in first
    assert "txtime-delay 200000" in first
    assert "clockid CLOCK_TAI" in first

    etf_cmds = [
        c for c in cmds[1:] if c.startswith("tc qdisc replace dev eth0 parent 100:")
    ]
    assert len(etf_cmds) == 4
    assert "delta 175000" in etf_cmds[0]


def test_create_tc_qdisc_gcl_command_custom_params():
    cmds = tc.create_tc_qdisc_gcl_command(
        interfaces=["enp1s0"],
        gcl=["sched-entry S 0F 100", "sched-entry S 0E 200"],
        num_tc=2,
        base_time=42,
        map_str="0 0 1 1 0 0 0 0 0 0 0 0 0 0 0 0",
        queues_str="2@0 1@1",
        handle_id="200",
        flags="0x2",
        txtime_delay=999,
        delta=888,
    )
    first = cmds[0]
    assert "dev enp1s0" in first
    assert "handle 200" in first
    assert "num_tc 2" in first
    assert "map 0 0 1 1" in first
    assert "queues 2@0 1@1" in first
    assert "base-time 42" in first
    assert "flags 0x2" in first
    assert "txtime-delay 999" in first
    etf_cmds = [
        c for c in cmds[1:] if c.startswith("tc qdisc replace dev enp1s0 parent 200:")
    ]
    assert len(etf_cmds) == 2
    assert "delta 888" in etf_cmds[0]


# -----------------------------
# Additional edge cases for filter builders
# -----------------------------


def test_create_tc_filter_commands_for_time_aware_talkers_skips_missing_interface(
    monkeypatch,
):
    monkeypatch.setattr(tc, "_clsact_exists", lambda iface: True)
    talkers = {"s": [{"source_ip": "1.2.3.4", "vlan_id": 10, "vlan_priority": 1}]}
    cmds = tc.create_tc_filter_commands_for_time_aware_talkers(talkers)
    assert cmds == []


def test_create_tc_filter_commands_for_time_aware_talkers_protocol_none_removes_layer3(
    monkeypatch,
):
    monkeypatch.setattr(tc, "_clsact_exists", lambda iface: False)
    talkers = {
        "stream1": [
            {
                "interface_name": "eth0",
                "vlan_id": 100,
                "vlan_priority": 5,
                "ip_protocol": 65535,
            }
        ]
    }
    cmds = tc.create_tc_filter_commands_for_time_aware_talkers(talkers)
    assert len(cmds) == 2
    assert "ip_proto" not in cmds[1]
    assert "dst_port" not in cmds[1]
    assert "src_port" not in cmds[1]


def test_create_tc_filter_commands_for_non_time_aware_talkers_skips_missing_interface():
    cmds = tc.create_tc_filter_commands_for_non_time_aware_talkers(
        {"x": [{"vlan_id": 1, "vlan_priority": 0}]}
    )
    assert cmds == []
