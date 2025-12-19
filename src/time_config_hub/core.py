"""
Time Config Hub Core Module

This module contains the core TIMEConfigHub class that handles:

- Configuration application from XML/YAML files
- Status retrieval for TSN interfaces
- Configuration reset to defaults
- Interface validation for TSN capabilities
- Integration with traffic control (tc) commands

The core module serves as the primary interface between the CLI
and the underlying system configuration mechanisms.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List

from time_config_hub.service_manager import ServiceManager
from tsn_config_parser import UniversalParser
from tsn_config_parser.tc_command import (
    create_tc_filter_commands_for_non_time_aware_talkers,
    create_tc_filter_commands_for_time_aware_talkers,
    create_tc_qdisc_gcl_command,
    reset_clsact_qdisc_interface,
    reset_egress_filter_interface,
    reset_root_qdisc_interface,
    run_tc_command,
    show_qdisc,
    show_tc_egress_filters,
)

from .exceptions import TSNConfigError

logger = logging.getLogger(__name__)


class TIMEConfigHub:
    """
    Main Time Config Hub class.

    Handles configuration application, status retrieval, and reset operations
    for Time-Sensitive Networking (TSN) configurations.
    It should be stateless or hold minimal state only
    """

    def __init__(self, app_config: dict):
        """
        Initialize Time Config Hub.

        :param str config_dir: Directory for TSN traffic configuration files
        :param bool verbose: Enable verbose logging
        """
        logger.debug("Initializing Time Config Hub...")
        self.app_config = app_config

        # config_dir suppose to store applied configuration backups
        self.config_dir = Path(app_config.get("General", {}).get("ConfigDirectory"))
        self.verbose = app_config.get("General", {}).get("Verbosity")
        self.service_manager = ServiceManager()

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Time Config Hub initialized with config_dir: {self.config_dir}")

    def apply_config(self, config_file: str, dry_run: bool = False):
        """
        Apply configuration from a file.

        :param str config_file: Path to configuration file (XML or YAML)
        :param bool dry_run: If True, show commands without executing
        :return: True if successful, False otherwise
        :rtype: None
        :raises TSNConfigError: If configuration application fails
        """
        try:
            logger.info(f"Applying configuration from {config_file}")

            # Parse configuration file
            uparser = self._parse_config(config_file)
            ge_dict = uparser.get_dictionary_helper()  # automatically checks chronos
            if not ge_dict:
                logger.info("Chronos domain not found. No dictionary available.")
                return

            # Extract stream configuration
            interfaces = ge_dict.get_interface_names()
            streams = ge_dict.get_stream_ids()
            gcl = ge_dict.get_gate_control_entries_formatted()
            logger.info(f"Interfaces: {interfaces}, Stream IDs: {streams}, gcl: {gcl}")

            # Validate interfaces
            for iface in interfaces:
                if not self._validate_interface(iface):
                    raise TSNConfigError(
                        f"Invalid or non-TSN-capable interface: {iface}"
                    )

            # TODO: Use Device.from_interface to determine TSN capabilities

            # Reset existing configuration before applying new config
            if not dry_run:
                logger.info("Resetting existing TSN configuration on interfaces...")
                self._reset_interfaces(interfaces)

            # Apply qdisc and filter configurations
            self._apply_qdisc_configuration(
                interfaces=interfaces,
                gcl=gcl,
                config_file=config_file,
                dry_run=dry_run,
            )

            self._apply_filter_configuration(
                interfaces=interfaces,
                ge_dict=ge_dict,
                config_file=config_file,
                dry_run=dry_run,
            )

        except TSNConfigError:
            logger.error(f"Failed to apply configuration: {config_file}")
            raise

        except Exception as e:
            logger.exception(f"Unexpected error applying configuration: {config_file}")
            raise TSNConfigError("Unexpected error applying configuration") from e

    def _parse_config(self, config_file: str) -> UniversalParser:
        """Parse a configuration file and return the parser.

        :param str config_file: Path to configuration file (XML or YAML)
        :return: UniversalParser instance
        :rtype: UniversalParser
        :raises TSNConfigError: If parsing yields no documents
        """
        uparser = UniversalParser()
        docs = uparser.parse(config_file)
        if not docs:
            raise TSNConfigError("No valid configuration documents found.")

        return uparser

    def _reset_interfaces(self, interfaces: List[str]) -> None:
        """Reset qdisc and filters for a list of interfaces."""
        for interface in interfaces:
            logger.info(f"Resetting qdisc and filters on interface: {interface}")
            self.reset_config(interface)

    def _apply_qdisc_configuration(
        self,
        interfaces: List[str],
        gcl: List[Any],
        config_file: str,
        dry_run: bool,
    ) -> None:
        """Generate and apply qdisc configuration."""
        # Don't pass base_time -> defaults to current system time
        # TODO: num_tc should be configurable according to device capabilities
        # TODO: tc mapping and queues should be configurable
        qdisc_cmds = create_tc_qdisc_gcl_command(
            interfaces,
            gcl,
            num_tc=4,
            map_str="0 0 0 0 1 1 2 3 0 0 0 0 0 0 0 0",
            queues_str="1@0 1@1 1@2 1@3",
        )
        logger.debug(f"tc generated: {qdisc_cmds}")

        fail_count = self._run_tc_commands(
            qdisc_cmds,
            dry_run=dry_run,
            header="> Generated qdisc command:",
        )

        if dry_run:
            logger.info("Dry-run enabled; skipping qdisc state display.")
        else:
            self.show_qdisc_state(interfaces)

        if fail_count > 0:
            raise TSNConfigError(f"Failed to apply qdisc config: {config_file}")

        logger.info(f"qdisc configuration applied successfully: {config_file}")

    def _apply_filter_configuration(
        self,
        interfaces: List[str],
        ge_dict: Any,
        config_file: str,
        dry_run: bool,
    ) -> None:
        """Generate and apply tc filter configuration."""
        all_talker_info = ge_dict.get_all_talker_stream_info()

        # Extract talker info
        time_aware_vlan_talkers = ge_dict.get_vlan_tagged_time_aware_talker_info(
            all_talker_info
        )
        self._log_time_aware_vlan_talkers(time_aware_vlan_talkers)

        vlan_non_time_aware = ge_dict.get_vlan_tagged_non_time_aware_talker_info(
            all_talker_info
        )

        # Generate filter commands
        time_aware_vlan_commands = create_tc_filter_commands_for_time_aware_talkers(
            time_aware_vlan_talkers
        )
        non_time_aware_vlan_commands = (
            create_tc_filter_commands_for_non_time_aware_talkers(vlan_non_time_aware)
        )

        # Run filter commands
        logger.info("\n=== Generated smart tc filter [TIME-AWARE] commands ===")
        fail_count = self._run_tc_commands(time_aware_vlan_commands, dry_run=dry_run)

        logger.info("\n=== Generated smart tc filter [NON-TIME-AWARE] commands ===")
        fail_count += self._run_tc_commands(
            non_time_aware_vlan_commands, dry_run=dry_run
        )

        if dry_run:
            logger.info("Dry-run enabled; skipping egress filter state display.")
        else:
            self._show_filter_state(interfaces)

        if fail_count > 0:
            raise TSNConfigError(f"Failed to apply filters config: {config_file}")

        logger.info(f"tc filter configuration applied successfully: {config_file}")

    def _run_tc_commands(
        self,
        commands: Iterable[str],
        dry_run: bool,
        header: str = "",
    ) -> int:
        """Log and run a list of tc commands.

        :param Iterable[str] commands: Commands to run
        :param bool dry_run: If True, commands are logged but not executed
        :param str header: Optional header prefix to log before each command
        :return: Number of failed commands
        :rtype: int
        """
        # TODO: create library for tc command under commands/tc_command.py
        fail_count = 0
        for cmd in commands:
            if header:
                logger.info(f"{header}\n{cmd}")
            else:
                logger.info(cmd)

            if dry_run:
                # Skip execution in dry-run mode
                continue

            result = run_tc_command(cmd)
            if result["returncode"] != 0:
                fail_count += 1
                logger.error(
                    f"Command failed with return code: {result['returncode']}\n"
                    + f" command: {cmd}\n"
                    + f" stderr: {result['stderr']}"
                )

        return fail_count

    def show_qdisc_state(self, interfaces: Iterable[str]) -> None:
        """Show qdisc state for all interfaces."""
        for iface in interfaces:
            logger.info(f"> qdisc state for {iface}:")
            qdisc_state = show_qdisc(iface)
            logger.info(qdisc_state["stdout"].strip())
            logger.info("-" * 40)

    def _show_filter_state(self, interfaces: Iterable[str]) -> None:
        """Show egress filter state for all interfaces."""
        for iface in interfaces:
            logger.info(f"> tc egress filters for {iface}:")
            filter_state = show_tc_egress_filters(iface)
            logger.info(filter_state["stdout"].strip())
            logger.info("-" * 40)

    def _log_time_aware_vlan_talkers(
        self, time_aware_vlan_talkers: Dict[str, Any]
    ) -> None:
        """Log VLAN-tagged time-aware talker stream information."""
        logger.info("\n=== VLAN-Tagged & Time-Aware Talker Streams ===")
        if not time_aware_vlan_talkers:
            logger.info("No VLAN-tagged time-aware talkers found.")
            return

        for stream_id, talkers in time_aware_vlan_talkers.items():
            logger.info(f"\nStream ID: {stream_id}")
            for t in talkers:
                logger.info(
                    f"  IF: {t['interface_name']}, MAC: {t['interface_mac']}, "
                    f"SrcMAC: {t['source_mac']}, DstMAC: {t['destination_mac']}, "
                    f"SrcIP: {t['source_ip']}, DstIP: {t['destination_ip']}, Port: {t['destination_port']}, "
                    f"VLAN_Tag: {t['vlan_tag']}, VLAN_ID: {t['vlan_id']}, PCP: {t['vlan_priority']}, "
                    f"TimeAware: {t['time_aware']}, Offset: {t['time_aware_offset']}, "
                    f"Earliest: {t['earliest_transmit_offset']}, Latest: {t['latest_transmit_offset']}"
                )

    def get_status(self, interface: str) -> Dict[str, Any]:
        """
        Get current TSN configuration status.

        :param str interface: Specific interface to check
        :return: Dictionary with status information
        :rtype: Dict[str, Any]
        :raises TSNConfigError: If status retrieval fails
        """
        try:
            qdisc_state = show_qdisc(interface)
            logger.debug(f"qdisc state: {qdisc_state}")

            filter_state = show_tc_egress_filters(interface)
            logger.debug(f"egress filter state: {filter_state}")

            status = {
                "qdisc": qdisc_state["stdout"].strip(),
                "egress_filters": filter_state["stdout"].strip(),
            }
            return status

        except Exception as e:
            logger.exception("Failed to get status")
            raise TSNConfigError("Failed to get status") from e

    def reset_config(self, interface: str) -> bool:
        """
        Reset TSN configuration to defaults.

        :param str interface: Specific interface to reset
        :return: True if successful, False otherwise
        :rtype: bool
        :raises TSNConfigError: If configuration reset fails
        """
        try:
            results = []
            results.append(reset_egress_filter_interface(interface))
            results.append(reset_clsact_qdisc_interface(interface))
            results.append(reset_root_qdisc_interface(interface))

            for res in results:
                if res["returncode"] != 0:
                    raise TSNConfigError(
                        f"Failed to reset qdisc on interface {interface}: "
                        f"{res['stderr']}"
                    )
            logger.info(
                f"TSN configuration reset successfully for interface: {interface}"
            )
            return True

        except Exception as e:
            logger.exception("Failed to reset configuration")
            raise TSNConfigError("Failed to reset configuration") from e

    def _validate_interface(self, interface: str) -> bool:
        """
        Validate that network interface exists and is TSN-capable.

        :param str interface: Network interface name to validate
        :return: True if interface is valid and TSN-capable
        :rtype: bool
        """
        try:
            # Check if interface exists
            iface_path = Path(f"/sys/class/net/{interface}")
            if not iface_path.exists():
                logger.error(f"Interface {interface} does not exist.")
                return False

            # TODO: Additional TSN capability checks could be added here
            # For now, we assume any interface can be used
            return True

        except Exception:
            logger.exception(f"Interface validation failed for {interface}")
            return False

    def file_event_handler(self, event_type: str, file_path: str):
        """
        Handle file system events, such as configuration file changes.
        This method is used by the watcher running in background (tch service).

        :param str event_type: Type of event ('created', 'modified', 'deleted')
        :param str file_path: Path to the file that triggered the event
        :return: None
        :rtype: None
        """
        logger.info(f"Handling file event: {event_type} for {file_path}")

        if event_type == "deleted":
            # For now, just log deletion events
            logger.debug(f"No action taken for deleted file: {file_path}")
            return

        if event_type in ["created", "modified"]:
            try:
                # For now, created and modified events are treated the same
                logger.debug(f"Handling {event_type} event: {file_path}")
                self.apply_config(file_path, dry_run=False)
                logger.info(f"Configuration applied successfully from {file_path}")

            except TSNConfigError:
                logger.error(f"Error handling file event {event_type}: {file_path}")

            except Exception:
                logger.exception(f"Error handling file event {event_type}: {file_path}")
                raise

        return
