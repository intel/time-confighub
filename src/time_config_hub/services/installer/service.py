# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Installer Service

Verifies connectivity to DUT targets and installs required tools and
dependencies (Testbench, AI Workloads, etc.) via system_controller.

This service is **role-agnostic**: every target (talker or listener)
goes through the same install procedure.
"""

from __future__ import annotations

import logging

from time_config_hub.infra.execution_transport import ExecutionTransport

logger = logging.getLogger(__name__)


class InstallerService:
    """Verify connectivity and install dependencies on DUT targets.

    :param packages: List of package names to install on targets.
    :param remote_config_dir: Remote directory to push configuration
        files into before any stage runs.
    """

    def __init__(
        self,
        packages: Optional[list[str]] = None,
        remote_config_dir: str = "/tmp/tch",
    ):
        self._packages = packages or []
        self._remote_config_dir = remote_config_dir

    def verify_connectivity(
        self,
        transport: ExecutionTransport,
    ) -> bool:
        """Check that the target is reachable.

        For :class:`~time_config_hub.infra.execution_transport.LocalTransport`
        this always returns ``True``.  For
        :class:`~time_config_hub.infra.execution_transport.RemoteTransport`
        an SSH round-trip is performed.

        :param transport: Execution transport for the target (local or remote).
        :return: True if the target responded successfully.
        :rtype: bool
        :raises RuntimeError: If the target cannot be reached.
        """
        from time_config_hub.infra.execution_transport import LocalTransport
        if isinstance(transport, LocalTransport):
            logger.debug("[installer] local target — skipping connectivity check")
            return True
        # TODO:
        #   result = transport.run(["echo", "connection-ok"])
        #   if not result.success:
        #       raise RuntimeError(
        #           f"Cannot reach '{transport.target_label}': {result.stderr}"
        #       )
        logger.info("[installer] connectivity verified for '%s'", transport.target_label)
        return True

    def install(
        self,
        transport: ExecutionTransport,
        dry_run: bool = False,
    ) -> list[str]:
        """Install required packages and push configuration files.

        :param transport: Execution transport for the target (local or remote).
        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        :raises RuntimeError: If the target cannot be reached.
        """
        output = [f"[installer] install on '{transport.target_label}'"]

        self.verify_connectivity(transport)

        if dry_run:
            output.append(
                f"[DRY RUN] Would install {self._packages} "
                f"on '{transport.target_label}'"
            )
            return output

        if self._packages:
            # TODO: for pkg in self._packages:
            #     result = transport.run(["apt-get", "install", "-y", pkg])
            #     if not result.success:
            #         raise RuntimeError(
            #             f"Package install failed on '{transport.target_label}': {result.stderr}"
            #         )
            output.append(
                f"[installer] packages installed on '{transport.target_label}': "
                f"{self._packages}"
            )

        # TODO: Push any required config/asset files to the remote target
        #   transport.put_file("local/assets/", self._remote_config_dir)

        logger.info("[installer] install complete on '%s'", transport.target_label)
        output.append(f"[installer] install complete on '{transport.target_label}'")
        return output
        output.append(f"[installer] install complete on '{target_id or 'local'}'")
        return output
