"""
Manual Test Script for Parser Validation

This script provides a manual test for the UniversalParser functionality
using real TSN configuration files. It demonstrates parsing of actual
configuration files and displays the parsed output.

Usage:
    python test_ge.py

Note: Update the file_path variable to point to your test file.
"""

from colorama import Fore, Style

from tsn_config_parser.tc_command import (
    create_tc_filter_commands_for_non_time_aware_talkers,
    create_tc_filter_commands_for_time_aware_talkers,
    create_tc_qdisc_gcl_command,
    reset_qdisc_interface,
    run_tc_command,
    show_qdisc,
    show_tc_egress_filters,
)
from tsn_config_parser.universal_parser import UniversalParser

if __name__ == "__main__":
    file_path = "./I226-1-ES-IDEAL_config_demo_4.xml"

    uparser = UniversalParser()
    docs = uparser.parse(file_path)

    # print(docs)
    # Print parsed docs count
    print(f"✅ Parsed {len(docs)} document(s)/root from {file_path}")

    # Check chronos-domain presence
    if uparser.has_chronos_domain():
        print(Fore.CYAN + "🔍 chronos-domain detected in file!" + Style.RESET_ALL)
    else:
        print(Fore.MAGENTA + "🔍 No chronos-domain found in file." + Style.RESET_ALL)

    # Later, if config.xml changes on disk
    docs = uparser.refresh(file_path)
    # print("Reloaded:", docs)

    interfaces = []
    streams = []
    gcl = []
    handle_id_dut = "100"

    ge_dict = uparser.get_dictionary_helper()  # automatically checks chronos
    if ge_dict:
        interfaces = ge_dict.get_interface_names()
        streams = ge_dict.get_stream_ids()
        # gcl = ge_dict.get_gate_control_entries()
        gcl = ge_dict.get_gate_control_entries_formatted()
        print("Interfaces:", interfaces)
        print("Stream IDs:", streams)
        print("gcl:", gcl)
    else:
        print("Chronos domain not found. No dictionary available.")

    # interfaces = ['enp170s0']  # Override interface for testing
    # Reset qdisc first
    for iface in interfaces:
        print(f"=== Resetting qdisc for {iface}...=== ")
        reset_result = reset_qdisc_interface(iface)
        print("Reset result:", reset_result)
        print("-" * 40)

    # Generate commands
    # Don't pass base_time -> defaults to current system time
    gcl_cmds = create_tc_qdisc_gcl_command(
        interfaces,
        gcl,
        num_tc=4,
        map_str="0 1 2 3 0 0 0 0 0 0 0 0 0 0 0 0",
        queues_str="1@0 1@1 1@2 1@3",
        handle_id=handle_id_dut,
    )
    # print("tc generated: ", cmds)

    # Show and run each command
    for c in gcl_cmds:
        print("=== Generated GCL command: ===\n", c)
        result = run_tc_command(c)
        print("Execution result:", result["returncode"])
        print("-" * 40)

    # Show qdisc state after config
    for iface in interfaces:
        print(f"=== Show qdisc state for {iface}: ===")
        qdisc_state = show_qdisc(iface)
        print(qdisc_state["stdout"])
        print("-" * 40)

    # Get all stream IDs
    stream_ids = ge_dict.get_stream_ids()  # pyright: ignore[reportOptionalMemberAccess]
    print("===Stream IDs:", stream_ids)

    # Print talker VLAN info for each stream
    for sid in stream_ids:
        print(f"\n===Stream {sid}:")
        for line in ge_dict.get_talker_vlan_info_by_stream(sid):
            print(" ", line)

    # Call the new function
    time_aware_info = (
        ge_dict.get_all_time_aware_talker_vlan_info()
    )  # pyright: ignore[reportOptionalMemberAccess]

    # Print time-aware offsets grouped by Stream ID
    for stream_id, entries in time_aware_info.items():
        print(f"\ntime_aware Stream ID: {stream_id}")
        for entry in entries:
            print(
                f"  MAC: {entry['mac']}, IF: {entry['interface']}, VLAN: {entry['vlan']}, "
                f"PCP: {entry['pcp']}, OFFSET: {entry['time-aware-offset']}"
            )

    # 🆕 Call the new function
    all_talker_info = (
        ge_dict.get_all_talker_stream_info()
    )  # pyright: ignore[reportOptionalMemberAccess]

    # print("\n=== All Talker Stream Information ===")
    # for stream_id, talkers in all_talker_info.items():
    #    print(f"\nStream ID: {stream_id}")
    #    for t in talkers:
    #        print(
    #            f"  IF: {t['interface_name']}, MAC: {t['interface_mac']}, "
    #            f"SrcMAC: {t['source_mac']}, DstMAC: {t['destination_mac']}, "
    #            f"SrcIP: {t['source_ip']}, DstIP: {t['destination_ip']}, Port: {t['destination_port']}, "
    #            f"VLAN_Tag: {t['vlan_tag']}, VLAN_ID: {t['vlan_id']}, PCP: {t['vlan_priority']}, "
    #            f"TimeAware: {t['time_aware']}, Offset: {t['time_aware_offset']}, "
    #            f"Earliest: {t['earliest_transmit_offset']}, Latest: {t['latest_transmit_offset']}"
    #        )

    # -------------------------------------------------------------
    # 🆕 VLAN + Time-Aware / Non-Time-Aware Filtering Tests
    # -------------------------------------------------------------

    # --- VLAN-tagged AND time-aware talkers ---
    time_aware_vlan_talkers = ge_dict.get_vlan_tagged_time_aware_talker_info(
        all_talker_info
    )  # pyright: ignore[reportOptionalMemberAccess]

    print("\n=== VLAN-Tagged & Time-Aware Talker Streams ===")
    if not time_aware_vlan_talkers:
        print("No VLAN-tagged time-aware talkers found.")
    else:
        for stream_id, talkers in time_aware_vlan_talkers.items():
            print(f"\nStream ID: {stream_id}")
            for t in talkers:
                print(
                    f"  IF: {t['interface_name']}, MAC: {t['interface_mac']}, "
                    f"SrcMAC: {t['source_mac']}, DstMAC: {t['destination_mac']}, "
                    f"SrcIP: {t['source_ip']}, DstIP: {t['destination_ip']}, Port: {t['destination_port']}, "
                    f"VLAN_Tag: {t['vlan_tag']}, VLAN_ID: {t['vlan_id']}, PCP: {t['vlan_priority']}, "
                    f"TimeAware: {t['time_aware']}, Offset: {t['time_aware_offset']}, "
                    f"Earliest: {t['earliest_transmit_offset']}, Latest: {t['latest_transmit_offset']}"
                )

    # --- VLAN-tagged AND non-time-aware talkers ---
    non_time_aware_vlan_talkers = ge_dict.get_vlan_tagged_non_time_aware_talker_info(
        all_talker_info
    )  # pyright: ignore[reportOptionalMemberAccess]

    print("\n=== VLAN-Tagged & Non-Time-Aware Talker Streams ===")
    if not non_time_aware_vlan_talkers:
        print("No VLAN-tagged non-time-aware talkers found.")
    else:
        for stream_id, talkers in non_time_aware_vlan_talkers.items():
            print(f"\nStream ID: {stream_id}")
            for t in talkers:
                print(
                    f"  IF: {t['interface_name']}, MAC: {t['interface_mac']}, "
                    f"SrcMAC: {t['source_mac']}, DstMAC: {t['destination_mac']}, "
                    f"SrcIP: {t['source_ip']}, DstIP: {t['destination_ip']}, Port: {t['destination_port']}, "
                    f"VLAN_Tag: {t['vlan_tag']}, VLAN_ID: {t['vlan_id']}, PCP: {t['vlan_priority']}, "
                    f"TimeAware: {t['time_aware']}, Offset: {t['time_aware_offset']}, "
                    f"Earliest: {t['earliest_transmit_offset']}, Latest: {t['latest_transmit_offset']}"
                )

    time_aware_vlan_commands = create_tc_filter_commands_for_time_aware_talkers(
        time_aware_vlan_talkers
    )

    print("\n=== Generated smart tc filter [TIME-AWARE] commands ===")
    for cmd in time_aware_vlan_commands:
        print(cmd)
        result = run_tc_command(cmd)
        print("Execution result:", result["returncode"])
        print("-" * 40)

    # Generate tc filter commands
    non_time_aware_vlan_commands = create_tc_filter_commands_for_non_time_aware_talkers(
        non_time_aware_vlan_talkers
    )

    print("\n=== Generated smart tc filter [NON-TIME-AWARE] commands ===")
    for cmd in non_time_aware_vlan_commands:
        print(cmd)
        result = run_tc_command(cmd)
        print("Execution result:", result["returncode"])
        print("-" * 40)

    # -------------------------------------------------------------
    # 4️⃣ Example B: Get time-aware offsets for a single stream ID
    # -------------------------------------------------------------
    stream_id = "de-ad-be-ef-00-01:00-05"
    offsets = ge_dict.get_time_aware_offsets_by_stream_id(
        stream_id
    )  # pyright: ignore[reportOptionalMemberAccess]

    print("\n=== Time-Aware Offsets for a Single Stream ===")
    if offsets:
        print(f"Stream ID: {stream_id} -> Offsets: {offsets}")
    else:
        print(f"No time-aware offsets found for stream {stream_id}.")

    print("\n================ show tc egress filter commands ===")
    # Show egress filter state after config
    for iface in interfaces:
        print(f"egress filter state for {iface}:")
        filter_state = show_tc_egress_filters(iface)
        print(filter_state["stdout"])
        print("-" * 40)

    # for iface in interfaces:
    #    delete_tc_egress_filters(iface)
