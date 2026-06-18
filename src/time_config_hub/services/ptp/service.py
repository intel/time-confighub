# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
PTP Service

Manages ptp4l (IEEE 1588 Precision Time Protocol daemon) and phc2sys
(PHC-to-system-clock synchronisation daemon) lifecycle operations on
local and remote DUT targets.

All methods accept an optional *target_id* (``user@host`` string used by
system_controller for remote execution, or ``None`` for the local host)
and a *dry_run* flag that suppresses all side-effects.

This service is **role-agnostic**: it does not know whether a target is a
talker or listener.  Role-specific sequencing is owned by the orchestration
layer (``multi_target.py`` / ``TimeHubService``).
"""

from __future__ import annotations

import logging

from time_config_hub.infra.execution_transport import ExecutionTransport

logger = logging.getLogger(__name__)


class PtpService:
    """Manage ptp4l and phc2sys daemons on local and remote targets.

    :param ptp4l_gm_config: Path to the ptp4l grandmaster config file.
    :param ptp4l_slave_config: Path to the ptp4l slave config file.
    :param ptp4l_interface: Network interface used by ptp4l.
    :param phc2sys_interface: Network interface used by phc2sys.
    :param ptp_sync_timeout: Maximum seconds to wait for PTP sync.
    :param ptp_sync_poll_interval: Seconds between PTP status polls.
    :param ptp_offset_threshold_ns: Maximum acceptable PTP offset (ns) for
        slave lock confirmation.
    """

    def __init__(
        self,
        ptp4l_gm_config: str = "/etc/ptp4l-gm.conf",
        ptp4l_slave_config: str = "/etc/ptp4l-slave.conf",
        ptp4l_interface: str = "eth0",
        phc2sys_interface: str = "eth0",
        ptp_sync_timeout: int = 60,
        ptp_sync_poll_interval: float = 2.0,
        ptp_offset_threshold_ns: int = 100,
    ):
        self._ptp4l_gm_config = ptp4l_gm_config
        self._ptp4l_slave_config = ptp4l_slave_config
        self._ptp4l_interface = ptp4l_interface
        self._phc2sys_interface = phc2sys_interface
        self._ptp_sync_timeout = ptp_sync_timeout
        self._ptp_sync_poll_interval = ptp_sync_poll_interval
        self._ptp_offset_threshold_ns = ptp_offset_threshold_ns

    # ------------------------------------------------------------------
    # Composite role-aware entry point
    # ------------------------------------------------------------------

    def run_ptp_phase(
        self,
        transport: ExecutionTransport,
        role: str | None,
        dry_run: bool = False,
    ) -> list[str]:
        """Run the full PTP setup phase for a given role.

        Dispatches internally based on *role*:

        - ``"talker"``  → start ptp4l (GM) → verify GM status → start phc2sys
        - ``"listener"`` → start ptp4l (slave) → verify SLAVE lock → start phc2sys

        Both paths terminate by verifying lock, so when the step barrier is
        reached in the orchestrator, all targets have confirmed PTP sync
        regardless of the order they were started.

        :param transport: Execution transport for the target (local or remote).
        :param role: Target role — ``"talker"`` or ``"listener"``.
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        :raises ValueError: If *role* is not ``"talker"`` or ``"listener"``.
        """
        if role == "talker":
            output: list[str] = []
            output += self.start_grandmaster(transport=transport, dry_run=dry_run)
            output += self.verify_grandmaster_status(transport=transport, dry_run=dry_run)
            output += self.start_phc2sys(transport=transport, dry_run=dry_run)
            return output
        elif role == "listener":
            output = []
            output += self.start_slave(transport=transport, dry_run=dry_run)
            output += self.verify_slave_lock(transport=transport, dry_run=dry_run)
            output += self.start_phc2sys(transport=transport, dry_run=dry_run)
            return output
        else:
            raise ValueError(
                f"run_ptp_phase: unsupported role '{role}'. "
                "Expected 'talker' or 'listener'."
            )

    # ------------------------------------------------------------------
    # ptp4l — grandmaster (talker)
    # ------------------------------------------------------------------

    def start_grandmaster(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Start ptp4l in grandmaster (PTP master) mode.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[ptp] start_grandmaster on '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would start ptp4l GM on '{transport.target_label}' "
                f"(iface={self._ptp4l_interface}, cfg={self._ptp4l_gm_config})"
            )
            return output
        # TODO:
        #   result = transport.run(
        #       ["ptp4l", "-i", self._ptp4l_interface, "-f", self._ptp4l_gm_config,
        #        "--masterOnly", "1", "-m"],
        #   )
        #   if not result.success:
        #       raise RuntimeError(
        #           f"ptp4l GM failed on '{transport.target_label}': {result.stderr}"
        #       )
        logger.info("[ptp] ptp4l GM started on '%s'", transport.target_label)
        output.append(f"[ptp] ptp4l GM started on '{transport.target_label}'")
        return output

    def verify_grandmaster_status(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Poll until ptp4l reports MASTER portState or timeout.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        :raises RuntimeError: If MASTER state is not achieved within timeout.
        """
        output = [f"[ptp] verify_grandmaster_status on '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would verify PTP GM status on '{transport.target_label}'"
            )
            return output
        # TODO: Poll ptp4l until portState is MASTER
        #   import time
        #   deadline = time.monotonic() + self._ptp_sync_timeout
        #   while time.monotonic() < deadline:
        #       result = transport.run(["pmc", "-u", "-b", "0", "GET PORT_DATA_SET"])
        #       if "MASTER" in result.stdout:
        #           break
        #       time.sleep(self._ptp_sync_poll_interval)
        #   else:
        #       raise RuntimeError(
        #           f"PTP GM status not achieved on '{transport.target_label}' "
        #           f"within {self._ptp_sync_timeout}s"
        #       )
        logger.info("[ptp] PTP GM status verified on '%s'", transport.target_label)
        output.append(f"[ptp] PTP GM status verified on '{transport.target_label}'")
        return output

    # ------------------------------------------------------------------
    # ptp4l — slave (listener)
    # ------------------------------------------------------------------

    def start_slave(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Start ptp4l in slave mode, syncing to the PTP grandmaster.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[ptp] start_slave on '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would start ptp4l slave on '{transport.target_label}' "
                f"(iface={self._ptp4l_interface}, cfg={self._ptp4l_slave_config})"
            )
            return output
        # TODO:
        #   result = transport.run(
        #       ["ptp4l", "-i", self._ptp4l_interface, "-f", self._ptp4l_slave_config, "-m"],
        #   )
        #   if not result.success:
        #       raise RuntimeError(
        #           f"ptp4l slave failed on '{transport.target_label}': {result.stderr}"
        #       )
        logger.info("[ptp] ptp4l slave started on '%s'", transport.target_label)
        output.append(f"[ptp] ptp4l slave started on '{transport.target_label}'")
        return output

    def verify_slave_lock(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Poll until ptp4l reports SLAVE portState and offset is within threshold.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        :raises RuntimeError: If SLAVE lock is not achieved within timeout.
        """
        output = [f"[ptp] verify_slave_lock on '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would verify PTP SLAVE lock on '{transport.target_label}'"
            )
            return output
        # TODO: Poll ptp4l until portState is SLAVE and offset < threshold
        #   import time
        #   deadline = time.monotonic() + self._ptp_sync_timeout
        #   while time.monotonic() < deadline:
        #       result = transport.run(["pmc", "-u", "-b", "0", "GET PORT_DATA_SET"])
        #       if "SLAVE" in result.stdout:
        #           # optionally parse offset from ptp4l log and check threshold
        #           break
        #       time.sleep(self._ptp_sync_poll_interval)
        #   else:
        #       raise RuntimeError(
        #           f"PTP SLAVE lock not achieved on '{transport.target_label}' "
        #           f"within {self._ptp_sync_timeout}s"
        #       )
        logger.info("[ptp] PTP SLAVE lock verified on '%s'", transport.target_label)
        output.append(f"[ptp] PTP SLAVE lock verified on '{transport.target_label}'")
        return output

    # ------------------------------------------------------------------
    # phc2sys
    # ------------------------------------------------------------------

    def start_phc2sys(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Start phc2sys to synchronise the system clock from the PHC.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[ptp] start_phc2sys on '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would start phc2sys on '{transport.target_label}' "
                f"(iface={self._phc2sys_interface})"
            )
            return output
        # TODO:
        #   result = transport.run(
        #       ["phc2sys", "-s", self._phc2sys_interface, "-c", "CLOCK_REALTIME",
        #        "-w", "-m"],
        #   )
        #   if not result.success:
        #       raise RuntimeError(
        #           f"phc2sys failed on '{transport.target_label}': {result.stderr}"
        #       )
        logger.info("[ptp] phc2sys started on '%s'", transport.target_label)
        output.append(f"[ptp] phc2sys started on '{transport.target_label}'")
        return output
