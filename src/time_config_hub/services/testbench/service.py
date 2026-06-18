# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Testbench Service

Manages the testbench application lifecycle (transmitter and receiver)
on local and remote DUT targets, and collects test output logs.

This service is **role-agnostic**: it exposes symmetric transmitter/receiver
operations.  The orchestration layer decides which role calls which method.
"""

from __future__ import annotations

import logging

from time_config_hub.infra.execution_transport import ExecutionTransport

logger = logging.getLogger(__name__)


class TestbenchService:
    """Manage testbench transmitter, receiver, and log collection.

    :param transmitter_bin: Path or command name of the testbench transmitter.
    :param receiver_bin: Path or command name of the testbench receiver.
    :param log_remote_path: Remote path where the testbench writes its log.
    :param log_local_dir: Local directory to store collected log files.
    """

    def __init__(
        self,
        transmitter_bin: str = "testbench-tx",
        receiver_bin: str = "testbench-rx",
        log_remote_path: str = "/tmp/testbench.log",
        log_local_dir: str = "results/",
    ):
        self._transmitter_bin = transmitter_bin
        self._receiver_bin = receiver_bin
        self._log_remote_path = log_remote_path
        self._log_local_dir = log_local_dir

    # ------------------------------------------------------------------
    # Transmitter (talker side)
    # ------------------------------------------------------------------

    def start_transmitter(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Start the testbench in transmit mode.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[testbench] start_transmitter on '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would start '{self._transmitter_bin}' "
                f"on '{transport.target_label}'"
            )
            return output
        # TODO:
        #   result = transport.run([self._transmitter_bin])
        #   if not result.success:
        #       raise RuntimeError(
        #           f"testbench TX failed on '{transport.target_label}': {result.stderr}"
        #       )
        logger.info("[testbench] transmitter started on '%s'", transport.target_label)
        output.append(f"[testbench] transmitter started on '{transport.target_label}'")
        return output

    def stop_transmitter(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Stop the testbench transmitter process.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[testbench] stop_transmitter on '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would stop '{self._transmitter_bin}' "
                f"on '{transport.target_label}'"
            )
            return output
        # TODO: transport.run(["pkill", "-f", self._transmitter_bin])
        logger.info("[testbench] transmitter stopped on '%s'", transport.target_label)
        output.append(f"[testbench] transmitter stopped on '{transport.target_label}'")
        return output

    # ------------------------------------------------------------------
    # Receiver (listener side)
    # ------------------------------------------------------------------

    def start_receiver(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Start the testbench in receive mode.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[testbench] start_receiver on '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would start '{self._receiver_bin}' "
                f"on '{transport.target_label}'"
            )
            return output
        # TODO: transport.run([self._receiver_bin])
        logger.info("[testbench] receiver started on '%s'", transport.target_label)
        output.append(f"[testbench] receiver started on '{transport.target_label}'")
        return output

    def stop_receiver(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Stop the testbench receiver process.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[testbench] stop_receiver on '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would stop '{self._receiver_bin}' "
                f"on '{transport.target_label}'"
            )
            return output
        # TODO: transport.run(["pkill", "-f", self._receiver_bin])
        logger.info("[testbench] receiver stopped on '%s'", transport.target_label)
        output.append(f"[testbench] receiver stopped on '{transport.target_label}'")
        return output

    # ------------------------------------------------------------------
    # Log collection
    # ------------------------------------------------------------------

    def collect_logs(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Retrieve testbench log from the target and store locally.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[testbench] collect_logs from '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would retrieve '{self._log_remote_path}' "
                f"from '{transport.target_label}' → '{self._log_local_dir}'"
            )
            return output
        # TODO:
        #   local_name = transport.target_label.replace("@", "_") + ".log"
        #   transport.get_file(
        #       self._log_remote_path,
        #       f"{self._log_local_dir}/{local_name}",
        #   )
        logger.info("[testbench] logs collected from '%s'", transport.target_label)
        output.append(f"[testbench] logs collected from '{transport.target_label}'")
        return output
