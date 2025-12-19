"""Device abstraction for network interfaces.

This module provides a base Device class for network device implementations.
All device-specific subclasses must define VALID_PCI_IDS as a list of supported
PCI ID strings in the format 'VENDOR:DEVICE' (e.g., '8086:125B').
"""

import logging
from typing import List, Type

from ..utils.pci_utils import PCIUtils

logger = logging.getLogger(__name__)


class Device:
    """Base class for network device implementations.

    All subclasses must define _VALID_PCI_IDS as a list of valid PCI ID strings.

    :ivar VALID_PCI_IDS: List of supported PCI ID strings in format 'VENDOR:DEVICE'
    :type VALID_PCI_IDS: List[str]
    :ivar NUM_TX_QUEUES: Number of transmit queues supported by the device
    :type NUM_TX_QUEUES: int
    :ivar NUM_RX_QUEUES: Number of receive queues supported by the device
    :type NUM_RX_QUEUES: int
    """

    NAME: str = "GenericDevice"
    VALID_PCI_IDS: List[str]  # Must be overridden in subclasses
    NUM_TX_QUEUES = 1
    NUM_RX_QUEUES = 1

    def __init__(self, interface: str):
        """Initialize a Device instance.

        :param str interface: Network interface name (e.g., 'eth0', 'enp1s0')
        :raises ValueError: if interface name is invalid or empty
        """
        if not interface or not interface.strip():
            raise ValueError("Interface name cannot be empty")

        self.interface = interface.strip()
        self._bus_info = None
        self._vendor_id = None
        self._device_id = None

        logger.debug(f"Initialized Device for interface: {self.interface}")

        # Validate that this device matches the expected PCI IDs
        self._validate_device_pci_id()

    def _validate_device_pci_id(self) -> None:
        """Validate that the device's PCI ID matches the class's VALID_PCI_IDS.

        This method ensures that the device instance matches one of the expected
        PCI IDs for this device class. It should be called during initialization.

        :raises RuntimeError: if the device's PCI ID doesn't match VALID_PCI_IDS
        :raises AttributeError: if the device class doesn't define VALID_PCI_IDS
        """
        # Skip validation for the base Device class
        if self.__class__ == Device:
            return

        # Ensure the subclass has VALID_PCI_IDS defined
        if not hasattr(self.__class__, "VALID_PCI_IDS"):
            raise AttributeError(
                f"Device class {self.__class__.__name__} must define "
                "VALID_PCI_IDS attribute"
            )

        if not self.__class__.VALID_PCI_IDS:
            raise AttributeError(
                f"Device class {self.__class__.__name__} has empty VALID_PCI_IDS list"
            )

        try:
            actual_pci_id = self.pci_id

            if actual_pci_id not in self.__class__.VALID_PCI_IDS:
                raise RuntimeError(
                    f"Device {self.interface} with PCI ID {actual_pci_id} "
                    f"is not a valid {self.__class__.__name__} controller. "
                    f"Expected one of: {self.__class__.VALID_PCI_IDS}"
                )

            logger.debug(
                f"PCI ID validation passed for {self.__class__.__name__}: "
                f"{actual_pci_id}"
            )

        except RuntimeError:
            # Re-raise our specific validation errors
            raise
        except (ValueError, AttributeError):
            # Re-raise configuration/attribute errors
            raise
        except Exception as e:
            # Wrap other unexpected errors
            logger.error(
                f"Failed to validate PCI ID for {self.__class__.__name__} "
                f"on interface {self.interface}: {e}"
            )
            raise RuntimeError(
                f"Could not validate device type for {self.__class__.__name__} "
                f"on interface {self.interface}"
            ) from e

    def __str__(self) -> str:
        """String representation of the device.

        :return: Human-readable string representation
        :rtype: str
        """
        try:
            return (
                f"{self.__class__.__name__}"
                f"(interface='{self.interface}', pci_id='{self.pci_id}')"
            )
        except (RuntimeError, ValueError):
            return (
                f"{self.__class__.__name__}"
                f"(interface='{self.interface}', pci_id='<unknown>')"
            )

    def __repr__(self) -> str:
        """Detailed string representation of the device.

        :return: Detailed string representation for debugging
        :rtype: str
        """
        return self.__str__()

    @property
    def bus_info(self) -> str:
        """Lazy-loaded bus information.

        :return: PCI bus address in format 'DOMAIN:BUS:DEVICE.FUNCTION'
        :rtype: str
        :raises RuntimeError: if unable to retrieve bus information
        """
        if self._bus_info is None:
            try:
                self._bus_info = PCIUtils.get_bus_address(self.interface)
                logger.debug(f"Cached bus info for {self.interface}: {self._bus_info}")
            except Exception as e:
                logger.error(f"Failed to get bus info for {self.interface}: {e}")
                raise RuntimeError(
                    f"Could not retrieve bus information for interface {self.interface}"
                ) from e
        return self._bus_info

    @property
    def vendor_id(self) -> str:
        """Lazy-loaded vendor ID.

        :return: PCI vendor ID in uppercase hexadecimal format
        :rtype: str
        :raises RuntimeError: if unable to retrieve vendor ID
        """
        if self._vendor_id is None:
            try:
                self._vendor_id = PCIUtils.get_vendor_id(self.interface)
                logger.debug(
                    f"Cached vendor ID for {self.interface}: {self._vendor_id}"
                )
            except Exception as e:
                logger.error(f"Failed to get vendor ID for {self.interface}: {e}")
                raise RuntimeError(
                    f"Could not retrieve vendor ID for interface {self.interface}"
                ) from e
        return self._vendor_id

    @property
    def device_id(self) -> str:
        """Lazy-loaded device ID.

        :return: PCI device ID in uppercase hexadecimal format
        :rtype: str
        :raises RuntimeError: if unable to retrieve device ID
        """
        if self._device_id is None:
            try:
                self._device_id = PCIUtils.get_device_id(self.interface)
                logger.debug(
                    f"Cached device ID for {self.interface}: {self._device_id}"
                )
            except Exception as e:
                logger.error(f"Failed to get device ID for {self.interface}: {e}")
                raise RuntimeError(
                    f"Could not retrieve device ID for interface {self.interface}"
                ) from e
        return self._device_id

    @property
    def pci_id(self) -> str:
        """Computed PCI ID from vendor and device IDs.

        :return: PCI ID in format 'VENDOR:DEVICE' (e.g., '8086:125B')
        :rtype: str
        :raises RuntimeError: if unable to retrieve vendor or device ID
        """
        try:
            pci_id = f"{self.vendor_id}:{self.device_id}"
            return pci_id
        except Exception as e:
            logger.error(f"Failed to compute PCI ID for {self.interface}: {e}")
            raise RuntimeError(
                f"Could not compute PCI ID for interface {self.interface}"
            ) from e

    @classmethod
    def _get_device_class_by_pci_id(cls, pci_id: str) -> Type["Device"]:
        """Helper method to retrieve the device class for a given PCI ID.

        :param str pci_id: PCI ID string in format "VENDOR:DEVICE" (e.g., "8086:125B")
        :return: Device class for the matching PCI ID
        :rtype: Type[Device]
        :raises ValueError: if PCI ID format is invalid
        :raises NameError: if the PCI ID is not recognized by any device class
        """
        if not pci_id or not pci_id.strip():
            raise ValueError("PCI ID cannot be empty")

        pci_id = pci_id.strip().upper()

        # Validate PCI ID format
        if ":" not in pci_id:
            raise ValueError(
                f"Invalid PCI ID format: {pci_id}. Expected format: VENDOR:DEVICE"
            )

        parts = pci_id.split(":")
        if len(parts) != 2:
            raise ValueError(
                f"Invalid PCI ID format: {pci_id}. Expected format: VENDOR:DEVICE"
            )

        vendor, device = parts
        if not vendor or not device:
            raise ValueError(
                f"Invalid PCI ID format: {pci_id}. "
                "Vendor and device parts cannot be empty"
            )

        logger.debug(f"Looking for device class for PCI ID: {pci_id}")

        device_classes: List[Type[Device]] = cls.__subclasses__()

        if not device_classes:
            logger.warning("No device subclasses found")

        for device_class in device_classes:
            if not hasattr(device_class, "VALID_PCI_IDS"):
                logger.warning(
                    f"Device class {device_class.__name__} "
                    "missing VALID_PCI_IDS attribute"
                )
                continue

            if pci_id in device_class.VALID_PCI_IDS:
                logger.debug(f"Found matching device class: {device_class.__name__}")
                return device_class

        available_ids = []
        for device_class in device_classes:
            if hasattr(device_class, "VALID_PCI_IDS"):
                available_ids.extend(device_class.VALID_PCI_IDS)

        logger.error(
            f"Unrecognized PCI ID: {pci_id}. Available PCI IDs: {available_ids}"
        )
        raise NameError(f"Unrecognized PCI ID: {pci_id}")

    @classmethod
    def from_bus_address(cls, bus_address: str) -> "Device":
        """Instantiate a Device subclass based on the PCI bus address.

        :param str bus_address: PCI bus address in format "DOMAIN:BUS:DEVICE.FUNCTION"
        :return: Instance of the appropriate Device subclass
        :rtype: Device
        :raises ValueError: if bus address format is invalid
        :raises RuntimeError: if unable to find interface for bus address
        :raises NameError: if the PCI ID is not recognized by any device class
        """
        if not bus_address or not bus_address.strip():
            raise ValueError("Bus address cannot be empty")

        bus_address = bus_address.strip()
        logger.debug(f"Creating device from bus address: {bus_address}")

        try:
            interface = PCIUtils.get_interface_by_bus_address(bus_address)
            logger.debug(f"Found interface {interface} for bus address {bus_address}")
            return cls.from_interface(interface)
        except Exception as e:
            logger.error(f"Failed to create device from bus address {bus_address}: {e}")
            raise RuntimeError(
                f"Could not create device from bus address {bus_address}"
            ) from e

    @classmethod
    def from_interface(cls, interface: str) -> "Device":
        """Instantiate a Device subclass based on the network interface name.

        :param str interface: Network interface name (e.g., 'eth0', 'enp1s0')
        :return: Instance of the appropriate Device subclass
        :rtype: Device
        :raises ValueError: if interface name is invalid or empty
        :raises RuntimeError: if unable to determine PCI ID for interface
        :raises NameError: if the PCI ID is not recognized by any device class
        """
        if not interface or not interface.strip():
            raise ValueError("Interface name cannot be empty")

        interface = interface.strip()
        logger.debug(f"Creating device from interface: {interface}")

        try:
            pci_id = PCIUtils.get_pci_id(interface)
            logger.debug(f"Found PCI ID {pci_id} for interface {interface}")

            device_cls = cls._get_device_class_by_pci_id(pci_id)
            device = device_cls(interface)

            logger.info(
                f"Created {device_cls.__name__} device for interface {interface} "
                f"(PCI ID: {pci_id})"
            )
            return device

        except Exception as e:
            logger.error(f"Failed to create device from interface {interface}: {e}")
            raise RuntimeError(
                f"Could not create device from interface {interface}"
            ) from e
