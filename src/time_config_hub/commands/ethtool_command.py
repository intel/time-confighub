"""Ethtool command utilities for network interface management.

This module provides the EthtoolCommand class for executing ethtool operations
on network interfaces. Ethtool is a standard Linux utility for querying and
controlling network device driver and hardware settings.

Note:
    All ethtool commands require appropriate permissions and the ethtool
    utility to be installed on the system.
"""

import logging

from .base_command import BaseCommand

logger = logging.getLogger(__name__)


class EthtoolCommand(BaseCommand):
    """Specialized command class for ethtool operations.

    This class extends the base Command class to provide specific functionality
    for ethtool commands, which are commonly used for network interface management
    and configuration.

    :cvar SUCCESS_CODES: Extended success codes including 80 for some ethtool operations
    :type SUCCESS_CODES: List[int]
    """

    SUCCESS_CODES = [0, 80]  # 80 is often returned by ethtool for some operations

    @classmethod
    def get_driver_info(cls, interface: str) -> str:
        """Get network interface driver information using ethtool.

        :param str interface: Network interface name (e.g., 'eth0', 'enp1s0')
        :return: Driver information output from ethtool
        :rtype: str
        :raises ValueError: if interface name is invalid or empty
        :raises RuntimeError: if ethtool command fails

        Example output:
            ```
            driver: igc
            version: 6.12rt-intel
            firmware-version: 2022:889d
            expansion-rom-version:
            bus-info: 0000:01:00.0
            supports-statistics: yes
            supports-test: yes
            supports-eeprom-access: yes
            supports-register-dump: yes
            supports-priv-flags: yes
            ```
        """
        if not interface or not interface.strip():
            raise ValueError(f"Invalid interface name: {interface}")

        logger.debug(f"Getting driver info for interface: {interface}")

        try:
            command = f"ethtool -i {interface}"
            output = cls.run(command)

            if not output.stdout.strip():
                raise RuntimeError(
                    f"No driver information available for interface: {interface}"
                )

            logger.debug(f"Successfully retrieved driver info for {interface}")
            return output.stdout.strip()

        except Exception as e:
            logger.error(f"Failed to get driver info for interface {interface}: {e}")
            raise RuntimeError(
                f"Could not retrieve driver information for interface {interface}"
            ) from e

    @classmethod
    def get_information(cls, interface: str) -> str:
        """Get general network interface information using ethtool.

        :param str interface: Network interface name (e.g., 'eth0', 'enp1s0')
        :return: General interface information output from ethtool
        :rtype: str
        :raises ValueError: if interface name is invalid or empty
        :raises RuntimeError: if ethtool command fails

        Example output:
            ```
            Settings for eth0:
                Supported ports: [ TP ]
                Supported link modes:   10baseT/Half 10baseT/Full
                                        100baseT/Half 100baseT/Full
                                        1000baseT/Full
                Supported pause frame use: Symmetric
                Supports auto-negotiation: Yes
                ...
            ```
        """
        if not interface or not interface.strip():
            raise ValueError(f"Invalid interface name: {interface}")

        logger.debug(f"Getting general info for interface: {interface}")

        try:
            command = f"ethtool {interface}"
            output = cls.run(command)

            if not output.stdout.strip():
                raise RuntimeError(
                    f"No information available for interface: {interface}"
                )

            logger.debug(f"Successfully retrieved general info for {interface}")
            return output.stdout.strip()

        except Exception as e:
            logger.error(f"Failed to get general info for interface {interface}: {e}")
            raise RuntimeError(
                f"Could not retrieve general information for interface {interface}"
            ) from e

    @classmethod
    def check_interface_exists(cls, interface: str) -> bool:
        """Check if a network interface exists and is accessible via ethtool.

        :param str interface: Network interface name to check
        :return: True if interface exists and is accessible, False otherwise
        :rtype: bool
        """
        if not interface or not interface.strip():
            return False

        try:
            cls.get_driver_info(interface)
            return True
        except (ValueError, RuntimeError):
            return False

    @classmethod
    def get_link_status(cls, interface: str) -> str:
        """Get link status information for a network interface.

        :param str interface: Network interface name (e.g., 'eth0', 'enp1s0')
        :return: Link status information from ethtool
        :rtype: str
        :raises ValueError: if interface name is invalid or empty
        :raises RuntimeError: if ethtool command fails
        """
        if not interface or not interface.strip():
            raise ValueError(f"Invalid interface name: {interface}")

        logger.debug(f"Getting link status for interface: {interface}")

        try:
            command = f"ethtool {interface}"
            output = cls.run(command)

            if not output.stdout.strip():
                raise RuntimeError(
                    f"No link status available for interface: {interface}"
                )

            logger.debug(f"Successfully retrieved link status for {interface}")
            return output.stdout.strip()

        except Exception as e:
            logger.error(f"Failed to get link status for interface {interface}: {e}")
            raise RuntimeError(
                f"Could not retrieve link status for interface {interface}"
            ) from e

    @classmethod
    def get_statistics(cls, interface: str) -> str:
        """Get network interface statistics using ethtool.

        :param str interface: Network interface name (e.g., 'eth0', 'enp1s0')
        :return: Interface statistics from ethtool
        :rtype: str
        :raises ValueError: if interface name is invalid or empty
        :raises RuntimeError: if ethtool command fails
        """
        if not interface or not interface.strip():
            raise ValueError(f"Invalid interface name: {interface}")

        logger.debug(f"Getting statistics for interface: {interface}")

        try:
            command = f"ethtool -S {interface}"
            output = cls.run(command)

            if not output.stdout.strip():
                raise RuntimeError(
                    f"No statistics available for interface: {interface}"
                )

            logger.debug(f"Successfully retrieved statistics for {interface}")
            return output.stdout.strip()

        except Exception as e:
            logger.error(f"Failed to get statistics for interface {interface}: {e}")
            raise RuntimeError(
                f"Could not retrieve statistics for interface {interface}"
            ) from e
