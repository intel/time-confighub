# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""Wrapper for ``ieee802-dot1q-cnc-config`` YANG module.

Covers the CNC (Centralized Network Configuration) stream and talker data
rooted at ``<cnc-config>``.
"""

from typing import Any, Dict, List

from time_config_hub.utils.yang_parser.base_yang_config_wrapper import (
    BaseYangConfigWrapper,
)
from time_config_hub.utils.yang_parser.exceptions import InvalidInputDataError


class Ieee8021QCncConfigWrapper(BaseYangConfigWrapper):
    """Wrapper for ``ieee802-dot1q-cnc-config`` YANG module.

    Provides typed accessors for TSN stream and talker configuration data
    stored under ``<cnc-config>`` in the parsed dictionary.

    :cvar YANG_MODULE: ``"ieee802-dot1q-cnc-config"``
    :cvar YANG_NAMESPACE: ``"urn:ieee:std:802.1Q:yang:ieee802-dot1q-cnc-config"``
    """

    YANG_MODULE = "ieee802-dot1q-cnc-config"
    YANG_NAMESPACE = "urn:ieee:std:802.1Q:yang:ieee802-dot1q-cnc-config"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_streams(self) -> List[Dict[str, Any]]:
        """Return a flat list of all ``<stream>`` dicts in the config.

        :return: List of stream dictionaries.
        :rtype: List[Dict[str, Any]]
        """
        domains = self._parsed_dict.get("cnc-config", {}).get("domain", [])
        if not isinstance(domains, list):
            domains = [domains]

        streams: List[Dict[str, Any]] = []
        for domain in domains:
            cucs = domain.get("cuc", [])
            if not isinstance(cucs, list):
                cucs = [cucs]
            for cuc in cucs:
                raw = cuc.get("stream", [])
                if not isinstance(raw, list):
                    raw = [raw]
                streams.extend(raw)
        return streams

    @staticmethod
    def _normalize_list(value: Any) -> List[Any]:
        """Ensure *value* is a list; wrap a dict/scalar in one if needed.

        :param value: Dict, list, or scalar.
        :return: List.
        :rtype: List[Any]
        """
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    @staticmethod
    def _text_value(val: Any) -> str:
        """Extract the plain string from a libyang ``#text`` wrapper or plain value.

        :param val: A string, a dict with a ``"#text"`` key, or any scalar.
        :return: String representation.
        :rtype: str
        """
        if isinstance(val, dict) and "#text" in val:
            return str(val["#text"])
        return str(val)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_stream_ids(self) -> List[str]:
        """Return all ``<stream-id>`` values in the config.

        :return: List of stream-id strings.
        :rtype: List[str]
        :raises InvalidInputDataError: If no stream IDs are found.
        """
        stream_ids = [
            self._text_value(s["stream-id"])
            for s in self._get_streams()
            if "stream-id" in s
        ]
        if not stream_ids:
            raise InvalidInputDataError("No stream ID found in configuration.")
        return stream_ids

    def get_talker_vlan_info(self) -> Dict[str, List[Dict[str, Any]]]:
        """Return VLAN info for each talker grouped by stream ID.

        :return: Dict keyed by stream-id, each value is a list of talker dicts
            with keys ``mac``, ``interface``, ``vlan``, ``pcp``.
        :rtype: Dict[str, List[Dict[str, Any]]]
        """
        result: Dict[str, List[Dict[str, Any]]] = {}

        for stream in self._get_streams():
            stream_id = stream.get("stream-id")
            if not stream_id:
                continue
            sid = self._text_value(stream_id)

            talkers = self._normalize_list(stream.get("talker"))
            talkers_info = []

            for talker in talkers:
                mac = talker.get("end-station-interfaces", {}).get("mac-address")
                iface_cfg = talker.get("interface-configuration", {})
                iface_list = iface_cfg.get("interface-list", {})
                if isinstance(iface_list, list):
                    iface_list = iface_list[0] if iface_list else {}
                iface_name = iface_list.get("interface-name")

                vlan_id = None
                pcp = None
                for cfg in self._normalize_list(iface_list.get("config-list")):
                    vlan_tag = cfg.get("ieee802-vlan-tag")
                    if vlan_tag:
                        vlan_id = vlan_tag.get("vlan-id")
                        pcp = vlan_tag.get("priority-code-point")

                talkers_info.append(
                    {"mac": mac, "interface": iface_name, "vlan": vlan_id, "pcp": pcp}
                )

            result[sid] = talkers_info

        return result

    def get_talker_vlan_info_by_stream(self, stream_id: str) -> List[str]:
        """Return formatted talker VLAN info for *stream_id*.

        :param str stream_id: The stream ID to look up.
        :return: List of formatted strings, or an empty list if not found.
        :rtype: List[str]
        """
        all_info = self.get_talker_vlan_info()
        if stream_id not in all_info:
            return []

        return [
            f"MAC: {t['mac']}, IF: {t['interface']}, VLAN: {t['vlan']}, PCP: {t['pcp']}"
            for t in all_info[stream_id]
        ]

    def get_all_time_aware_talker_vlan_info(self) -> Dict[str, List[Dict[str, Any]]]:
        """Return VLAN info only for talkers that have a ``<time-aware-offset>``.

        :return: Dict keyed by stream-id. Each entry contains ``mac``,
            ``interface``, ``vlan``, ``pcp``, and ``time-aware-offset``.
        :rtype: Dict[str, List[Dict[str, Any]]]
        """
        result: Dict[str, List[Dict[str, Any]]] = {}

        for stream in self._get_streams():
            stream_id = stream.get("stream-id")
            if not stream_id:
                continue
            sid = self._text_value(stream_id)

            for talker in self._normalize_list(stream.get("talker")):
                mac = talker.get("end-station-interfaces", {}).get("mac-address")
                iface_cfg = talker.get("interface-configuration", {})
                iface_list = iface_cfg.get("interface-list", {})
                if isinstance(iface_list, list):
                    iface_list = iface_list[0] if iface_list else {}
                iface_name = iface_list.get("interface-name")
                cfg_lists = self._normalize_list(iface_list.get("config-list"))

                time_offsets = [
                    cfg.get("time-aware-offset")
                    for cfg in cfg_lists
                    if "time-aware-offset" in cfg
                ]
                if not time_offsets:
                    continue

                vlan_id = None
                pcp = None
                for cfg in cfg_lists:
                    vlan_tag = cfg.get("ieee802-vlan-tag")
                    if vlan_tag:
                        vlan_id = vlan_tag.get("vlan-id")
                        pcp = vlan_tag.get("priority-code-point")

                for offset in time_offsets:
                    result.setdefault(sid, []).append(
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
        """Return all ``<time-aware-offset>`` values for *stream_id*.

        :param str stream_id: The stream ID to look up.
        :return: List of offset strings; empty list if not found.
        :rtype: List[str]
        """
        time_aware_info = self.get_all_time_aware_talker_vlan_info()
        return [
            entry["time-aware-offset"]
            for entry in time_aware_info.get(stream_id, [])
            if "time-aware-offset" in entry
        ]

    def get_all_talker_stream_info(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract comprehensive talker information grouped by stream ID.

        Returns a dict keyed by stream-id where each value is a list of talker
        info dicts with the following keys:

        - ``interface_name``, ``interface_mac``
        - ``source_mac``, ``destination_mac``
        - ``source_ip``, ``destination_ip``, ``dscp``, ``ip_protocol``
        - ``source_port``, ``destination_port``
        - ``vlan_tag`` (*bool*), ``vlan_id``, ``vlan_priority``
        - ``time_aware`` (*bool*), ``time_aware_offset``
        - ``earliest_transmit_offset``, ``latest_transmit_offset``

        :return: Dict keyed by stream-id.
        :rtype: Dict[str, List[Dict[str, Any]]]
        """
        result: Dict[str, List[Dict[str, Any]]] = {}

        for stream in self._get_streams():
            stream_id = stream.get("stream-id")
            if not stream_id:
                continue
            sid = self._text_value(stream_id)

            for talker in self._normalize_list(stream.get("talker")):
                # End-station interface
                end_station = talker.get("end-station-interfaces", {})
                if isinstance(end_station, list):
                    end_station = end_station[0] if end_station else {}
                src_mac = end_station.get("mac-address")
                src_mac = src_mac.replace("-", ":") if src_mac else None

                # Interface configuration
                iface_cfg = talker.get("interface-configuration", {})
                iface_list_raw = iface_cfg.get("interface-list", {})
                if isinstance(iface_list_raw, list):
                    iface_list = iface_list_raw[0] if iface_list_raw else {}
                else:
                    iface_list = iface_list_raw

                interface_mac = iface_list.get("mac-address")
                interface_mac = (
                    interface_mac.replace("-", ":") if interface_mac else None
                )
                interface_name = iface_list.get("interface-name")
                cfg_lists = self._normalize_list(iface_list.get("config-list"))

                # Per-entry defaults
                dst_mac = None
                vlan_tag = False
                vlan_id = None
                pcp = None
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

                for cfg in cfg_lists:
                    if "ieee802-mac-addresses" in cfg:
                        macs = cfg["ieee802-mac-addresses"]
                        dst_mac = macs.get("destination-mac-address")
                        dst_mac = dst_mac.replace("-", ":") if dst_mac else None

                    if "ieee802-vlan-tag" in cfg:
                        vlan_tag = True
                        vlan = cfg["ieee802-vlan-tag"]
                        vlan_id = vlan.get("vlan-id")
                        pcp = vlan.get("priority-code-point")

                    if "ipv4-tuple" in cfg:
                        ipv4 = cfg["ipv4-tuple"]
                        src_ip = ipv4.get("source-ip-address")
                        dst_ip = ipv4.get("destination-ip-address")
                        dscp = ipv4.get("dscp")
                        ip_protocol = ipv4.get("protocol")
                        src_port = ipv4.get("source-port")
                        dst_port = ipv4.get("destination-port")

                    if "time-aware-offset" in cfg:
                        offset_val = cfg.get("time-aware-offset")
                        if offset_val and str(offset_val).strip() not in (
                            "0",
                            "0.0",
                            "",
                        ):
                            time_aware = True
                            time_aware_offset = offset_val

                    if "time-aware" in cfg:
                        time_block = cfg["time-aware"]
                        earliest_tx_offset = time_block.get("earliest-transmit-offset")
                        latest_tx_offset = time_block.get("latest-transmit-offset")
                        for val in [earliest_tx_offset, latest_tx_offset]:
                            if val and str(val).strip() not in ("0", "0.0", ""):
                                time_aware = True

                # Also check traffic-specification for time-aware window
                traffic_spec = talker.get("traffic-specification", {})
                ta_spec = traffic_spec.get("time-aware")
                if ta_spec and earliest_tx_offset is None:
                    earliest_tx_offset = ta_spec.get("earliest-transmit-offset")
                    latest_tx_offset = ta_spec.get("latest-transmit-offset")

                result.setdefault(sid, []).append(
                    {
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
                )

        return result

    def get_vlan_tagged_time_aware_talker_info(
        self, all_talker_info: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Filter *all_talker_info* to entries where ``vlan_tag`` and ``time_aware`` are both ``True``.

        :param all_talker_info: Output of :meth:`get_all_talker_stream_info`.
        :type all_talker_info: Dict[str, List[Dict[str, Any]]]
        :return: Filtered dict keyed by stream-id.
        :rtype: Dict[str, List[Dict[str, Any]]]
        """
        return {
            sid: [
                t
                for t in talkers
                if t.get("vlan_tag", False) and t.get("time_aware", False)
            ]
            for sid, talkers in all_talker_info.items()
            if any(
                t.get("vlan_tag", False) and t.get("time_aware", False) for t in talkers
            )
        }

    def get_vlan_tagged_non_time_aware_talker_info(
        self, all_talker_info: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Filter *all_talker_info* to entries where ``vlan_tag`` is ``True`` but ``time_aware`` is ``False``.

        :param all_talker_info: Output of :meth:`get_all_talker_stream_info`.
        :type all_talker_info: Dict[str, List[Dict[str, Any]]]
        :return: Filtered dict keyed by stream-id.
        :rtype: Dict[str, List[Dict[str, Any]]]
        """
        return {
            sid: [
                t
                for t in talkers
                if t.get("vlan_tag", False) and not t.get("time_aware", False)
            ]
            for sid, talkers in all_talker_info.items()
            if any(
                t.get("vlan_tag", False) and not t.get("time_aware", False)
                for t in talkers
            )
        }
