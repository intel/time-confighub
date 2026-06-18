# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
system_controller — local/remote command dispatch with SSH key-auth lifecycle.

Callers identify remote hosts by an identity string (``"user@host"``).
Call :func:`register` once (with a password) to exchange SSH keys; all
subsequent calls use the key transparently.

Public API
----------
register               : Exchange SSH keys with a remote host and register it.
unregister             : Remove a host from the registry.
is_registered          : Return True if the identity is registered.
list_targets           : Return a safe view of all registered targets.
get_remote_dir         : Return the remote working directory for a registered target.
run                    : Execute a command locally or on a registered remote target.
get_file               : Copy a file or directory from a remote target to a local path.
put_file               : Upload a local file or directory to a path on a remote target.
start_remote_process   : Start a long-running command on a remote target (non-blocking).
get_network_interfaces : Enumerate network interfaces on a local or remote host.
"""

from .dispatch import get_file, get_network_interfaces, put_file, run, start_remote_process
from .registry import (
    get_remote_dir,
    is_registered,
    list_targets,
    register,
    unregister,
)

__all__ = [
    "register",
    "unregister",
    "is_registered",
    "list_targets",
    "get_remote_dir",
    "run",
    "get_file",
    "put_file",
    "start_remote_process",
    "get_network_interfaces",
]
