# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
system_controller.registry — target registration and management.

Callers identify remote hosts by an identity string (``"user@host"``).
The registry maps each identity to its connection parameters and SSH key
path, stored in ``~/.tch/known_targets.json``.

Public functions
----------------
register      : Exchange SSH keys with a remote host and add it to the registry.
unregister    : Remove a host from the registry (key stays on remote).
is_registered : Return True if the identity is in the registry.
list_targets  : Return a safe view of all registered targets.
get_remote_dir: Return the remote working directory for a registered target.

Internal helpers
----------------
_parse_identity : Parse ``"user@host"`` into ``(user, host)``.
_load_target    : Reconstruct a :class:`~system_controller.target.Target`
                  from registry data; raises ``LookupError`` if not found.
"""

from __future__ import annotations

import logging

from .target import Target
from .key_exchange import _load_registry, ensure_key_auth, _save_registry
from ..common.status_codes import TchStatusCode

_log = logging.getLogger("system_controller")


# ── Identity parsing ──────────────────────────────────────────────────────────


def _parse_identity(identity: str) -> tuple[str, str]:
    """Parse an identity string into ``(user, host)``.

    :param str identity: Identity string in the form ``user@host``.
    :return: Tuple of ``(user, host)``.
    :rtype: tuple[str, str]
    :raises ValueError: If *identity* is not a valid ``user@host`` string.
    """
    parts = identity.split("@", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Invalid identity '{identity}': expected 'user@host'"
        )
    return parts[0], parts[1]


# ── Internal helpers ──────────────────────────────────────────────────────────


def _load_target(identity: str) -> "Target":
    """Reconstruct a :class:`~system_controller.target.Target` from the registry.

    Used internally by :mod:`system_controller.dispatch` to resolve an
    identity string before building SSH commands.

    :param str identity: Remote host identity as ``user@host``.
    :return: Target populated from the registry entry.
    :rtype: Target
    :raises LookupError: If *identity* is not present in the registry.
    """
    registry = _load_registry()
    if identity not in registry:
        raise LookupError(
            f"Target '{identity}' is not registered. "
            "Call system_controller.register(identity, password=...) first."
        )
    entry = registry[identity]
    return Target(
        host=entry["host"],
        user=entry["user"],
        port=entry.get("port", 22),
        remote_dir=entry.get("remote_dir", "/opt/tch"),
    )


# ── Public API ────────────────────────────────────────────────────────────────


def is_registered(identity: str) -> bool:
    """Return ``True`` if *identity* is present in the registry.

    Does **not** make a network connection.

    :param str identity: Remote host identity as ``user@host``.
    :return: True if the target is registered.
    :rtype: bool
    """
    return identity in _load_registry()


def get_remote_dir(identity: str) -> str:
    """Return the remote working directory for a registered target.

    :param str identity: Remote host identity as ``user@host``.
    :return: Remote working directory path (e.g. ``"/opt/tch"``).
    :rtype: str
    :raises LookupError: If *identity* is not registered.
    """
    return _load_target(identity).remote_dir


def register(
    identity: str,
    password: str,
    port: int = 22,
    remote_dir: str = "/opt/tch",
) -> dict:
    """Register a remote target and set up SSH key authentication.

    Parses *identity* as ``"user@host"``, then calls
    :func:`~system_controller.key_exchange.ensure_key_auth`.  On the first
    call the SSH password is required; subsequent calls return immediately
    without making any network connection.

    :param str identity: Remote host identity as ``user@host``.
    :param str password: SSH password — used only for the one-time key
        exchange and **never** written to disk.
    :param int port: SSH port (default 22).
    :param str remote_dir: Working directory on the remote host
        (default ``"/opt/tch"``).
    :return: Result dict with ``ok``, ``output``, ``data`` keys.
    :rtype: dict
    """
    try:
        user, host = _parse_identity(identity)
    except ValueError as exc:
        return {
            "status_code": TchStatusCode.USER_INPUT_ERROR,
            "output": "",
            "error": str(exc),
            "data": None,
        }

    target = Target(
        host=host,
        user=user,
        port=port,
        remote_dir=remote_dir,
        password=password,
    )
    return ensure_key_auth(target)


def unregister(identity: str) -> None:
    """Remove *identity* from the registry.

    Does **not** remove the public key from the remote host's
    ``authorized_keys``.

    :param str identity: Remote host identity as ``user@host``.
    :return: None
    :rtype: None
    """
    registry = _load_registry()
    if identity in registry:
        del registry[identity]
        _save_registry(registry)
        _log.info("[REGISTRY] unregistered %s", identity)
    else:
        _log.debug("[REGISTRY] unregister: '%s' not found, nothing to do", identity)


def list_targets() -> list[dict]:
    """Return a safe view of all registered targets.

    Passwords and raw key paths are **not** included in the response.

    :return: List of dicts with ``identity``, ``host``, ``user``, ``port``,
             ``remote_dir``, and ``added_at`` keys.
    :rtype: list[dict]
    """
    registry = _load_registry()
    return [
        {
            "identity": identity,
            "host": entry.get("host", ""),
            "user": entry.get("user", ""),
            "port": entry.get("port", 22),
            "remote_dir": entry.get("remote_dir", "/opt/tch"),
            "added_at": entry.get("added_at", ""),
        }
        for identity, entry in registry.items()
    ]
