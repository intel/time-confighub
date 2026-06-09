# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""Wrapper for ``ietf-interfaces`` YANG module.

Covers interface, gate-control-list, and CBS (Credit-Based Shaper) data
rooted at ``<interfaces>``.
"""

from typing import Any, Dict, List

from time_config_hub.utils.yang_parser.base_yang_config_wrapper import (
    BaseYangConfigWrapper,
)
from time_config_hub.utils.yang_parser.exceptions import InvalidInputDataError


class IetfInterfacesWrapper(BaseYangConfigWrapper):
    """Wrapper for ``ietf-interfaces`` YANG module.

    Provides typed accessors for network interface configuration, including
    gate control lists (GCL / IEEE 802.1Qbv) and credit-based shaper (CBS)
    parameters stored under ``<interfaces>``.

    :cvar YANG_MODULE: ``"ietf-interfaces"``
    :cvar YANG_NAMESPACE: ``"urn:ietf:params:xml:ns:yang:ietf-interfaces"``
    """

    YANG_MODULE = "ietf-interfaces"
    YANG_NAMESPACE = "urn:ietf:params:xml:ns:yang:ietf-interfaces"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_interface_list(self) -> List[Dict[str, Any]]:
        """Return a flat list of all ``<interface>`` dicts in the config.

        :return: List of interface dictionaries.
        :rtype: List[Dict[str, Any]]
        """
        interfaces_section = self._parsed_dict.get("interfaces", {})
        raw = interfaces_section.get("interface", [])
        if not isinstance(raw, list):
            raw = [raw] if raw else []
        return raw

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_interface_names(self) -> List[str]:
        """Return all ``<name>`` values under ``<interfaces>``.

        :return: List of interface name strings.
        :rtype: List[str]
        :raises InvalidInputDataError: If no interface names are found.
        """
        names: List[str] = []
        for iface in self._get_interface_list():
            name_entry = iface.get("name")
            if name_entry is None:
                continue
            if isinstance(name_entry, dict) and "#text" in name_entry:
                names.append(str(name_entry["#text"]))
            else:
                names.append(str(name_entry))

        if not names:
            raise InvalidInputDataError(
                "No interface name found in configuration file."
            )
        return names

    def get_gate_control_entries(self) -> List[Dict[str, Any]]:
        """Return all ``<gate-control-entry>`` dicts across all interfaces.

        :return: List of gate-control-entry dicts with keys ``index``,
            ``operation-name``, ``gate-states-value``, ``time-interval-value``.
        :rtype: List[Dict[str, Any]]
        :raises InvalidInputDataError: If no gate control entries are found.
        """
        entries: List[Dict[str, Any]] = []

        for iface in self._get_interface_list():
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

        if not entries:
            raise InvalidInputDataError(
                "No gate-control-entry found in configuration file."
            )
        return entries

    def get_gate_control_entries_formatted(self) -> List[str]:
        """Return gate-control-entries as ``sched-entry`` strings.

        Each entry is formatted as::

            sched-entry S <HEX_GATE_STATE> <INTERVAL_NS>

        :return: List of formatted sched-entry strings.
        :rtype: List[str]
        """
        formatted: List[str] = []
        for entry in self.get_gate_control_entries():
            op = str(entry.get("operation-name", ""))
            state_val = entry.get("gate-states-value", "0")
            interval = entry.get("time-interval-value", "0")

            if "sched:set-gate-states" in op:
                hex_state = f"{int(state_val):02X}"
                formatted.append(f"sched-entry S {hex_state} {interval}")
            else:
                formatted.append(f"sched-entry ? {state_val} {interval}")

        return formatted

    def get_gcl_list(self) -> List[str]:
        """Return the formatted gate control list (alias for :meth:`get_gate_control_entries_formatted`).

        :return: List of formatted sched-entry strings.
        :rtype: List[str]
        """
        return self.get_gate_control_entries_formatted()

    def get_cbsa_params(self) -> List[Dict[str, Any]]:
        """Return all ``<cbsa-parameter-table>`` entries across all interfaces.

        Each entry contains at minimum the keys ``traffic-class`` and
        ``admin-idle-slope`` as defined in
        ``ieee802-dot1dc-cbsa-if``.

        :return: List of CBSA parameter dicts.  Empty list if none configured.
        :rtype: List[Dict[str, Any]]
        """
        params: List[Dict[str, Any]] = []

        for iface in self._get_interface_list():
            cbsa = self._find_key(iface, "cbsa")
            if not cbsa:
                continue
            table = cbsa.get("cbsa-parameter-table")
            if not table:
                continue
            if not isinstance(table, list):
                table = [table]
            params.extend(table)

        return params

    def get_admin_cycle_time(self) -> List[Dict[str, Any]]:
        """Return ``<admin-cycle-time>`` dicts for each interface that has one.

        :return: List of dicts with ``numerator`` and ``denominator`` keys.
        :rtype: List[Dict[str, Any]]
        """
        result: List[Dict[str, Any]] = []
        for iface in self._get_interface_list():
            gate_table = self._find_key(iface, "gate-parameter-table")
            if not gate_table:
                continue
            cycle_time = gate_table.get("admin-cycle-time")
            if cycle_time:
                result.append(cycle_time)
        return result
