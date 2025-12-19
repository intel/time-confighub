# File: tc_command.py
"""
tc_command
==========

This module provides helper functions for generating and executing
``tc qdisc taprio`` commands with Gate Control List (GCL) scheduling.
It is intended for Time-Sensitive Networking (TSN) configurations where
deterministic transmission scheduling is required.

Example
-------

.. code-block:: python

    from tc_command import create_tc_qdisc_gcl_command, run_tc_command

    interfaces = ["enp170s0"]
    gcl = ["sched-entry S 0F 500000", "sched-entry S 0E 500000"]

    cmds = create_tc_qdisc_gcl_command(
        interfaces,
        gcl,
        num_tc=4,
        map_str="0 1 2 3 0 0 0 0 0 0 0 0 0 0 0 0",
        queues_str="1@0 1@1 1@2 1@3"
    )

    for c in cmds:
        print(run_tc_command(c))
"""

import socket
import subprocess
import time
from typing import Any, Dict, List, Optional

__all__ = ["create_tc_qdisc_gcl_command", "run_tc_command"]

safety_delay = 1  # seconds , this will be replaced in the i226 hw file.
current_chain_number = 0  # Global chain number tracker

# TODO: Wrap all functions into a class for better state management with Device context
# TODO: Migrate to time_config_hub.commands.tc_command


def create_tc_qdisc_gcl_command(
    interfaces: List[str],
    gcl: List[str],
    num_tc: int = 4,
    base_time: Optional[int] = None,
    map_str: Optional[str] = None,
    queues_str: Optional[str] = None,
    handle_id: Optional[str] = None,
    flags: str = "0x1",
    txtime_delay: int = 200000,
    delta: int = 175000,
) -> List[str]:
    """
    Create ``tc qdisc taprio`` commands with Gate Control List (GCL) entries.

    :param interfaces: List of network interfaces (e.g., ``["enp170s0"]``).
    :type interfaces: List[str]
    :param gcl: List of GCL (Gate Control List) entries, such as
                ``["sched-entry S 0F 500000", "sched-entry S 0E 500000"]``.
    :type gcl: List[str]
    :param num_tc: Number of traffic classes to configure. Defaults to 4.
    :type num_tc: int
    :param base_time: Base time in nanoseconds. If ``None``, the current system
                      time is used (from :func:`time.time_ns`).
    :type base_time: int, optional
    :param map_str: The traffic class mapping string. If ``None``, defaults to
                    ``"0 1 2 3 0 0 0 0 0 0 0 0 0 0 0 0"``.
    :type map_str: str, optional
    :param queues_str: The queue assignment string. If ``None``, defaults to
                       ``"1@0 1@1 1@2 1@3"``.
    :type queues_str: str, optional
    :param handle_id: unique identifier for taprio tc qdisc. If ``None``, defaults to
                       ``"100"``.
    :type handle_id: str, optional
    :param flags: Flags value to pass to ``taprio`` (default: ``"0x2"``).
    :type flags: str

    :return: A list of complete ``tc qdisc taprio`` commands as multi-line strings.
    :rtype: List[str]
    """
    if base_time is None:
        base_time = time.time_ns()  # default to "now"

    if map_str is None:
        map_str = "0 1 2 3" + " 0" * 12

    if queues_str is None:
        queues_str = "1@0 1@1 1@2 1@3"

    if handle_id is None:
        handle_id = "100"

    commands = []

    for iface in interfaces:
        # Start building command
        cmd_lines = [
            f"tc qdisc replace dev {iface} parent root handle {handle_id} taprio",
            f" num_tc {num_tc} map {map_str}",
            f" queues {queues_str}",
            f" base-time {base_time}",
        ]

        # Add GCL entries
        for entry in gcl:
            cmd_lines.append(f" {entry} ")

        # Add flags
        cmd_lines.append(f"flags {flags}")

        # Add txtime-delay
        cmd_lines.append(f"txtime-delay {txtime_delay} ")

        # Add flags
        cmd_lines.append("clockid CLOCK_TAI ")
        commands.append(" ".join(cmd_lines))

        # Enrol additional tc configuration for hybrid (SW Qbv + ETF LaunchTime)
        # Add ETF qdisc for each traffic class (1-based index)
        for q in range(1, num_tc + 1):
            commands.append(
                f"tc qdisc replace dev {iface} parent {handle_id}:{q} etf "
                f"skip_sock_check offload delta {delta} clockid CLOCK_TAI "
            )

    return commands


def run_tc_command(command: str) -> Dict[str, Any]:
    """
    Execute a ``tc`` command in the system shell.

    :param command: The full ``tc`` command string to execute.
    :type command: str

    :return: A dictionary containing:
             - ``stdout``: Standard output of the command
             - ``stderr``: Standard error of the command
             - ``returncode``: Exit status code (0 means success)
    :rtype: Dict[str, Any]
    """
    process = subprocess.run(
        f"sudo {command}", shell=True, capture_output=True, text=True
    )

    # Safety delay
    time.sleep(safety_delay)

    return {
        "stdout": process.stdout.strip(),
        "stderr": process.stderr.strip(),
        "returncode": process.returncode,
    }


def reset_root_qdisc_interface(interface: str) -> Dict[str, Dict[str, str]]:
    """
    Reset the root qdisc (queue discipline) for a specified network interface.

    This function checks if a root qdisc exists on the given interface. If no root qdisc
    is found, it returns a success response. Otherwise, it deletes the root qdisc using
    the tc (traffic control) command and applies a safety delay before returning.

    Args:
        interface (str): The name of the network interface (e.g., 'eth0', 'enp0s3').

    Returns:
        Dict[str, Dict[str, str]]: A dict with the command execution results with keys:
            - 'stdout' (str): Standard output from the tc command.
            - 'stderr' (str): Standard error output from the tc command.
            - 'returncode' (int): The return code of the command (0 for success).

    Note:
        A safety delay is applied after deleting the qdisc to ensure the system
        has time to process the changes.
    """

    output = show_qdisc(interface)
    if "root" in output["stdout"]:
        cmd = f"tc qdisc del dev {interface} root"
        res = run_tc_command(cmd)
        # Safety delay
        time.sleep(safety_delay)
    # No qdisc exists, return success
    res = {"stdout": "", "stderr": "", "returncode": 0}

    return res


def reset_clsact_qdisc_interface(interface: str) -> Dict[str, str]:
    """
    Reset the clsact qdisc on a specific interface by deleting
    the clsact qdisc. This function is idempotent:
    if the qdisc does not exist, the error is ignored.

    :param interface: The network interface to reset (e.g., ``"enp170s0"``).
    :type interface: str

    :return: A dictionary containing:
             - ``stdout``: Standard output of the command
             - ``stderr``: Standard error of the command
             - ``returncode``: Exit status code (0 means success)
    :rtype: Dict[str, str]

    Example
    -------
    .. code-block:: python

        from tc_command import reset_clsact_qdisc_interface

        result = reset_clsact_qdisc_interface("enp170s0")
        print(result)
    """
    output = show_qdisc(interface)
    if "clsact" in output["stdout"]:
        cmd = f"tc qdisc del dev {interface} clsact"
        res = run_tc_command(cmd)
        # Safety delay
        time.sleep(safety_delay)
    # No clsact qdisc exists, return success
    res = {"stdout": "", "stderr": "", "returncode": 0}
    return res


def reset_egress_filter_interface(interface: str) -> Dict[str, str]:
    """
    Reset all tc filters on a specific interface by deleting
    all egress filters. This function is idempotent:
    if the filters do not exist, the error is ignored.

    :param interface: The network interface to reset (e.g., ``"enp170s0"``).
    :type interface: str

    :return: A dictionary containing:
             - ``stdout``: Standard output of the command
             - ``stderr``: Standard error of the command
             - ``returncode``: Exit status code (0 means success)
    :rtype: Dict[str, str]

    Example
    -------
    .. code-block:: python

        from tc_command import reset_filter_interface

        result = reset_filter_interface("enp170s0")
        print(result)
    """
    output = show_tc_egress_filters(interface)
    if "filter" in output["stdout"]:
        cmd = f"tc filter del dev {interface} egress"
        res = run_tc_command(cmd)
        # Safety delay
        time.sleep(safety_delay)
    # No egress filters exist, return success
    res = {"stdout": "", "stderr": "", "returncode": 0}

    return res


def reset_qdisc_interface(interface: str) -> Dict[str, Any]:
    """Reset tc configuration on an interface.

    This is a convenience wrapper used by demos/scripts.

    It removes, in this order:

    1. Egress filters
    2. ``clsact`` qdisc
    3. Root qdisc

    The function is intended to be idempotent: if a qdisc/filter does not
    exist, it will be skipped.

    :param str interface: Network interface name (e.g. ``"eth0"``)
    :return: A dict with per-step results.
    :rtype: Dict[str, Any]
    """

    def _success_result() -> Dict[str, str]:
        return {"stdout": "", "stderr": "", "returncode": 0}

    results: Dict[str, Any] = {
        "interface": interface,
        "egress_filters": _success_result(),
        "clsact": _success_result(),
        "root": _success_result(),
    }

    # 1) Egress filters
    try:
        filters_state = show_tc_egress_filters(interface)
        if filters_state.get("stdout") and "filter" in filters_state["stdout"]:
            results["egress_filters"] = run_tc_command(
                f"tc filter del dev {interface} egress"
            )
    except Exception as exc:
        results["egress_filters"] = {
            "stdout": "",
            "stderr": str(exc),
            "returncode": 1,
        }

    # 2) clsact qdisc
    try:
        qdisc_state = show_qdisc(interface)
        if qdisc_state.get("stdout") and "clsact" in qdisc_state["stdout"]:
            results["clsact"] = run_tc_command(f"tc qdisc del dev {interface} clsact")
    except Exception as exc:
        results["clsact"] = {
            "stdout": "",
            "stderr": str(exc),
            "returncode": 1,
        }

    # 3) Root qdisc
    try:
        qdisc_state = show_qdisc(interface)
        if qdisc_state.get("stdout") and "root" in qdisc_state["stdout"]:
            results["root"] = run_tc_command(f"tc qdisc del dev {interface} root")
    except Exception as exc:
        results["root"] = {
            "stdout": "",
            "stderr": str(exc),
            "returncode": 1,
        }

    return results


def show_qdisc(interface: str) -> Dict[str, str]:
    """
    Show the qdisc configuration of a given interface.

    This runs ``sudo tc qdisc show dev <interface>`` and returns the result.

    :param interface: The network interface to inspect (e.g., ``"enp170s0"``).
    :type interface: str

    :return: A dictionary containing:
             - ``stdout``: Standard output of the command (the qdisc configuration)
             - ``stderr``: Standard error of the command
             - ``returncode``: Exit status code (0 means success)
    :rtype: Dict[str, str]

    Example
    -------
    .. code-block:: python

        from tc_command import show_qdisc

        result = show_qdisc("enp170s0")
        print(result["stdout"])
    """
    cmd = f"tc qdisc show dev {interface}"
    return run_tc_command(cmd)


def show_tc_egress_filters(interface: str) -> Dict[str, str]:
    """
    Display all egress filters currently configured ``tc filters`` on the interface.

    This helper runs the ``tc filter show`` command for one
    network interfaces, showing the filters configured in the kernel.

    :param interface: The network interface to inspect (e.g., ``"enp170s0"``).
    :type interface: str

    :return: A dictionary containing:
             - ``stdout``: Standard output of the command (the qdisc configuration)
             - ``stderr``: Standard error of the command
             - ``returncode``: Exit status code (0 means success)
    :rtype: Dict[str, str]

    Example
    -------
    .. code-block:: python

        from tc_command import show_tc_egress_filters

        result = show_tc_egress_filters("enp170s0")
        print(result["stdout"])
    """
    cmd = f"tc filter show dev {interface} egress"
    return run_tc_command(cmd)


def delete_tc_egress_filters(
    interface: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Delete all configured egress ``tc filters`` for a given interface, or for all interfaces if none is specified.

    This helper executes the ``tc filter delete`` command to remove all
    filters under a given qdisc parent. If no interface is specified, it
    attempts to clear filters from all available interfaces returned by
    ``ip link show``.

    .. warning::
       This operation is destructive — it permanently removes all
       existing tc filter rules. Use with caution.

    Parameters
    ----------
    interface : Optional[str], optional
        The name of the network interface (e.g., ``"eth0"``). If ``None``,
        filters are deleted for all available interfaces.

    Returns
    -------
    Optional[Dict[str, Any]]
        A dictionary containing the result of the deletion command with
        ``stdout``, ``stderr``, and ``returncode`` keys, or ``None`` if
        a single interface was specified.

    Examples
    --------
    >>> from tc_command import delete_tc_filters
    >>> # Delete filters for one interface
    >>> delete_tc_egress_filters("eth0")
    🔧 Deleting tc filters for interface: eth0
    ✅ Successfully deleted filters on eth0 (parent 100:)

    >>> # Delete filters for all interfaces
    >>> delete_tc_egress_filters()
    🔧 Deleting tc filters on all interfaces...
    Interface: eth0 -> ✅ Deleted
    Interface: eth1 -> ⚠️ No filters found
    """

    def _run_cmd(cmd: list) -> str:
        """Run a system command and return its output or error as text."""
        print(cmd)
        try:
            return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        except subprocess.CalledProcessError as e:
            return e.output.strip()

    if interface:
        print(f"🔧 Deleting tc filters for interface: {interface}")
        output = _run_cmd(["tc", "filter", "del", "dev", interface, "egress"])
        if not output.strip():
            print(f"✅ Successfully deleted filters on {interface} (egress)")
        else:
            print(f"⚠️ {output.strip()}")
        return None

    # No interface provided — clear all interfaces
    print("🔧 Deleting tc egress filters on all interfaces...\n")

    link_output = _run_cmd(["ip", "-o", "link", "show"])
    interfaces = [
        line.split(":")[1].strip() for line in link_output.splitlines() if ": " in line
    ]

    for iface in interfaces:
        print(f"Interface: {iface}")
        cmd = f"tc filter del dev {iface} egress"
        print("-" * 50)
        return run_tc_command(cmd)


def _clsact_exists(interface: str) -> bool:
    """
    Check whether a ``clsact`` qdisc is already attached to a given network interface.

    This function uses the ``tc qdisc show dev <interface>`` command to verify
    if a ``clsact`` qdisc is already configured on the specified interface. It helps
    prevent duplicate qdisc creation errors such as:

    .. code-block:: text

        Error: "clsact" is a duplicate parent ID

    :param interface:
        The name of the network interface to inspect.
    :type interface: str
    :return:
        ``True`` if a ``clsact`` qdisc is already attached, otherwise ``False``.
    :rtype: bool
    """
    try:
        result = subprocess.run(
            ["tc", "qdisc", "show", "dev", interface],
            capture_output=True,
            text=True,
            check=False,
        )
        return "clsact" in result.stdout
    except Exception:
        return False


def _is_port_in_range(port):
    """
    Checks if a given port number is within the valid TCP port range (1-65535).

    :param port: The port number to check.
    :type port: int
    :raises TypeError: if `port` is not an integer.
    :returns: True if the port is in range, False otherwise.
    :rtype: bool
    """
    return 1 <= port <= 65535


def _get_ip_protocol_and_ports_filter_configuration(
    protocol_number, destination_port, source_port
):
    """
    Returns the name of the protocol (tcp,udp,sctp) corresponding to the given
    protocol number. Defaults to 'udp' if the number does not match.
    tc filter flower for dest_port will only support tcp,udp and sctp.

    Refer : https://man7.org/linux/man-pages/man8/tc-flower.8.html

    :param unsigned int protocol_number:
        protocol_number (int): The IP protocol number.
    :param unsigned int destination_port:
        destination_port (int): The destination port number.
    :param unsigned int source_port:
        source_port (int): The source port number.

    :returns: a string to be used in the tc filter command
    :rtype: str
    """
    use_port = True
    protocol_name = ""
    protocol_port_cmd = ""

    if protocol_number == 65535:
        # "IPv4 Protocol (e.g. UDP). The special value of all 1’s (FFFF hex)
        # represents ’None’, meaning that protocol, source-port, and
        # destination-port are ignored for purposes of Stream identification
        return ""
    elif protocol_number == socket.IPPROTO_TCP:
        protocol_name = "tcp"
    elif protocol_number == socket.IPPROTO_UDP:
        protocol_name = "udp"
    elif protocol_number == socket.IPPROTO_SCTP:
        protocol_name = "sctp"
    else:
        if protocol_number <= 0xFF:
            # IANA protocol is over 8 bit.
            # For non-other than tcp, udp, sctp,
            # we will not use the ports in the command.
            # we will only pass the ip protocol number in hex
            protocol_name = hex(protocol_number)
            use_port = False
        else:
            # Number bigger than 8 bit will not be used.
            return ""
    if protocol_name != "":
        protocol_port_cmd = f"ip_proto {protocol_name} "
    if (_is_port_in_range(destination_port)) and use_port:
        protocol_port_cmd += f"dst_port {destination_port} "
    if (_is_port_in_range(source_port)) and use_port:
        protocol_port_cmd += f"src_port {source_port} "

    return protocol_port_cmd


def create_tc_filter_commands_for_time_aware_talkers(
    vlan_time_aware_info: Dict[str, List[Dict[str, Any]]],
) -> List[str]:
    """
    Generate ``tc filter`` commands for VLAN-tagged, time-aware talkers with
    automatic chain number increment and dynamic ``clsact`` detection.

    This function consumes the output from
    :meth:`GE_Dictionary.get_vlan_tagged_time_aware_talker_info`
    and generates two pipe ``tc filter`` rules per talker entry:

    1. **IP chain (chain N)** — Matches traffic based on L2/L3 attributes
       (e.g. MAC, IP, port), push VLAN ID and priority, maps the vlan priority to
       socket buffer priority (``SO_PRIORITY``) using the ``skbedit`` action.

    Before creating any filters, the function checks whether the ``clsact``
    qdisc is already attached to the target interface. If not, it automatically
    adds one to enable egress filtering.

    **Example Output**
    
    .. code-block:: bash

        tc qdisc add dev enp170s0 clsact

        tc filter add dev enp170s0 egress protocol ip flower \
            src_mac aa:bb:cc:dd:ee:ff dst_mac 11:22:33:44:55:66 \
            src_ip 192.168.1.10 dst_ip 192.168.1.20 dst_port 8080 \
            action vlan push id 22 protocol 802.1Q priority 3 pipe \
            action skbedit priority 3

    :param vlan_time_aware_info:
        Parsed talker information from 
        :meth:`GE_Dictionary.get_vlan_tagged_time_aware_talker_info`, 
        where each key is a stream ID and each value is a list of talker dictionaries.
    :type vlan_time_aware_info: Dict[str, List[Dict[str, Any]]]

    :return:
        A list of fully formatted ``tc`` command strings ready for execution using
        :func:`run_tc_command`.
    :rtype: List[str]

    :raises subprocess.SubprocessError:
        If ``tc qdisc show dev`` command fails unexpectedly.

    **Implementation Details**
    
    - Automatically ensures ``clsact`` exists per interface.
    - Uses separate chain pairs for each talker (N and N+1).
    - Dynamically builds commands only with fields available in the dataset.
    - Safe to run multiple times (idempotent regarding ``clsact`` setup).
    """
    commands: List[str] = []

    processed_ifaces = set()

    for stream_id, talkers in vlan_time_aware_info.items():
        for talker in talkers:
            interface = talker.get("interface_name")
            if not interface:
                continue

            src_mac = talker.get("source_mac")
            dst_mac = talker.get("destination_mac")
            src_ip = talker.get("source_ip")
            dst_ip = talker.get("destination_ip")
            dst_port = talker.get("destination_port")
            src_port = talker.get("source_port")
            vlan_id = talker.get("vlan_id")
            vlan_prio = talker.get("vlan_priority")
            ip_proto = talker.get("ip_protocol")

            # Safe conversions
            proto_num = int(ip_proto) if ip_proto is not None else 65535
            dst_port_num = int(dst_port) if dst_port is not None else 0
            src_port_num = int(src_port) if src_port is not None else 0

            # --- Automatically add clsact if missing ---
            if interface not in processed_ifaces:
                if not _clsact_exists(interface):
                    commands.append(f"tc qdisc add dev {interface} clsact")
                processed_ifaces.add(interface)

            # --- Chain N: IP filter rule ---
            cmd_ip = f"tc filter add dev {interface} egress protocol ip flower "

            layer3_proto_cmd = _get_ip_protocol_and_ports_filter_configuration(
                proto_num, dst_port_num, src_port_num
            )

            if src_mac:
                cmd_ip += f"src_mac {src_mac} "
            if dst_mac:
                cmd_ip += f"dst_mac {dst_mac} "
            if src_ip:
                cmd_ip += f"src_ip {src_ip} "
            if dst_ip:
                cmd_ip += f"dst_ip {dst_ip} "
            if layer3_proto_cmd != "":
                cmd_ip += f"{layer3_proto_cmd} "
            cmd_ip += (
                f"action vlan push id {vlan_id} protocol 802.1Q priority {vlan_prio} pipe "
                f"action skbedit priority {vlan_prio}"
            )
            commands.append(cmd_ip.strip())

    return commands


def create_tc_filter_commands_for_non_time_aware_talkers(
    vlan_non_time_aware_info: Dict[str, List[Dict[str, Any]]],
) -> List[str]:
    """
    Generate ``tc filter`` commands for VLAN-tagged, non-time-aware talkers.

    This function consumes the output from
    :meth:`GE_Dictionary.get_vlan_tagged_non_time_aware_talker_info`
    and produces one ``tc filter`` rule per talker that *pushes* a VLAN tag.

    **Example Output**
    
    .. code-block:: bash

        tc filter add dev eth0 egress protocol ip flower \
            src_mac aa:bb:cc:dd:ee:ff \
            dst_mac 11:22:33:44:55:66 \
            src_ip 192.168.1.10 \
            dst_ip 192.168.1.20 \
            action vlan push id 100 prio 3 protocol 802.1Q

    :param vlan_non_time_aware_info:
        Output from :meth:`GE_Dictionary.get_vlan_tagged_non_time_aware_talker_info`.
        Each key is a stream ID, and each value is a list of talker dictionaries.
    :type vlan_non_time_aware_info: Dict[str, List[Dict[str, Any]]]

    :return:
        A list of ``tc`` command strings, one per talker.
    :rtype: List[str]

    :raises KeyError:
        If required VLAN attributes are missing from a talker entry.

    **Implementation Notes**
    
    - Builds IP-based flower filters that push VLAN headers.
    - Uses ``action vlan push`` rather than ``modify``.
    - Dynamically includes only fields that exist in the talker data.
    """
    commands: List[str] = []

    for stream_id, talkers in vlan_non_time_aware_info.items():
        for talker in talkers:
            interface = talker.get("interface_name")
            if not interface:
                continue

            src_mac = talker.get("source_mac")
            dst_mac = talker.get("destination_mac")
            src_ip = talker.get("source_ip")
            dst_ip = talker.get("destination_ip")
            ip_proto = talker.get("ip_protocol")
            dst_port = talker.get("destination_port")
            src_port = talker.get("source_port")
            vlan_id = talker.get("vlan_id")
            vlan_prio = talker.get("vlan_priority")

            # Safe conversions
            proto_num = int(ip_proto) if ip_proto is not None else 65535
            dst_port_num = int(dst_port) if dst_port is not None else 0
            src_port_num = int(src_port) if src_port is not None else 0

            layer3_proto_cmd = _get_ip_protocol_and_ports_filter_configuration(
                proto_num, dst_port_num, src_port_num
            )

            # Base command
            cmd = f"tc filter add dev {interface} egress protocol ip flower "
            if src_mac:
                cmd += f"src_mac {src_mac} "
            if dst_mac:
                cmd += f"dst_mac {dst_mac} "
            if src_ip:
                cmd += f"src_ip {src_ip} "
            if dst_ip:
                cmd += f"dst_ip {dst_ip} "
            if layer3_proto_cmd != "":
                cmd += f"{layer3_proto_cmd} "
            # VLAN push action
            cmd += (
                f"action vlan push id {vlan_id} protocol 802.1Q priority {vlan_prio} pipe "
                f"action skbedit priority {vlan_prio}"
            )

            commands.append(cmd.strip())

    return commands
