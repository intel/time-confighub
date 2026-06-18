# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
ServiceFactory — per-target TimeHubService construction.

The orchestrator is responsible for topology-aware service instantiation.
``ServiceFactory`` encapsulates the logic that maps a :class:`~.models.Target`
(including its per-DUT PTP config fields) onto a fully-configured
:class:`~.time_hub_service.TimeHubService`.

Each call to :meth:`ServiceFactory.build` returns a **new, independent**
``TimeHubService`` instance.  Because every worker thread receives its own
instance, there is no shared mutable state between threads — thread-safety
is achieved by construction, not by locking.

Extension point
~~~~~~~~~~~~~~~
As other services acquire per-target configuration (e.g. a custom testbench
binary path, a workload-specific arg set, or a per-DUT TSN interface name),
add the corresponding fields to :class:`~.models.Target` and resolve them
here, keeping the topology concern firmly in the orchestrator layer and out
of the service classes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .models import Target

from time_config_hub.services.ai_workload.service import AIWorkloadService
from time_config_hub.services.installer.service import InstallerService
from time_config_hub.services.ptp.service import PtpService
from time_config_hub.services.testbench.service import TestbenchService
from time_config_hub.services.tcc.service import TCCService
from time_config_hub.services.tsn.service import TSNService

logger = logging.getLogger("orchestrator.service_factory")

__all__ = ["ServiceFactory"]


class ServiceFactory:
    """Build a :class:`~.time_hub_service.TimeHubService` for a given target.

    :param app_config: Application configuration dictionary (deployment-wide
        defaults).  Per-target overrides are taken from the :class:`~.models.Target`
        fields and take precedence over these defaults.
    """

    def __init__(
        self,
        app_config: Dict[str, Any],
    ):
        self._app_config = app_config

    def build(self, target: Target) -> Any:
        """Return a :class:`~.time_hub_service.TimeHubService` for *target*.

        Constructs every service from the appropriate section of *app_config*,
        with ``target.*`` fields taking precedence for per-DUT overrides (e.g.
        ``target.ptp_interface``).  The resolved instances are passed explicitly
        into :class:`~.time_hub_service.TimeHubService` so the facade itself
        has no knowledge of config resolution or topology.

        Config section → service mapping:

        - ``app_config["PTP"]``         → :class:`~...ptp.PtpService`
        - ``app_config["Testbench"]``   → :class:`~...testbench.TestbenchService`
        - ``app_config["AIWorkload"]``  → :class:`~...ai_workload.AIWorkloadService`
        - ``app_config["Installer"]``   → :class:`~...installer.InstallerService`
        - ``app_config`` (whole dict)   → :class:`~...tsn.TSNService`, :class:`~...tcc.TCCService`

        :param target: The DUT target to build services for.
        :return: A fully configured :class:`~.time_hub_service.TimeHubService`.
        """
        from .time_hub_service import TimeHubService

        cfg = self._app_config

        # -- PTP: per-target fields take precedence over app_config["PTP"] --
        ptp_cfg = cfg.get("PTP", {})
        ptp_service = PtpService(
            ptp4l_gm_config=(
                target.ptp_gm_config
                or ptp_cfg.get("Ptp4lGmConfig", "/etc/ptp4l-gm.conf")
            ),
            ptp4l_slave_config=(
                target.ptp_slave_config
                or ptp_cfg.get("Ptp4lSlaveConfig", "/etc/ptp4l-slave.conf")
            ),
            ptp4l_interface=(
                target.ptp_interface
                or ptp_cfg.get("Interface", "eth0")
            ),
            phc2sys_interface=(
                target.ptp_interface
                or ptp_cfg.get("Interface", "eth0")
            ),
            ptp_sync_timeout=int(ptp_cfg.get("SyncTimeout", 60)),
            ptp_sync_poll_interval=float(ptp_cfg.get("PollInterval", 2.0)),
            ptp_offset_threshold_ns=int(ptp_cfg.get("OffsetThresholdNs", 100)),
        )

        # -- Testbench: from app_config["Testbench"] --
        tb_cfg = cfg.get("Testbench", {})
        testbench_service = TestbenchService(
            transmitter_bin=tb_cfg.get("TransmitterBin", "testbench-tx"),
            receiver_bin=tb_cfg.get("ReceiverBin", "testbench-rx"),
            log_remote_path=tb_cfg.get("LogRemotePath", "/tmp/testbench.log"),
            log_local_dir=tb_cfg.get("LogLocalDir", "results/"),
        )

        # -- AI Workload: from app_config["AIWorkload"] --
        ai_cfg = cfg.get("AIWorkload", {})
        ai_workload_service = AIWorkloadService(
            workload_bin=ai_cfg.get("WorkloadBin", "ai-workload"),
            workload_args=ai_cfg.get("WorkloadArgs"),
            log_remote_path=ai_cfg.get("LogRemotePath", "/tmp/ai_workload.log"),
            log_local_dir=ai_cfg.get("LogLocalDir", "results/"),
        )

        # -- Installer: from app_config["Installer"] --
        inst_cfg = cfg.get("Installer", {})
        installer_service = InstallerService(
            packages=inst_cfg.get("Packages"),
            remote_config_dir=inst_cfg.get("RemoteConfigDir", "/tmp/tch"),
        )

        # -- TSN / TCC: take the full app_config (they parse their own sections) --
        tsn_service = TSNService(cfg)
        tcc_service = TCCService(cfg)

        logger.debug(
            "ServiceFactory: built TimeHubService for target '%s' (role=%s, ptp_iface=%s)",
            target.id,
            target.role,
            target.ptp_interface or ptp_cfg.get("Interface", "eth0"),
        )
        return TimeHubService(
            app_config=cfg,
            tsn_service=tsn_service,
            tcc_service=tcc_service,
            ptp_service=ptp_service,
            testbench_service=testbench_service,
            ai_workload_service=ai_workload_service,
            installer_service=installer_service,
        )
