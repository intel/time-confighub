# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
system_controller.dispatch — command execution for local and remote targets.

Public functions
----------------
run                  : Execute a command locally or on a remote target (by identity string).
get_file             : Copy a file or directory from a remote target to a local path.
put_file             : Upload a local file or directory to a path on a remote target.
start_remote_process : Launch a long-running command on a remote target (non-blocking Popen).
get_network_interfaces : Enumerate network interfaces on a local or remote host.

Internal helpers
----------------
_run_local   : ``subprocess.run`` wrapper returning an ok/fail result dict.
_run_remote  : SSH wrapper for a resolved Target object.
_ssh_cmd     : Build the ``ssh`` invocation list for a target.
_scp_cmd     : Build the ``scp`` invocation list for a target.
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess # nosec B404 (Controlled usage without shell=True)
from pathlib import Path
from typing import Optional

from .target import Target
from .registry import _load_target
from ..common.status_codes import TchStatusCode

_log = logging.getLogger("system_controller")


# ── Result helpers ────────────────────────────────────────────────────────────


def _ok(output: str = "", data=None) -> dict:
    """Return a success result dict.

    :param str output: Captured stdout/stderr or human-readable message.
    :param data: Optional payload; ``None`` for operations with no data.
    :return: Result dict with ``status_code``, ``output``, ``error``, ``data``.
    :rtype: dict
    """
    return {"status_code": TchStatusCode.SUCCESS, "output": output, "error": "", "data": data}


def _fail(
    error: str,
    status_code: TchStatusCode = TchStatusCode.ERROR,
    output: str = "",
) -> dict:
    """Return a failure result dict.

    :param str error: Human-readable failure message.
    :param TchStatusCode status_code: Specific failure code (default ERROR).
    :param str output: Captured stdout/stderr if any.
    :return: Result dict with ``status_code``, ``output``, ``error``, ``data``.
    :rtype: dict
    """
    return {"status_code": status_code, "output": output, "error": error, "data": None}


# ── SSH / SCP command builders ────────────────────────────────────────────────


def _ssh_key_path() -> Path:
    """Return the path to the dedicated TCH SSH private key.

    :return: Path to ``~/.ssh/tch_ed25519``.
    :rtype: Path
    """
    return Path.home() / ".ssh" / "tch_ed25519"


def _ssh_cmd(target: "Target") -> list[str]:
    """Build the base ``ssh`` command list for key-based authentication.

    Uses ``BatchMode=yes`` so the command fails immediately instead of
    prompting for a password when key auth is not set up.
    ``StrictHostKeyChecking=accept-new`` trusts new host keys but rejects
    changed ones (mitigates MITM against known hosts).

    :param Target target: Remote host parameters.
    :return: SSH command prefix list.
    :rtype: list[str]
    """
    return [
        "ssh",
        "-i", str(_ssh_key_path()),
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        "-p", str(target.port),
        target.identity,
    ]


def _scp_cmd(target: "Target") -> list[str]:
    """Build the base ``scp`` command list for key-based authentication.

    :param Target target: Remote host parameters.
    :return: SCP command prefix list.
    :rtype: list[str]
    """
    return [
        "scp",
        "-i", str(_ssh_key_path()),
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-P", str(target.port),
    ]


# ── Local / remote runners ────────────────────────────────────────────────────


def _run_local(cmd: list[str], timeout: int = 600) -> dict:
    """Run *cmd* as a local subprocess and return an ok/fail result dict.

    :param list[str] cmd: Command and arguments.
    :param int timeout: Maximum seconds to wait.
    :return: Result dict with ``ok``, ``output``, ``data`` keys.
    :rtype: dict
    """
    cmd_str = " ".join(str(c) for c in cmd)
    _log.debug("[RUN] local cmd: %s", cmd_str)
    try:
        result = subprocess.run( #nosec B603 (Controlled usage without shell=True and user input is formatted as a list)
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            _log.debug("[RUN] local exit=0 output: %s", output[:120])
            return _ok(output)
        _log.warning(
            "[RUN] local exit=%d cmd: %s  output: %s",
            result.returncode,
            cmd_str[:120],
            output[:200],
        )
        return _fail(output or f"Exit code {result.returncode}", output=output)
    except subprocess.TimeoutExpired:
        _log.error("[RUN] local TIMEOUT after %ds — cmd: %s", timeout, cmd_str[:120])
        return _fail(f"Timed out after {timeout}s", TchStatusCode.TIMEOUT)
    except FileNotFoundError as exc:
        _log.error("[RUN] local command not found: %s", exc)
        return _fail(str(exc))


def _run_remote(target, remote_cmd: str, timeout: int = 600) -> dict:
    """Run *remote_cmd* on *target* via key-based SSH.

    *target* must be a resolved ``Target`` object loaded from the registry.
    General errors from the SSH subprocess are promoted to ``REMOTE_ERROR``;
    ``TIMEOUT`` is preserved as-is.

    :param target: Remote host parameters (internal Target object).
    :param str remote_cmd: Shell command string to execute on the remote host.
    :param int timeout: Maximum seconds to wait.
    :return: Result dict with ``status_code``, ``output``, ``error``, ``data``.
    :rtype: dict
    """
    _log.debug(
        "[RUN] remote [%s] cmd: %s",
        target.identity,
        remote_cmd[:200],
    )
    cmd = _ssh_cmd(target) + [remote_cmd]
    result = _run_local(cmd, timeout=timeout)
    if result["status_code"] == TchStatusCode.ERROR:
        return {**result, "status_code": TchStatusCode.REMOTE_ERROR}
    return result


# ── Public API ────────────────────────────────────────────────────────────────


def run(
    cmd: "list[str] | str",
    target_id: Optional[str] = None,
    timeout: int = 600,
) -> dict:
    """Execute *cmd* locally or on a registered remote target.

    When *target_id* is ``None``, the command runs on localhost via
    ``subprocess.run``.  When *target_id* is provided (e.g.
    ``"root@10.0.0.1"``), the command runs on the remote host via SSH
    using the pre-exchanged key.

    For remote execution *cmd* may be a ``list[str]`` (shell-quoted
    automatically) or a pre-built shell command ``str``.

    :param cmd: Command to execute.  Local: ``list[str]`` required.
        Remote: ``list[str]`` or ``str``.
    :type cmd: list[str] or str
    :param target_id: Remote host identity as ``"user@host"``, or ``None``
        for localhost.
    :type target_id: str or None
    :param int timeout: Maximum seconds to wait (default 600).
    :return: Result dict with ``status_code``, ``output``, ``error``, ``data``.
    :rtype: dict
    """
    if target_id is None:
        if isinstance(cmd, str):
            _log.error("[RUN] local execution requires a list, not a bare string")
            return _fail(
                "Local execution requires a list, not a bare string",
                TchStatusCode.USER_INPUT_ERROR,
            )
        return _run_local(cmd, timeout=timeout)

    try:
        target = _load_target(target_id)
    except LookupError as exc:
        _log.error("[RUN] %s", exc)
        return _fail(str(exc), TchStatusCode.NOT_FOUND)

    remote_cmd = (
        cmd if isinstance(cmd, str) else shlex.join(str(c) for c in cmd)
    )
    return _run_remote(target, remote_cmd, timeout=timeout)


def start_remote_process(
    cmd: "list[str] | str",
    target_id: str,
) -> "subprocess.Popen | None":
    """Start a long-running command on a remote target without blocking.

    Returns a :class:`subprocess.Popen` handle wrapping the SSH connection
    so the caller can poll or terminate the process.  Use this instead of
    :func:`run` when the remote command must run in the background.

    :param cmd: Shell command to execute on the remote host.
    :type cmd: list[str] or str
    :param str target_id: Remote host identity as ``"user@host"``.
    :return: Popen handle, or ``None`` if the target is not registered or
        the SSH binary is missing.
    :rtype: subprocess.Popen or None
    """
    try:
        target = _load_target(target_id)
    except LookupError as exc:
        _log.error("[POPEN] %s", exc)
        return None

    remote_cmd = (
        cmd if isinstance(cmd, str) else shlex.join(str(c) for c in cmd)
    )
    _log.debug("[POPEN] [%s] cmd: %s", target_id, remote_cmd[:200])
    ssh_cmd = _ssh_cmd(target) + [remote_cmd]
    try:
        return subprocess.Popen(
            ssh_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ) #nosec B603 (Controlled usage without shell=True and user input is formatted as a list)
    except FileNotFoundError:
        _log.error("[POPEN] ssh binary not found")
        return None


def get_file(
    remote_path: str,
    local_path: "str | Path",
    target_id: str,
    timeout: int = 60,
    recursive: bool = False,
) -> dict:
    """Copy a file or directory from a registered remote target to a local path.

    Parent directories of *local_path* are created automatically.  Pass
    ``recursive=True`` to copy a remote directory tree.

    :param str remote_path: Absolute path on the remote host to retrieve.
    :param local_path: Destination path on the local machine.
    :type local_path: str or Path
    :param str target_id: Remote host identity as ``"user@host"``.
    :param int timeout: Maximum seconds to wait for the transfer (default 60).
    :param bool recursive: Copy directories recursively (default False).
    :return: Result dict with ``status_code``, ``output``, ``error``, ``data``.
        On success ``data`` contains ``{"local_path": str}``.
    :rtype: dict
    """
    try:
        target = _load_target(target_id)
    except LookupError as exc:
        _log.error("[GET] %s", exc)
        return _fail(str(exc), TchStatusCode.NOT_FOUND)

    local = Path(local_path)
    local.parent.mkdir(parents=True, exist_ok=True)

    base_cmd = _scp_cmd(target)
    if recursive:
        base_cmd = base_cmd + ["-r"]
    cmd = base_cmd + [f"{target.identity}:{remote_path}", str(local)]
    _log.debug("[GET] %s:%s → %s (recursive=%s)", target.identity, remote_path, local, recursive)

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout) #nosec B603 (Controlled usage without shell=True and user input is formatted as a list)
    except subprocess.TimeoutExpired:
        _log.warning("[GET] TIMEOUT after %ds — %s:%s", timeout, target_id, remote_path)
        return _fail(f"Timed out after {timeout}s", TchStatusCode.TIMEOUT)
    except FileNotFoundError:
        _log.error("[GET] scp binary not found")
        return _fail("scp binary not found")

    if result.returncode == 0:
        _log.debug("[GET] OK — saved to %s", local)
        return _ok(f"Downloaded {remote_path} → {local}", data={"local_path": str(local)})

    msg = (result.stderr or b"").decode(errors="replace").strip()[:200]
    _log.warning("[GET] failed (exit=%d): %s", result.returncode, msg)
    return _fail(msg or f"scp exited with code {result.returncode}", TchStatusCode.REMOTE_ERROR)


def put_file(
    local_path: "str | Path",
    remote_path: str,
    target_id: str,
    timeout: int = 60,
    recursive: bool = False,
) -> dict:
    """Upload a local file or directory to a specific path on a registered remote target.

    The remote parent directory is created automatically before the transfer.
    Pass ``recursive=True`` to upload a local directory tree.

    :param local_path: Path to the local file or directory to upload.
    :type local_path: str or Path
    :param str remote_path: Absolute destination path on the remote host.
    :param str target_id: Remote host identity as ``"user@host"``.
    :param int timeout: Maximum seconds to wait for the transfer (default 60).
    :param bool recursive: Upload directories recursively (default False).
    :return: Result dict with ``status_code``, ``output``, ``error``, ``data``.
        On success ``data`` contains ``{"remote_path": str}``.
    :rtype: dict
    """
    try:
        target = _load_target(target_id)
    except LookupError as exc:
        _log.error("[PUT] %s", exc)
        return _fail(str(exc), TchStatusCode.NOT_FOUND)

    local = Path(local_path)
    if not local.exists():
        return _fail(f"Local path not found: {local}", TchStatusCode.NOT_FOUND)

    if local.is_dir() and not recursive:
        return _fail(
            f"'{local}' is a directory — pass recursive=True to upload directories.",
            TchStatusCode.USER_INPUT_ERROR,
        )

    # Ensure the remote parent directory exists before transferring
    remote_dir = str(Path(remote_path).parent)
    mkdir_result = _run_remote(target, f"mkdir -p {remote_dir}", timeout=15)
    if mkdir_result["status_code"] != TchStatusCode.SUCCESS:
        _log.warning("[PUT] could not create remote dir %s: %s", remote_dir, mkdir_result["error"][:80])

    base_cmd = _scp_cmd(target)
    if recursive:
        base_cmd = base_cmd + ["-r"]
    cmd = base_cmd + [str(local), f"{target.identity}:{remote_path}"]
    _log.debug("[PUT] %s → %s:%s (recursive=%s)", local, target.identity, remote_path, recursive)

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout) #nosec B603 (Controlled usage without shell=True and user input is formatted as a list)
    except subprocess.TimeoutExpired:
        _log.warning("[PUT] TIMEOUT after %ds — %s → %s:%s", timeout, local, target_id, remote_path)
        return _fail(f"Timed out after {timeout}s", TchStatusCode.TIMEOUT)
    except FileNotFoundError:
        _log.error("[PUT] scp binary not found")
        return _fail("scp binary not found")

    if result.returncode == 0:
        _log.debug("[PUT] OK — uploaded to %s:%s", target.identity, remote_path)
        return _ok(f"Uploaded {local} → {remote_path}", data={"remote_path": remote_path})

    msg = (result.stderr or b"").decode(errors="replace").strip()[:200]
    _log.warning("[PUT] failed (exit=%d): %s", result.returncode, msg)
    return _fail(msg or f"scp exited with code {result.returncode}", TchStatusCode.REMOTE_ERROR)


def get_network_interfaces(target_id: Optional[str] = None) -> dict:
    """Enumerate all network interfaces on the local or a remote host.

    Runs ``ip -j addr show`` (locally or via SSH) and returns a structured list
    with interface name, MAC address, operational state, and assigned IP
    addresses.

    :param target_id: Remote host identity as ``"user@host"``, or ``None``
        for localhost.
    :type target_id: str or None
    :return: Result dict with ``status_code``, ``output``, ``error``, and
        ``data``.  On success ``data`` is a list of interface dicts each
        containing ``name``, ``mac``, ``state``, and ``ip``.
    :rtype: dict
    """
    cmd = ["ip", "-j", "addr", "show"]
    result = run(cmd, target_id=target_id)

    if result["status_code"] != TchStatusCode.SUCCESS:
        return result

    try:
        raw = json.loads(result["output"])
    except (ValueError, TypeError) as exc:
        _log.error("[NET] failed to parse ip output: %s", exc)
        return _fail(f"Failed to parse 'ip -j addr show' output: {exc}")

    interfaces = [
        {
            "name": iface.get("ifname", ""),
            "mac": iface.get("address", ""),
            "state": iface.get("operstate", "UNKNOWN"),
            "ip": [
                addr["local"]
                for addr in iface.get("addr_info", [])
                if "local" in addr
            ],
        }
        for iface in raw
    ]

    _log.debug("[NET] found %d interfaces", len(interfaces))
    return _ok(result["output"], data=interfaces)
