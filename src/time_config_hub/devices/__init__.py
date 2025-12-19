"""
Device management module for Time Config Hub.

This module provides device detection, identification, and management capabilities
for Time-Sensitive Networking (TSN) enabled network devices.
"""

from importlib import import_module
from pathlib import Path

# Import the base Device class first
from .device import Device

# Auto-discover and import all device implementations
parent = Path(__file__).parent
sources = parent.rglob("*.py")
module_names = [
    f".{source.stem}"
    for source in sources
    if not source.stem.startswith("__")  # and source.stem != "device"
]

for module_name in module_names:
    import_module(module_name, __package__)

# Clean up namespace
del parent, sources, module_names, import_module, Path

# Define public API
__all__ = ["Device"]
