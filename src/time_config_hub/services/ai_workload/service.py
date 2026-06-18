# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
AI Workload Service

Manages the AI workload application lifecycle on local and remote DUT
targets (listeners).

This service is **role-agnostic**: it exposes start/stop operations and
makes no assumptions about talker/listener topology.  The orchestration
layer decides which targets invoke these methods.
"""

from __future__ import annotations

import logging
from typing import Optional

from time_config_hub.infra.execution_transport import ExecutionTransport

logger = logging.getLogger(__name__)


class AIWorkloadService:
    """Manage AI workload application lifecycle on DUT targets.

    :param workload_bin: Path or command name of the AI workload binary.
    :param workload_args: Additional arguments passed to the workload binary.
    :param log_remote_path: Remote path where the workload writes its log.
    :param log_local_dir: Local directory to store collected log files.
    """

    def __init__(
        self,
        workload_bin: str = "ai-workload",
        workload_args: Optional[list[str]] = None,
        log_remote_path: str = "/tmp/ai_workload.log",
        log_local_dir: str = "results/",
    ):
        self._workload_bin = workload_bin
        self._workload_args = workload_args or []
        self._log_remote_path = log_remote_path
        self._log_local_dir = log_local_dir

    def start(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Start the AI workload on the target.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[ai_workload] start on '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would start '{self._workload_bin}' "
                f"on '{transport.target_label}'"
            )
            return output
        # TODO:
        #   result = transport.run([self._workload_bin] + self._workload_args)
        #   if not result.success:
        #       raise RuntimeError(
        #           f"AI workload failed on '{transport.target_label}': {result.stderr}"
        #       )
        logger.info("[ai_workload] started on '%s'", transport.target_label)
        output.append(f"[ai_workload] started on '{transport.target_label}'")
        return output

    def stop(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Stop the AI workload on the target.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[ai_workload] stop on '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would stop '{self._workload_bin}' "
                f"on '{transport.target_label}'"
            )
            return output
        # TODO: transport.run(["pkill", "-f", self._workload_bin])
        logger.info("[ai_workload] stopped on '%s'", transport.target_label)
        output.append(f"[ai_workload] stopped on '{transport.target_label}'")
        return output

    def collect_logs(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Retrieve AI workload log from the target and store locally.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[ai_workload] collect_logs from '{transport.target_label}'"]
        if dry_run:
            output.append(
                f"[DRY RUN] Would retrieve '{self._log_remote_path}' "
                f"from '{transport.target_label}' → '{self._log_local_dir}'"
            )
            return output
        # TODO:
        #   local_name = transport.target_label.replace("@", "_") + "_ai.log"
        #   transport.get_file(
        #       self._log_remote_path,
        #       f"{self._log_local_dir}/{local_name}",
        #   )
        logger.info("[ai_workload] logs collected from '%s'", transport.target_label)
        output.append(f"[ai_workload] logs collected from '{transport.target_label}'")
        return output
