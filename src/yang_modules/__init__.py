"""Utilities for loading YANG modules into a libyang context.

This package provides helper functions to locate and load YANG modules, enabling
all features on successfully loaded modules.
"""

import os
from typing import Optional

import libyang

# Centralized source of truth for the default YANG module directory
DEFAULT_YANG_DIR = "/etc/tch/yang_modules"


def load_yang_module(ctx: libyang.Context, module_name: str) -> libyang.Module:
    """Search for and load a YANG module into the context if not already present.

    :param libyang.Context ctx: The libyang context to load the module into
    :param str module_name: The name of the YANG module (e.g., 'ietf-interfaces')
    :return: The loaded libyang module object
    :rtype: libyang.Module
    :raises libyang.LibyangError: If the module cannot be found or fails to compile
    """

    try:
        # load_module uses the search paths defined when the Context was initialized
        new_mod = ctx.load_module(module_name)
        new_mod.feature_enable_all()
        return new_mod
    except libyang.LibyangError as e:
        raise libyang.LibyangError(
            f"Required YANG module '{module_name}' not found or failed to load: {e}"
        ) from e
