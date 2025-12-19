"""
PCI Utilities Module for Time Config Hub.

This module provides utilities for working with PCI devices and network interfaces
in the context of Time-Sensitive Networking (TSN) configuration. It offers functionality
to retrieve PCI device information, bus addresses, vendor and device IDs, and map
between network interface names and PCI bus addresses.

The module is designed to work with Linux systems.
"""

import logging
import re

from ..commands.base_command import BaseCommand
from ..commands.ethtool_command import EthtoolCommand

logger = logging.getLogger(__name__)


class PCIUtils:
    """Utility class for PCI-related operations."""

    @staticmethod
    def get_bus_address(interface: str) -> str:
        """Get PCI bus address for a network interface.

        :param str interface: Network interface name (e.g., 'eth0', 'enp1s0')
        :return: PCI bus address in format 'DOMAIN:BUS:DEVICE.FUNCTION'
        :rtype: str
        :raises RuntimeError: if ethtool command fails or bus address not found
        :raises ValueError: if interface name is invalid or empty
        """
        if not interface or not interface.strip():
            raise ValueError("Interface name cannot be empty")

        logger.debug(f"Getting bus address for interface: {interface}")

        try:
            ethtool_cmd = EthtoolCommand()
            driver_info = ethtool_cmd.get_driver_info(interface)

            if not driver_info:
                raise RuntimeError(
                    f"No driver information available for interface: {interface}"
                )

            regex = re.compile(r"bus-info: (\S+)")
            matches = regex.findall(driver_info)

            if not matches:
                raise RuntimeError(
                    f"Bus address not found in driver info for interface: {interface}"
                )

            bus_address = matches[0]
            logger.debug(f"Found bus address for {interface}: {bus_address}")
            return bus_address

        except Exception as e:
            logger.error(f"Failed to get bus address for interface {interface}: {e}")
            raise RuntimeError(
                f"Could not retrieve bus address for interface {interface}"
            ) from e

    @staticmethod
    def get_vendor_id(interface: str) -> str:
        """Get PCI vendor ID for a network interface.

        :param str interface: Network interface name (e.g., 'eth0', 'enp1s0')
        :return: PCI vendor ID in uppercase hexadecimal format without '0x' prefix
        :rtype: str
        :raises RuntimeError: if unable to read vendor ID from sysfs
        :raises ValueError: if interface name is invalid or empty
        """
        if not interface or not interface.strip():
            raise ValueError("Interface name cannot be empty")

        logger.debug(f"Getting vendor ID for interface: {interface}")

        try:
            bus_address = PCIUtils.get_bus_address(interface)
            base_cmd = f"/sys/bus/pci/devices/{bus_address}"
            vendor_id_cmd = f"cat {base_cmd}/vendor"

            logger.debug(f"Reading vendor ID from: {base_cmd}/vendor")
            result = BaseCommand.run(vendor_id_cmd)

            if not result.stdout.strip():
                raise RuntimeError(f"Empty vendor ID for interface: {interface}")

            vendor_id = result.stdout.strip().replace("0x", "").upper()
            logger.debug(f"Found vendor ID for {interface}: {vendor_id}")
            return vendor_id

        except Exception as e:
            logger.error(f"Failed to get vendor ID for interface {interface}: {e}")
            raise RuntimeError(
                f"Could not retrieve vendor ID for interface {interface}"
            ) from e

    @staticmethod
    def get_device_id(interface: str) -> str:
        """Get PCI device ID for a network interface.

        :param str interface: Network interface name (e.g., 'eth0', 'enp1s0')
        :return: PCI device ID in uppercase hexadecimal format without '0x' prefix
        :rtype: str
        :raises RuntimeError: if unable to read device ID from sysfs
        :raises ValueError: if interface name is invalid or empty
        """
        if not interface or not interface.strip():
            raise ValueError("Interface name cannot be empty")

        logger.debug(f"Getting device ID for interface: {interface}")

        try:
            bus_info = PCIUtils.get_bus_address(interface)
            base_cmd = f"/sys/bus/pci/devices/{bus_info}"
            device_id_cmd = f"cat {base_cmd}/device"

            logger.debug(f"Reading device ID from: {base_cmd}/device")
            result = BaseCommand.run(device_id_cmd)

            if not result.stdout.strip():
                raise RuntimeError(f"Empty device ID for interface: {interface}")

            device_id = result.stdout.strip().replace("0x", "").upper()
            logger.debug(f"Found device ID for {interface}: {device_id}")
            return device_id

        except Exception as e:
            logger.error(f"Failed to get device ID for interface {interface}: {e}")
            raise RuntimeError(
                f"Could not retrieve device ID for interface {interface}"
            ) from e

    @staticmethod
    def get_pci_id(interface: str) -> str:
        """Get combined PCI vendor:device ID for a network interface.

        :param str interface: Network interface name (e.g., 'eth0', 'enp1s0')
        :return: PCI ID in format 'VENDOR:DEVICE' (e.g., '8086:125B')
        :rtype: str
        :raises RuntimeError: if unable to read vendor or device ID
        :raises ValueError: if interface name is invalid or empty
        """
        if not interface or not interface.strip():
            raise ValueError("Interface name cannot be empty")

        logger.debug(f"Getting PCI ID for interface: {interface}")

        try:
            vendor_id = PCIUtils.get_vendor_id(interface)
            device_id = PCIUtils.get_device_id(interface)

            pci_id = f"{vendor_id}:{device_id}"
            logger.debug(f"Found PCI ID for {interface}: {pci_id}")
            return pci_id

        except Exception as e:
            logger.error(f"Failed to get PCI ID for interface {interface}: {e}")
            raise RuntimeError(
                f"Could not retrieve PCI ID for interface {interface}"
            ) from e

    @staticmethod
    def get_interface_by_bus_address(bus_address: str) -> str:
        """Get network interface name from PCI bus address.

        :param str bus_address: PCI bus address in format 'DOMAIN:BUS:DEVICE.FUNCTION'
        :return: Network interface name (e.g., 'eth0', 'enp1s0')
        :rtype: str
        :raises RuntimeError: if unable to find interface for the given bus address
        :raises ValueError: if bus address is invalid or empty
        """
        if not bus_address or not bus_address.strip():
            raise ValueError("Bus address cannot be empty")

        # Validate bus address format
        bus_pattern = re.compile(
            r"^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]$"
        )
        if not bus_pattern.match(bus_address):
            raise ValueError(
                f"Invalid bus address format: {bus_address}. "
                "Expected format: DOMAIN:BUS:DEVICE.FUNCTION"
            )

        logger.debug(f"Getting interface for bus address: {bus_address}")

        try:
            cmd = f"ls /sys/bus/pci/devices/{bus_address}/net"
            logger.debug(f"Running command: {cmd}")
            result = BaseCommand.run(cmd)

            if not result.stdout.strip():
                raise RuntimeError(
                    f"No network interface found for bus address: {bus_address}"
                )

            interfaces = result.stdout.strip().split()
            if not interfaces:
                raise RuntimeError(
                    f"No network interface found for bus address: {bus_address}"
                )

            interface = interfaces[0]
            logger.debug(f"Found interface for bus address {bus_address}: {interface}")
            return interface

        except Exception as e:
            logger.error(f"Failed to find interface for bus address {bus_address}: {e}")
            raise RuntimeError(
                f"Could not find interface for bus address {bus_address}"
            ) from e
