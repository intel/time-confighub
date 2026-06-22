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

from time_config_hub.services.tcc.service import TCCService
from time_config_hub.services.tsn.service import TSNService

logger = logging.getLogger("orchestrator.service_factory")

__all__ = ["ServiceFactory"]


class ServiceFactory:
    """Build a :class:`~.time_hub_service.TimeHubService` for a given target.

    :param tch_config: Application configuration dictionary (deployment-wide
        defaults).  Per-target overrides are taken from the :class:`~.models.Target`
        fields and take precedence over these defaults.
    """

    def __init__(
        self,
        tch_config: Dict[str, Any],
    ):
        self._tch_config = tch_config

    def build(self, target: Target) -> Any:
        """Return a :class:`~.time_hub_service.TimeHubService` for *target*.

        :param target: The DUT target to build services for.
        :return: A fully configured :class:`~.time_hub_service.TimeHubService`.
        """
        from .time_hub_service import TimeHubService

        cfg = self._tch_config

        # -- TSN / TCC: take the full tch_config (they parse their own sections) --
        tsn_service = TSNService(cfg)
        tcc_service = TCCService(cfg)

        logger.info(
            "ServiceFactory: built TimeHubService for target '%s' (role=%s, ptp_iface=%s)",
            target.id,
            target.role,
            target.ptp_interface or cfg.get("PTP", {}).get("Interface", "eth0"),
        )
        return TimeHubService(
            tch_config=cfg,
            tsn_service=tsn_service,
            tcc_service=tcc_service,
        )
