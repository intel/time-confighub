# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""YANG namespace → wrapper class registry.

The registries are built **automatically** at import time by discovering every
``*.py`` module inside this package and collecting all
:class:`~time_config_hub.utils.yang_parser.base_yang_config_wrapper.BaseYangConfigWrapper`
subclasses that declare a non-empty ``YANG_NAMESPACE`` / ``YANG_MODULE``.

To add support for a new YANG schema, simply drop a new module in this
package that defines a subclass — no changes to this file are needed.

Usage::

    from time_config_hub.utils.yang_parser.wrappers import get_wrapper_for_namespace

    cls = get_wrapper_for_namespace("urn:ietf:params:xml:ns:yang:ietf-interfaces")
    wrapper = cls(raw_config, parsed_dict)
"""

import importlib
import pkgutil
from pathlib import Path
from typing import Dict, Optional, Type

from time_config_hub.utils.yang_parser.base_yang_config_wrapper import (
    BaseYangConfigWrapper,
)


def _build_registries() -> (
    tuple[Dict[str, Type[BaseYangConfigWrapper]], Dict[str, Type[BaseYangConfigWrapper]]]
):
    """Auto-import all sibling modules and collect wrapper subclasses.

    :return: A ``(namespace_registry, module_registry)`` tuple.
    """
    _pkg_dir = Path(__file__).parent
    for _, mod_name, _ in pkgutil.iter_modules([str(_pkg_dir)]):
        importlib.import_module(f"{__name__}.{mod_name}")

    ns_registry: Dict[str, Type[BaseYangConfigWrapper]] = {}
    mod_registry: Dict[str, Type[BaseYangConfigWrapper]] = {}

    def _collect(cls: Type[BaseYangConfigWrapper]) -> None:
        for sub in cls.__subclasses__():
            if sub.YANG_NAMESPACE:
                ns_registry[sub.YANG_NAMESPACE] = sub
            if sub.YANG_MODULE:
                mod_registry[sub.YANG_MODULE] = sub
            _collect(sub)

    _collect(BaseYangConfigWrapper)
    return ns_registry, mod_registry


#: Maps each YANG XML namespace URI to its concrete wrapper class.
#: Populated automatically from all submodules in this package.
YANG_NAMESPACE_REGISTRY, YANG_MODULE_REGISTRY = _build_registries()


def get_wrapper_for_namespace(ns: str) -> Optional[Type[BaseYangConfigWrapper]]:
    """Return the wrapper class registered for *ns*, or ``None``.

    :param str ns: XML namespace URI (e.g. ``"urn:ietf:params:xml:ns:yang:ietf-interfaces"``).
    :return: Wrapper subclass, or ``None`` if no match is registered.
    :rtype: Optional[Type[BaseYangConfigWrapper]]
    """
    return YANG_NAMESPACE_REGISTRY.get(ns)


def get_wrapper_for_module(module_name: str) -> Optional[Type[BaseYangConfigWrapper]]:
    """Return the wrapper class registered for *module_name*, or ``None``.

    :param str module_name: Short YANG module name (e.g. ``"ietf-interfaces"``).
    :return: Wrapper subclass, or ``None`` if no match is registered.
    :rtype: Optional[Type[BaseYangConfigWrapper]]
    """
    return YANG_MODULE_REGISTRY.get(module_name)


__all__ = [
    "YANG_NAMESPACE_REGISTRY",
    "YANG_MODULE_REGISTRY",
    "get_wrapper_for_namespace",
    "get_wrapper_for_module",
]
