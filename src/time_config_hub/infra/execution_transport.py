# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Execution Transport

Abstracts the command execution transport layer so that orchestration
services are independent of whether a target is local (localhost) or
remote (SSH via system_controller).

Two concrete implementations are provided:

- :class:`LocalTransport` — runs commands in a subprocess on the local host.
- :class:`RemoteTransport` — delegates command execution and file transfer
  to ``system_controller`` over SSH.

Use :func:`make_transport` to create the appropriate transport for a given
:class:`~time_config_hub.orchestrator.models.Target` without coupling
service code to topology decisions.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from time_config_hub.orchestrator.models import Target

logger = logging.getLogger(__name__)

__all__ = [
    "ExecutionResult",
    "ExecutionTransport",
    "LocalTransport",
    "RemoteTransport",
    "make_transport",
]

_DEFAULT_TIMEOUT = 60  # seconds


# ======================================================================
# Result type
# ======================================================================

@dataclass
class ExecutionResult:
    """Result from a transport command execution.

    :param returncode: Process exit code (0 = success).
    :param stdout: Captured standard output.
    :param stderr: Captured standard error.
    """

    returncode: int
    stdout: str = ""
    stderr: str = ""

    def __post_init__(self) -> None:
        self._logs: list[str] = []

    @property
    def success(self) -> bool:
        """True if *returncode* is 0."""
        return self.returncode == 0

    def as_log_lines(self) -> list[str]:
        """Return stdout lines suitable for appending to stage output."""
        lines = list(self._logs)
        if self.stdout:
            lines.extend(self.stdout.splitlines())
        if self.stderr and not self.success:
            lines.extend(f"[stderr] {l}" for l in self.stderr.splitlines())
        return lines


# ======================================================================
# Protocol
# ======================================================================

@runtime_checkable
class ExecutionTransport(Protocol):
    """Protocol for executing commands and transferring files on a target.

    Implementations must be safe to call from multiple threads (one
    per-target worker thread in the orchestrator).
    """

    def run(
        self,
        cmd: list[str],
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """Run *cmd* on the target and return the result.

        :param cmd: Argument list (e.g. ``["ptp4l", "-i", "eth0"]``).
        :param timeout: Maximum seconds to wait.  ``None`` uses the
            transport's default.
        :return: Execution result.
        :rtype: ExecutionResult
        """
        ...

    def put_file(self, local_path: str, remote_path: str) -> None:
        """Copy *local_path* from the controller host to *remote_path* on the target.

        For :class:`LocalTransport` this is a no-op if both paths are the same,
        or a plain file copy otherwise.

        :param local_path: Absolute path on the controller host.
        :param remote_path: Destination path on the target.
        """
        ...

    def get_file(self, remote_path: str, local_path: str) -> None:
        """Copy *remote_path* from the target to *local_path* on the controller host.

        :param remote_path: Source path on the target.
        :param local_path: Destination path on the controller host.
        """
        ...

    @property
    def target_label(self) -> str:
        """Human-readable label for log messages (e.g. ``'local'`` or ``'user@host'``)."""
        ...


# ======================================================================
# Local transport
# ======================================================================

class LocalTransport:
    """Execute commands on the local host using :mod:`subprocess`.

    :param default_timeout: Default command timeout in seconds.
    """

    def __init__(self, default_timeout: int = _DEFAULT_TIMEOUT):
        self._default_timeout = default_timeout

    @property
    def target_label(self) -> str:
        return "local"

    def run(
        self,
        cmd: list[str],
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """Run *cmd* as a subprocess on the local host.

        :param cmd: Argument list.
        :param timeout: Override the default timeout (seconds).
        :return: Execution result.
        :rtype: ExecutionResult
        :raises FileNotFoundError: If the executable is not found.
        """
        effective_timeout = timeout if timeout is not None else self._default_timeout
        logger.debug("[local] run: %s", cmd)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=effective_timeout,
            )
            result = ExecutionResult(
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
            if not result.success:
                logger.warning("[local] cmd=%s exited %d: %s", cmd, proc.returncode, proc.stderr.strip())
            return result
        except subprocess.TimeoutExpired:
            logger.error("[local] cmd=%s timed out after %ds", cmd, effective_timeout)
            return ExecutionResult(
                returncode=124,
                stderr=f"Command timed out after {effective_timeout}s",
            )

    def put_file(self, local_path: str, remote_path: str) -> None:
        """Copy a file on the local filesystem.

        :param local_path: Source path.
        :param remote_path: Destination path (on the same machine).
        """
        import shutil
        if local_path != remote_path:
            logger.debug("[local] put_file: %s → %s", local_path, remote_path)
            shutil.copy2(local_path, remote_path)

    def get_file(self, remote_path: str, local_path: str) -> None:
        """Copy a file on the local filesystem.

        :param remote_path: Source path (on the same machine).
        :param local_path: Destination path.
        """
        import shutil
        if remote_path != local_path:
            logger.debug("[local] get_file: %s → %s", remote_path, local_path)
            shutil.copy2(remote_path, local_path)


# ======================================================================
# Remote transport (system_controller)
# ======================================================================

class RemoteTransport:
    """Execute commands on a remote target via ``system_controller`` (SSH).

    Holds the full SSH profile from :class:`~time_config_hub.orchestrator.models.Target`
    so that each DUT (talker, listener-1, listener-N) can carry its own
    credentials, port, and key-path independently.

    :param target: The DUT target whose SSH profile this transport represents.
    :param default_timeout: Default command timeout in seconds.
    """

    def __init__(self, target: "Target", default_timeout: int = _DEFAULT_TIMEOUT):
        self._target = target
        self._default_timeout = default_timeout

    @property
    def target_label(self) -> str:
        """Human-readable label, e.g. ``'user@192.168.1.10:2222'``."""
        label = self._target.sc_target_id or self._target.id
        if self._target.ssh_port != 22:
            label = f"{label}:{self._target.ssh_port}"
        return label

    def run(
        self,
        cmd: list[str],
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """Run *cmd* on the remote target via SSH.

        :param cmd: Argument list.
        :param timeout: Override the default timeout (seconds).
        :return: Execution result.
        :rtype: ExecutionResult
        """
        effective_timeout = timeout if timeout is not None else self._default_timeout
        logger.debug("[remote:%s] run: %s", self.target_label, cmd)
        # TODO: replace stub with real system_controller call:
        #   import system_controller as sc
        #   result = sc.run(
        #       cmd,
        #       target_id=self._target.sc_target_id,
        #       timeout=effective_timeout,
        #       ssh_port=self._target.ssh_port,
        #       ssh_key_path=self._target.ssh_key_path,
        #   )
        #   return ExecutionResult(
        #       returncode=result["returncode"],
        #       stdout=result.get("stdout", ""),
        #       stderr=result.get("stderr", ""),
        #   )
        logger.info("[remote:%s] would run: %s (timeout=%ds)", self.target_label, cmd, effective_timeout)
        return ExecutionResult(returncode=0, stdout="", stderr="")

    def put_file(self, local_path: str, remote_path: str) -> None:
        """Push *local_path* to *remote_path* on the remote target via SCP.

        :param local_path: Source path on the controller host.
        :param remote_path: Destination path on the remote target.
        """
        logger.debug("[remote:%s] put_file: %s → %s", self.target_label, local_path, remote_path)
        # TODO:
        #   sc.put_file(
        #       local_path, remote_path,
        #       target_id=self._target.sc_target_id,
        #       ssh_port=self._target.ssh_port,
        #       ssh_key_path=self._target.ssh_key_path,
        #   )
        logger.info("[remote:%s] would push %s → %s", self.target_label, local_path, remote_path)

    def get_file(self, remote_path: str, local_path: str) -> None:
        """Fetch *remote_path* from the remote target to *local_path* via SCP.

        :param remote_path: Source path on the remote target.
        :param local_path: Destination path on the controller host.
        """
        logger.debug("[remote:%s] get_file: %s → %s", self.target_label, remote_path, local_path)
        # TODO:
        #   sc.get_file(
        #       remote_path, local_path,
        #       target_id=self._target.sc_target_id,
        #       ssh_port=self._target.ssh_port,
        #       ssh_key_path=self._target.ssh_key_path,
        #   )
        logger.info("[remote:%s] would fetch %s → %s", self.target_label, remote_path, local_path)


# ======================================================================
# Factory
# ======================================================================

def make_transport(target: "Target") -> ExecutionTransport:
    """Return the appropriate transport for *target*.

    The transport type is determined by whether the target has SSH credentials:

    - No ``ssh_user`` (local target) → :class:`LocalTransport`
    - Has ``ssh_user`` (remote DUT) → :class:`RemoteTransport` carrying the
      full SSH profile (``ip_address``, ``ssh_port``, ``ssh_key_path``,
      ``ssh_password``)

    Each call returns a **new** instance, so every target in a MULTI_DUT
    topology gets an independent transport with its own SSH profile.

    :param target: The DUT target to create a transport for.
    :return: A :class:`LocalTransport` or :class:`RemoteTransport`.
    :rtype: ExecutionTransport
    """
    if target.ssh_user is None:
        return LocalTransport()
    return RemoteTransport(target=target)
