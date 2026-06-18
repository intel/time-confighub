# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
system_controller.key_exchange — SSH public-key setup for remote targets.

Flow
----
1. On first connection to a new ``Target``, call :func:`ensure_key_auth`.
   - Generates ``~/.ssh/tch_ed25519`` if it does not exist.
   - Copies the public key to the remote host using ``sshpass`` + ``ssh-copy-id``.
   - Marks the target as ready in ``~/.tch/known_targets.json``.
2. All subsequent calls to :func:`~system_controller.dispatch.run` or
   :func:`~system_controller.dispatch.scp_fetch` use key-based auth only —
   no password, no ``sshpass``.

The password is used **exclusively** inside :func:`ensure_key_auth` and is
**never** written to disk.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .target import Target
from time_config_hub.utils.common import TchStatusCode

_log = logging.getLogger("system_controller")

_SSH_KEY = Path.home() / ".ssh" / "tch_ed25519"
_REGISTRY_PATH = Path.home() / ".tch" / "known_targets.json"


# ── Registry helpers ──────────────────────────────────────────────────────────


def _load_registry() -> dict:
    """Load the known-targets registry from disk.

    :return: Registry dict keyed by ``user@host`` identity strings.
    :rtype: dict
    """
    try:
        return json.loads(_REGISTRY_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_registry(data: dict) -> None:
    """Atomically write *data* to the known-targets registry.

    :param dict data: Registry dict to persist.
    :return: None
    :rtype: None
    """
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _REGISTRY_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2))
    tmp_path.replace(_REGISTRY_PATH)
    _log.debug("[KEY] registry saved to %s", _REGISTRY_PATH)


# ── Key generation ────────────────────────────────────────────────────────────


def _generate_key() -> None:
    """Generate the TCH ed25519 SSH key pair if it does not already exist.

    :return: None
    :rtype: None
    :raises RuntimeError: If ``ssh-keygen`` fails.
    """
    if _SSH_KEY.exists():
        _log.debug("[KEY] key already exists at %s", _SSH_KEY)
        return

    _SSH_KEY.parent.mkdir(parents=True, exist_ok=True)
    _log.info("[KEY] generating new ed25519 key at %s", _SSH_KEY)
    result = subprocess.run(
        [
            "ssh-keygen",
            "-t", "ed25519",
            "-N", "",            # no passphrase
            "-C", "tch-controller",
            "-f", str(_SSH_KEY),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ssh-keygen failed: {(result.stdout + result.stderr).strip()}"
        )
    # Restrict permissions on the private key
    os.chmod(_SSH_KEY, 0o600)
    _log.info("[KEY] key pair created at %s", _SSH_KEY)


# ── Public API ────────────────────────────────────────────────────────────────


def is_key_auth_ready(target: "Target") -> bool:
    """Return ``True`` if key-based SSH auth is already set up for *target*.

    Checks the local registry only — does **not** make a network connection.

    :param Target target: Remote host to check.
    :return: ``True`` if the target identity is present in the registry.
    :rtype: bool
    """
    registry = _load_registry()
    ready = target.identity in registry
    _log.debug(
        "[KEY] is_key_auth_ready(%s) → %s", target.identity, ready
    )
    return ready


def ensure_key_auth(target: "Target") -> dict:
    """Set up key-based SSH authentication for *target* (one-time operation).

    Steps:

    1. Generate ``~/.ssh/tch_ed25519`` if it does not already exist.
    2. Use ``sshpass`` + ``ssh-copy-id`` to copy the public key to the remote
       host.  The password from ``target.password`` is used **only** for this
       step and is never written to disk.
    3. Verify the key works by attempting a ``BatchMode`` connection.
    4. Record the target identity in ``~/.tch/known_targets.json``.

    If *target* is already in the registry this function returns immediately
    with ``ok=True`` without making any network connection.

    :param Target target: Remote host to set up.  ``target.password`` must be
        set if key auth is not already in place.
    :return: Result dict with ``ok``, ``output``, ``data`` keys.
    :rtype: dict
    :raises ValueError: If *target.password* is empty and key auth is not set up.
    """
    if is_key_auth_ready(target):
        _log.info("[KEY] key auth already ready for %s", target.identity)
        return {
            "status_code": TchStatusCode.SUCCESS,
            "output": f"Key auth already set up for {target.identity}",
            "error": "",
            "data": None,
        }

    if not target.password:
        return {
            "status_code": TchStatusCode.USER_INPUT_ERROR,
            "output": "",
            "error": (
                f"SSH password required for first-time key exchange with "
                f"{target.identity}. Provide target.password."
            ),
            "data": None,
        }

    _log.info("[KEY] starting key exchange for %s", target.identity)

    try:
        _generate_key()
    except RuntimeError as exc:
        return {
            "status_code": TchStatusCode.ERROR,
            "output": "",
            "error": str(exc),
            "data": None,
        }

    pub_key = (_SSH_KEY.with_suffix(".pub")).read_text().strip()

    # Use ssh-copy-id with sshpass for the one-time key exchange.
    # sshpass is only used here; all subsequent commands use BatchMode.
    result = subprocess.run(
        [
            "sshpass", "-p", target.password,
            "ssh-copy-id",
            "-i", str(_SSH_KEY.with_suffix(".pub")),
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=15",
            "-p", str(target.port),
            target.identity,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        _log.warning("[KEY] ssh-copy-id failed for %s: %s", target.identity, output[:200])
        return {
            "status_code": TchStatusCode.REMOTE_ERROR,
            "output": "",
            "error": f"Key exchange failed: {output[:200]}",
            "data": None,
        }

    # Verify the key actually works before updating the registry
    verify = subprocess.run(
        [
            "ssh",
            "-i", str(_SSH_KEY),
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10",
            "-p", str(target.port),
            target.identity,
            "echo tch-key-ok",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )

    if verify.returncode != 0 or "tch-key-ok" not in verify.stdout:
        output = (verify.stdout + verify.stderr).strip()
        _log.warning("[KEY] key verification failed for %s: %s", target.identity, output[:200])
        return {
            "status_code": TchStatusCode.REMOTE_ERROR,
            "output": "",
            "error": f"Key copied but verification failed: {output[:200]}",
            "data": None,
        }

    # Record in registry
    registry = _load_registry()
    registry[target.identity] = {
        "key_path": str(_SSH_KEY),
        "host": target.host,
        "user": target.user,
        "port": target.port,
        "remote_dir": target.remote_dir,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_registry(registry)

    _log.info("[KEY] key exchange successful for %s", target.identity)
    return {
        "status_code": TchStatusCode.SUCCESS,
        "output": f"Key-based SSH auth set up for {target.identity}",
        "error": "",
        "data": {"key_path": str(_SSH_KEY), "pub_key": pub_key},
    }


def remove_key_auth(target: "Target") -> None:
    """Remove *target* from the known-targets registry.

    Does not remove the key from the remote host's ``authorized_keys``.

    :param Target target: Remote host to deregister.
    :return: None
    :rtype: None
    """
    registry = _load_registry()
    if target.identity in registry:
        del registry[target.identity]
        _save_registry(registry)
        _log.info("[KEY] removed %s from registry", target.identity)
