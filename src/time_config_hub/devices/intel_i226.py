"""Intel I226 network device implementation.

This module provides the IntelI226 device class for Intel I226 network controllers.
The I226 is a 2.5 Gigabit Ethernet controller with Time-Sensitive Networking (TSN)
capabilities, commonly used in embedded and automotive applications.

Example:
    ```python
    from time_config_hub.devices.intel_i226 import IntelI226

    # Create device instance
    device = IntelI226('eth0')
    print(f"Device: {device}")
    print(f"TX Queues: {device.NUM_TX_QUEUES}")
    print(f"RX Queues: {device.NUM_RX_QUEUES}")
    ```
"""

import logging

from .device import Device

logger = logging.getLogger(__name__)


class IntelI226(Device):
    """Intel I226 Ethernet Controller device implementation.

    The Intel I226 is a 2.5 Gigabit Ethernet controller with TSN capabilities.
    This class provides device-specific configuration and management for
    I226 controllers.

    :cvar VALID_PCI_IDS: List of supported PCI ID strings for I226 variants
    :type VALID_PCI_IDS: List[str]
    :cvar NUM_TX_QUEUES: Number of transmit queues (4 for I226)
    :type NUM_TX_QUEUES: int
    :cvar NUM_RX_QUEUES: Number of receive queues (4 for I226)
    :type NUM_RX_QUEUES: int
    """

    NAME: str = "Intel I226"
    VALID_PCI_IDS = ["8086:125B", "8086:125D"]
    NUM_TX_QUEUES = 4
    NUM_RX_QUEUES = 4

    def __init__(self, interface: str):
        """Initialize an Intel I226 device instance.

        :param str interface: Network interface name (e.g., 'eth0', 'enp1s0')
        :raises ValueError: if interface name is invalid or empty
        :raises RuntimeError: if the device is not a valid I226 controller
        """
        logger.debug(f"Initializing IntelI226 device for interface: {interface}")

        try:
            super().__init__(interface)
            logger.info(
                f"Successfully initialized IntelI226 device for interface {interface} "
                f"(PCI ID: {self.pci_id})"
            )

        except Exception as e:
            logger.error(
                f"Failed to initialize IntelI226 device for interface {interface}: {e}"
            )
            raise RuntimeError(
                f"Could not initialize IntelI226 device for interface {interface}"
            ) from e
