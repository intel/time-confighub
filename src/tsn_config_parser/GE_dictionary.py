# File: GE_Dictionary.py
"""
GE Dictionary Helper for TSN XML/YAML/JSON configuration.
"""

from typing import Any, Dict, List


class GE_Dictionary:
    """Helper class to extract specific TSN configuration values."""

    def __init__(self, documents: List[Dict[str, Any]]):
        self.documents = documents

    def get_interface_names(self) -> List[str]:
        """Return all interface names under <interfaces>."""
        names: List[str] = []
        for doc in self.documents:
            interfaces_section = self._find_key(doc, "interfaces")
            if interfaces_section:
                interface_list = interfaces_section.get("interface")
                if not interface_list:
                    continue
                if not isinstance(interface_list, list):
                    interface_list = [interface_list]
                for iface in interface_list:
                    name_entry = iface.get("name")
                    if name_entry:
                        if isinstance(name_entry, dict) and "#text" in name_entry:
                            names.append(name_entry["#text"])
                        else:
                            names.append(str(name_entry))
        return names

    def get_stream_ids(self) -> List[str]:
        """Return all <stream-id> values in documents."""
        stream_ids: List[str] = []
        for doc in self.documents:
            streams = self._find_all_keys(doc, "stream-id")
            stream_ids.extend(
                [
                    str(s["#text"] if isinstance(s, dict) and "#text" in s else s)
                    for s in streams
                ]
            )
        return stream_ids

    def get_talker_vlan_info(self) -> Dict[str, List[Dict[str, str]]]:
        """Return dict of stream-id -> list of talker info dicts."""
        result = {}

        for doc in self.documents:
            domains = doc.get("cnc-config", {}).get("domain", [])
            if not isinstance(domains, list):
                domains = [domains]

            for domain in domains:
                cucs = domain.get("cuc", [])
                if not isinstance(cucs, list):
                    cucs = [cucs]

                for cuc in cucs:
                    streams = cuc.get("stream", [])
                    if not isinstance(streams, list):
                        streams = [streams]

                    for stream in streams:
                        stream_id = stream.get("stream-id")
                        if stream_id not in self.get_stream_ids():
                            continue  # safeguard

                        talkers_info = []
                        talkers = stream.get("talker", [])
                        if not isinstance(talkers, list):
                            talkers = [talkers]

                        for talker in talkers:
                            mac = talker.get("end-station-interfaces", {}).get(
                                "mac-address"
                            )

                            iface_cfg = talker.get("interface-configuration", {})
                            iface_list = iface_cfg.get("interface-list", {})
                            iface_name = iface_list.get("interface-name")

                            vlan_id = None
                            pcp = None
                            cfg_lists = iface_list.get("config-list", [])
                            if not isinstance(cfg_lists, list):
                                cfg_lists = [cfg_lists]

                            for cfg in cfg_lists:
                                vlan_tag = cfg.get("ieee802-vlan-tag")
                                if vlan_tag:
                                    vlan_id = vlan_tag.get("vlan-id")
                                    pcp = vlan_tag.get("priority-code-point")

                            talkers_info.append(
                                {
                                    "mac": mac,
                                    "interface": iface_name,
                                    "vlan": vlan_id,
                                    "pcp": pcp,
                                }
                            )

                        result[stream_id] = talkers_info
        return result

    def get_talker_vlan_info_by_stream(self, stream_id: str) -> List[str]:
        """
        Return formatted talker VLAN info for a given stream-id.
        Reuses get_stream_ids() to ensure valid input.
        """
        if stream_id not in self.get_stream_ids():
            return [f"Stream ID '{stream_id}' not found."]

        all_info = self.get_talker_vlan_info()
        talkers = all_info.get(stream_id, [])

        return [
            f"MAC: {t['mac']}, IF: {t['interface']}, VLAN: {t['vlan']}, PCP: {t['pcp']}"
            for t in talkers
        ]

    def get_all_time_aware_talker_vlan_info(self) -> Dict[str, List[Dict[str, str]]]:
        """
        Retrieve VLAN and PCP information for all talkers that include
        a ``<time-aware-offset>`` entry in their interface configuration.

        This function reuses the logic from :meth:`get_talker_vlan_info`
        and filters only those streams that contain a ``<time-aware-offset>``
        element within their ``<config-list>`` section. Each result entry
        includes the MAC address, interface name, VLAN ID, PCP value, and
        the corresponding time-aware offset.

        Returns
        -------
        Dict[str, List[Dict[str, str]]]
            A dictionary where each key is a ``stream-id`` string, and each
            value is a list of dictionaries. Each dictionary includes:

            - ``mac`` : str
            The MAC address of the talker.
            - ``interface`` : str
            The interface name (e.g., ``eth0``).
            - ``vlan`` : str
            The VLAN ID associated with the stream.
            - ``pcp`` : str
            The priority code point value.
            - ``time-aware-offset`` : str
            The time-aware transmission offset value, in nanoseconds or
            microseconds depending on the configuration.

        Examples
        --------
        >>> ge = GE_Dictionary(parsed_docs)
        >>> ge.get_all_time_aware_talker_vlan_info()
        {
            "de-ad-be-ef-00-01:00-05": [
                {
                    "mac": "DE-AD-BE-EF-00-01",
                    "interface": "eth0",
                    "vlan": "22",
                    "pcp": "2",
                    "time-aware-offset": "78600"
                }
            ]
        }
        """
        result: Dict[str, List[Dict[str, str]]] = {}

        for doc in self.documents:
            domains = doc.get("cnc-config", {}).get("domain", [])
            if not isinstance(domains, list):
                domains = [domains]

            for domain in domains:
                cucs = domain.get("cuc", [])
                if not isinstance(cucs, list):
                    cucs = [cucs]

                for cuc in cucs:
                    streams = cuc.get("stream", [])
                    if not isinstance(streams, list):
                        streams = [streams]

                    for stream in streams:
                        stream_id = stream.get("stream-id")
                        if not stream_id:
                            continue

                        talkers = stream.get("talker", [])
                        if not isinstance(talkers, list):
                            talkers = [talkers]

                        for talker in talkers:
                            mac = talker.get("end-station-interfaces", {}).get(
                                "mac-address"
                            )

                            iface_cfg = talker.get("interface-configuration", {})
                            iface_list = iface_cfg.get("interface-list", {})
                            iface_name = iface_list.get("interface-name")

                            cfg_lists = iface_list.get("config-list", [])
                            if not isinstance(cfg_lists, list):
                                cfg_lists = [cfg_lists]

                            # Look for time-aware-offset entries
                            time_offsets = [
                                cfg.get("time-aware-offset")
                                for cfg in cfg_lists
                                if "time-aware-offset" in cfg
                            ]
                            if not time_offsets:
                                continue  # Skip talkers without offset

                            vlan_id = None
                            pcp = None
                            for cfg in cfg_lists:
                                vlan_tag = cfg.get("ieee802-vlan-tag")
                                if vlan_tag:
                                    vlan_id = vlan_tag.get("vlan-id")
                                    pcp = vlan_tag.get("priority-code-point")

                            for offset in time_offsets:
                                result.setdefault(stream_id, []).append(
                                    {
                                        "mac": str(mac),
                                        "interface": str(iface_name),
                                        "vlan": str(vlan_id),
                                        "pcp": str(pcp),
                                        "time-aware-offset": str(offset),
                                    }
                                )

        return result

    def get_time_aware_offsets_by_stream_id(self, stream_id: str) -> List[str]:
        """
        Retrieve all ``<time-aware-offset>`` values for a specific stream ID.

        This function reuses :meth:`get_all_time_aware_talker_vlan_info`
        to ensure consistent filtering and data structure. It extracts only
        the time-aware offset values corresponding to the given ``stream-id``.

        Parameters
        ----------
        stream_id : str
            The unique stream identifier (``<stream-id>``) whose
            time-aware offsets should be retrieved.

        Returns
        -------
        List[str]
            A list of all ``<time-aware-offset>`` values associated with the
            specified stream. Returns an empty list if no matching offsets are found.

        Examples
        --------
        >>> ge = GE_Dictionary(parsed_docs)
        >>> ge.get_time_aware_offsets_by_stream_id("de-ad-be-ef-00-01:00-05")
        ['78600']
        """
        time_aware_info = self.get_all_time_aware_talker_vlan_info()

        if stream_id not in time_aware_info:
            print(f"No <time-aware-offset> found for stream '{stream_id}'.")
            return []

        offsets = [
            entry["time-aware-offset"]
            for entry in time_aware_info[stream_id]
            if "time-aware-offset" in entry
        ]
        return offsets

    def get_gate_control_entries(self) -> List[Dict[str, Any]]:
        """Return all gate-control-entry dictionaries under interfaces."""
        entries: List[Dict[str, Any]] = []

        for doc in self.documents:
            interfaces_section = self._find_key(doc, "interfaces")
            if not interfaces_section:
                continue

            interface_list = interfaces_section.get("interface")
            if not interface_list:
                continue
            if not isinstance(interface_list, list):
                interface_list = [interface_list]

            for iface in interface_list:
                gate_table = self._find_key(iface, "gate-parameter-table")
                if not gate_table:
                    continue
                admin_list = self._find_key(gate_table, "admin-control-list")
                if not admin_list:
                    continue
                gate_entries = admin_list.get("gate-control-entry")
                if not gate_entries:
                    continue
                if not isinstance(gate_entries, list):
                    gate_entries = [gate_entries]
                entries.extend(gate_entries)

        return entries

    def get_gate_control_entries_formatted(self) -> List[str]:
        """Return gate-control-entries as formatted sched-entry strings."""
        formatted_entries: List[str] = []

        for entry in self.get_gate_control_entries():
            op = entry.get("operation-name")
            # idx = entry.get("index")
            state_val = entry.get("gate-states-value")
            interval = entry.get("time-interval-value")

            if state_val is None:
                state_val = "0"
            if interval is None:
                interval = "0"
            if op == "sched:set-gate-states":
                # Convert decimal to 2-digit uppercase hex (with leading zero if needed)
                hex_state = f"{int(state_val):02X}"
                formatted_entries.append(f"sched-entry S {hex_state} {interval}")
            else:
                # Fallback: just dump raw
                formatted_entries.append(f"sched-entry ? {state_val} {interval}")

        return formatted_entries

    # -----------------------
    # Internal helper methods
    # -----------------------

    def _find_key(self, node: Any, key: str) -> Any:
        """Recursive find first occurrence of a key."""
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key:
                    return v
                found = self._find_key(v, key)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = self._find_key(item, key)
                if found is not None:
                    return found
        return None

    def _find_all_keys(self, node: Any, key: str) -> List[Any]:
        """Recursive find all occurrences of a key."""
        results: List[Any] = []
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key:
                    results.append(v)
                results.extend(self._find_all_keys(v, key))
        elif isinstance(node, list):
            for item in node:
                results.extend(self._find_all_keys(item, key))
        return results

    def get_all_talker_stream_info(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract detailed stream information for each talker in all streams,
        grouped by stream ID.

        For every ``<stream>``, the following fields are collected:

        - **interface_name**
        - **interface_mac**
        - **source_mac**
        - **destination_mac**
        - **source_ip**
        - **destination_ip**
        - **dscp**
        - **ip_protocol**
        - **source-port**
        - **destination-port**
        - **vlan_tag** (*bool*)
        - **vlan_id**
        - **vlan_priority**
        - **time_aware** (*bool*)
        - **time_aware_offset** (*str* or *None*)
        - **earliest_transmit_offset** (*str* or *None*)
        - **latest_transmit_offset** (*str* or *None*)

        :return: A dictionary keyed by stream ID. Each value is a list of talker dictionaries.
        :rtype: Dict[str, List[Dict[str, Any]]]
        """
        # --- Handle empty or missing documents safely ---
        if not self.documents:
            return {}

        result: Dict[str, List[Dict[str, Any]]] = {}

        for doc in self.documents:
            domains = doc.get("cnc-config", {}).get("domain", [])
            if not isinstance(domains, list):
                domains = [domains]

            for domain in domains:
                cucs = domain.get("cuc", [])
                if not isinstance(cucs, list):
                    cucs = [cucs]

                for cuc in cucs:
                    streams = cuc.get("stream", [])
                    if not isinstance(streams, list):
                        streams = [streams]

                    for stream in streams:
                        stream_id = stream.get("stream-id")
                        if not stream_id:
                            continue

                        talkers = stream.get("talker", [])
                        if not isinstance(talkers, list):
                            talkers = [talkers]

                        for talker in talkers:
                            # --- Default values ---
                            interface_name = None
                            interface_mac = None
                            src_mac = None
                            dst_mac = None
                            vlan_id = None
                            pcp = None
                            vlan_tag = False
                            src_ip = None
                            dst_ip = None
                            dscp = None
                            ip_protocol = None
                            src_port = None
                            dst_port = None
                            time_aware = False
                            time_aware_offset = None
                            earliest_tx_offset = None
                            latest_tx_offset = None

                            # --- End-station interface info ---
                            end_iface = talker.get("end-station-interfaces", {})
                            src_mac = end_iface.get("mac-address")
                            src_mac = src_mac.replace("-", ":") if src_mac else None

                            # --- Interface configuration ---
                            iface_cfg = talker.get("interface-configuration", {})
                            iface_list = iface_cfg.get("interface-list", {})

                            # Interface-level info (mac-address, interface-name)
                            interface_mac = iface_list.get("mac-address")
                            interface_mac = (
                                interface_mac.replace("-", ":")
                                if interface_mac
                                else None
                            )
                            interface_name = iface_list.get("interface-name")

                            cfg_lists = iface_list.get("config-list", [])
                            if not isinstance(cfg_lists, list):
                                cfg_lists = [cfg_lists]

                            for cfg in cfg_lists:
                                # Destination MAC
                                if "ieee802-mac-addresses" in cfg:
                                    macs = cfg["ieee802-mac-addresses"]
                                    dst_mac = macs.get("destination-mac-address")
                                    dst_mac = (
                                        dst_mac.replace("-", ":") if dst_mac else None
                                    )
                                # VLAN info
                                if "ieee802-vlan-tag" in cfg:
                                    vlan_tag = True
                                    vlan = cfg["ieee802-vlan-tag"]
                                    vlan_id = vlan.get("vlan-id")
                                    pcp = vlan.get("priority-code-point")

                                # IPv4 info
                                if "ipv4-tuple" in cfg:
                                    ipv4 = cfg["ipv4-tuple"]
                                    src_ip = ipv4.get("source-ip-address")
                                    dst_ip = ipv4.get("destination-ip-address")
                                    dscp = ipv4.get("dscp")
                                    ip_protocol = ipv4.get("protocol")
                                    src_port = ipv4.get("source-port")
                                    dst_port = ipv4.get("destination-port")

                                # time-aware-offset
                                if "time-aware-offset" in cfg:
                                    offset_val = cfg.get("time-aware-offset")
                                    if offset_val and str(offset_val).strip() not in (
                                        "0",
                                        "0.0",
                                        "",
                                    ):
                                        time_aware = True
                                        time_aware_offset = offset_val

                                # time-aware block
                                if "time-aware" in cfg:
                                    time_block = cfg["time-aware"]
                                    earliest_tx_offset = time_block.get(
                                        "earliest-transmit-offset"
                                    )
                                    latest_tx_offset = time_block.get(
                                        "latest-transmit-offset"
                                    )

                                    for val in [earliest_tx_offset, latest_tx_offset]:
                                        if val and str(val).strip() not in (
                                            "0",
                                            "0.0",
                                            "",
                                        ):
                                            time_aware = True

                            talker_entry = {
                                "interface_name": interface_name,
                                "interface_mac": interface_mac,
                                "source_mac": src_mac,
                                "destination_mac": dst_mac,
                                "source_ip": src_ip,
                                "destination_ip": dst_ip,
                                "dscp": dscp,
                                "ip_protocol": ip_protocol,
                                "source_port": src_port,
                                "destination_port": dst_port,
                                "vlan_tag": vlan_tag,
                                "vlan_id": vlan_id,
                                "vlan_priority": pcp,
                                "time_aware": time_aware,
                                "time_aware_offset": time_aware_offset,
                                "earliest_transmit_offset": earliest_tx_offset,
                                "latest_transmit_offset": latest_tx_offset,
                            }

                            result.setdefault(stream_id, []).append(talker_entry)

        return result

    def get_vlan_tagged_non_time_aware_talker_info(
        self, all_talker_info: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieve talkers that have VLAN tagging enabled but are not time-aware.

        This method filters the provided ``all_talker_info`` dataset, returning only
        the talkers where ``vlan_tag`` is set to ``True`` **and**
        ``time_aware`` is set to ``False``.
        It can be used to isolate VLAN-enabled but non-time-aware traffic streams.

        :param all_talker_info:
            A dictionary containing all talker information, typically obtained from
            :meth:`get_all_talker_stream_info`. Each key represents a stream ID, and
            each value is a list of talker dictionaries.
        :type all_talker_info: Dict[str, List[Dict[str, Any]]]

        :return:
            A filtered dictionary keyed by stream ID, where each value is a list of
            talkers with ``vlan_tag == True`` and ``time_aware == False``.
        :rtype: Dict[str, List[Dict[str, Any]]]
        """
        vlan_non_time_aware_only: Dict[str, List[Dict[str, Any]]] = {}

        for stream_id, talkers in all_talker_info.items():
            filtered = [
                t
                for t in talkers
                if t.get("vlan_tag", False) and not t.get("time_aware", False)
            ]
            if filtered:
                vlan_non_time_aware_only[stream_id] = filtered

        return vlan_non_time_aware_only

    def get_vlan_tagged_time_aware_talker_info(
        self, all_talker_info: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieve talkers that have VLAN tagging enabled and are time-aware.

        This method filters the provided ``all_talker_info`` dataset, returning only
        the talkers where both ``vlan_tag`` and ``time_aware`` are set to ``True``.
        It can be used to isolate VLAN-enabled, time-synchronized traffic streams
        such as those used in TSN (Time-Sensitive Networking) configurations.

        :param all_talker_info:
            A dictionary containing all talker information, typically obtained from
            :meth:`get_all_talker_stream_info`. Each key represents a stream ID, and
            each value is a list of talker dictionaries.
        :type all_talker_info: Dict[str, List[Dict[str, Any]]]

        :return:
            A filtered dictionary keyed by stream ID, where each value is a list of
            talkers with ``vlan_tag == True`` and ``time_aware == True``.
        :rtype: Dict[str, List[Dict[str, Any]]]
        """
        vlan_time_aware_only: Dict[str, List[Dict[str, Any]]] = {}

        for stream_id, talkers in all_talker_info.items():
            filtered = [
                t
                for t in talkers
                if t.get("vlan_tag", False) and t.get("time_aware", False)
            ]
            if filtered:
                vlan_time_aware_only[stream_id] = filtered

        return vlan_time_aware_only


# -----------------------
# CLI / testing
# -----------------------
if __name__ == "__main__":
    import json
    import sys

    from universal_parser import UniversalParser

    if len(sys.argv) < 2:
        print("Usage: python GE_Dictionary.py <path-to-xml/yaml/json>")
        sys.exit(1)

    file_path = sys.argv[1]
    uparser = UniversalParser()
    uparser.parse(file_path)

    if uparser.has_chronos_domain():
        print("🔍 chronos-domain detected in file!")
        ge_dict = uparser.get_dictionary_helper()
        assert ge_dict is not None, "expected a GE_Dictionary"

        print("Interface names:", ge_dict.get_interface_names())
        print("Stream IDs:", ge_dict.get_stream_ids())
        print("Gate-control entries:")
        for entry in ge_dict.get_gate_control_entries():
            print(json.dumps(entry, indent=2))
    else:
        print("❌ chronos-domain not found in file.")
