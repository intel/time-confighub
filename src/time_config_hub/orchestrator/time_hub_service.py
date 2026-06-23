# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Real Time Service Facade for Time Config Hub.

This module provides a single :class:`TimeHubService` class that serves as
a unified facade over the independent TSN and TCC service implementations.

Example usage:

from time_config_hub import TimeHubService

svc = TimeHubService.from_default_config()
svc.tsn.apply("/path/to/tsn.xml", dry_run=True)
svc.tcc.status()

"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, Optional

from time_config_hub.config.config_reader import load_app_config
from time_config_hub.services.common.service_interfaces import (
    TCCServiceInterface,
    TSNServiceInterface,
)
from time_config_hub.infra.linux.service_manager import ServiceManager
from time_config_hub.services.tcc.service import TCCService
from time_config_hub.services.tsn.service import TSNService
from time_config_hub.infra.execution_transport import ExecutionTransport, make_transport
from .models import StageContext

logger = logging.getLogger(__name__)


@contextmanager
def _stage_span(
    stage_name: str, ctx: StageContext, output: list[str]
) -> Generator[None, None, None]:
    """Record start / done / failed telemetry for a single workflow stage.

    Emits a ``STAGE START`` log entry on entry.  On clean exit, appends a
    ``STAGE DONE`` line (with elapsed wall-clock time) to *output* and logs
    it at INFO level.  On exception, logs ``STAGE FAILED`` and re-raises so
    the caller sees the original error unchanged.

    :param str stage_name: Short stage identifier (e.g. ``"install"``).
    :param StageContext ctx: Current stage execution context.
    :param list[str] output: Mutable list that receives the telemetry line on
        success.
    """
    # 1. Setup phase label and log start
    target = ctx.target
    role_tag = f"/{target.role}" if target.role else ""
    label = f"{stage_name}[{target.id}{role_tag}]"
    logger.info("STAGE START  %s  dry_run=%s", label, ctx.dry_run)
    t0 = time.monotonic()
    try:
        # 2. Hand over control to the 'with' block
        yield
        # On success, record elapsed time and append a "STAGE DONE" line to output
        elapsed = time.monotonic() - t0
        msg = f"STAGE DONE   {label}  elapsed={elapsed:.3f}s"
        logger.info(msg)
        output.append(msg)
    except Exception:
        elapsed = time.monotonic() - t0
        logger.exception("STAGE FAILED %s  elapsed=%.3f s", label, elapsed)
        raise


class TimeHubService:
    """Unified service facade over TSN, TCC for a **single target**.

    ``TimeHubService`` is a pure service facade — it has no knowledge of
    topology or multi-DUT orchestration.  The orchestrator layer is
    responsible for constructing one instance per target via
    :class:`~.service_factory.ServiceFactory`.

    :param app_config: Application configuration dictionary.
    :param tsn_service: Optional TSN service override (tests / custom impl).
    :param tcc_service: Optional TCC service override.
    """

    def __init__(
        self,
        tch_config: Dict[str, Any],
        tsn_service: Optional[TSNServiceInterface] = None,
        tcc_service: Optional[TCCServiceInterface] = None,
    ):
        logger.debug("Initializing Time Config Hub Service...")
        self.tch_config = tch_config

        # config_dir suppose to store applied configuration backups
        self.config_dir = Path(tch_config.get("General", {}).get("ConfigDirectory", ""))
        self.verbose = tch_config.get("General", {}).get("Verbosity")

        # Initialize the ServiceManager for system-level (TCH daemon) service control (start/stop/restart/status)
        self.service_manager = ServiceManager()

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self._tsn_service: TSNServiceInterface = tsn_service or TSNService(tch_config)
        self._tcc_service: TCCServiceInterface = tcc_service or TCCService(tch_config)

        logger.debug("TimeHubService initialised with config_dir: %s", self.config_dir)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_default_config(cls) -> "TimeHubService":
        """Create a facade using configuration loaded from default paths.

        :return: A new :class:`TimeHubService` instance.
        :rtype: TimeHubService
        """
        return cls(tch_config=load_app_config())

    # ------------------------------------------------------------------
    # Typed property access (library API)
    # ------------------------------------------------------------------

    @property
    def tsn(self) -> TSNServiceInterface:
        """TSN service interface.

        :rtype: TSNServiceInterface
        """
        return self._tsn_service

    @property
    def tcc(self) -> TCCServiceInterface:
        """TCC service interface.

        :rtype: TCCServiceInterface
        """
        return self._tcc_service

    # ------------------------------------------------------------------
    # WorkflowStagePlugin implementation
    # ------------------------------------------------------------------
    # TODO: Consider extracting the stage_* methods below into a dedicated module
    #       (e.g. orchestrator/stage_handlers.py). They are not part of the TSN/TCC
    #       service interface but are the default concrete WorkflowStagePlugin impl.
    #
    # Thread-safety: this instance is NOT shared across threads.  The orchestrator
    # calls TimeHubService.for_target(target, app_config) to create one instance
    # per target before building each StageContext.  Because each worker thread
    # owns its own instance, all service calls are inherently thread-safe.

    def _make_transport(self, ctx: StageContext) -> ExecutionTransport:
        """Return the appropriate execution transport for *ctx.target*.

        Each call returns a new independent transport instance bound to
        the full SSH profile of ``ctx.target`` (credentials, port, key).

        :param StageContext ctx: Current stage execution context.
        :return: :class:`~time_config_hub.infra.execution_transport.LocalTransport`
            when the target is local, otherwise a
            :class:`~time_config_hub.infra.execution_transport.RemoteTransport`.
        :rtype: ExecutionTransport
        """
        return make_transport(ctx.target)

    def stage_install(self, ctx: StageContext) -> list[str]:
        """Install tools and dependencies on a target.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        """
        logger.warning("[STUB] stage_install not yet implemented for target '%s'", ctx.target.id)
        return [f"[{ctx.target.id}] stage_install: stub — skipped"]

        """
        output: list[str] = []
        with _stage_span("install", ctx, output):
            output += self._installer_service.install(
                transport=self._make_transport(ctx),
                dry_run=ctx.dry_run,
            )
        return output
        """

    def stage_apply_config(self, ctx: StageContext) -> list[str]:
        """Apply TCC and TSN configurations on a target.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        """
        target = ctx.target
        dry_run = ctx.dry_run
        output: list[str] = [f"[{target.id}] Applying configuration ({target.ip_address})"]
        with _stage_span("apply_config", ctx, output):
            if dry_run:
                output.append(f"[DRY RUN] Would apply TCC/TSN config on '{target.id}'")
            elif target.sc_target_id is None:
                # Local target — apply config directly via TSN/TCC services
                logger.info("<<<<Applying config for local target '%s'", target.id)
                if ctx.tcc_config_path:
                    #self.apply_tcc_config(ctx.tcc_config_path, dry_run=dry_run)
                    output.append(f"TCC config applied from '{ctx.tcc_config_path}'")
                if ctx.tsn_config_path:
                    #self.apply_config(ctx.tsn_config_path, dry_run=dry_run)
                    output.append(f"TSN config applied from '{ctx.tsn_config_path}'")
            else:
                logger.info("<<<<Applying config for remote target '%s'", target.id)
                transport = self._make_transport(ctx)
                if ctx.tcc_config_path:
                    transport.put_file(ctx.tcc_config_path, "/tmp/tcc.xml")
                    result = transport.run(["tch", "tcc", "apply", "/tmp/tcc.xml"])
                    output.extend(result.as_log_lines())
                    if not result.success:
                        raise RuntimeError(
                            f"[{target.id}] tcc apply failed (exit {result.returncode}): {result.stderr.strip()}"
                        )
                    output.append(f"[{target.id}] TCC config applied from '/tmp/tcc.xml'")
                if ctx.tsn_config_path:
                    transport.put_file(ctx.tsn_config_path, "/tmp/tsn.xml")
                    result = transport.run(["tch", "tsn", "apply", "/tmp/tsn.xml"])
                    output.extend(result.as_log_lines())
                    if not result.success:
                        raise RuntimeError(
                            f"[{target.id}] tsn apply failed (exit {result.returncode}): {result.stderr.strip()}"
                        )
                    output.append(f"[{target.id}] TSN config applied from '/tmp/tsn.xml'")
            output.append(f"[{target.id}] Configuration applied")
        return output

    # ------------------------------------------------------------------
    # Multi-target run stage — stubs (not yet implemented)
    # ------------------------------------------------------------------

    def stage_verify_hw(self, ctx: StageContext) -> list[str]:
        """Stub: verify hardware readiness before PTP startup.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        """
        logger.warning("[STUB] stage_verify_hw not yet implemented for target '%s'", ctx.target.id)
        return [f"[{ctx.target.id}] stage_verify_hw: stub — skipped"]

    def stage_start_ptp(self, ctx: StageContext) -> list[str]:
        """Stub: start the PTP daemon for this target's role.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        """
        logger.warning("[STUB] stage_start_ptp not yet implemented for target '%s'", ctx.target.id)
        return [f"[{ctx.target.id}] stage_start_ptp: stub — skipped"]

    def stage_validate_timesync(self, ctx: StageContext) -> list[str]:
        """Stub: poll for PTP lock and validate sub-microsecond offset.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        """
        logger.warning("[STUB] stage_validate_timesync not yet implemented for target '%s'", ctx.target.id)
        return [f"[{ctx.target.id}] stage_validate_timesync: stub — skipped"]

    def stage_run_workloads(self, ctx: StageContext) -> list[str]:
        """Stub: start workloads for this target's role.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        """
        logger.warning("[STUB] stage_run_workloads not yet implemented for target '%s'", ctx.target.id)
        return [f"[{ctx.target.id}] stage_run_workloads: stub — skipped"]

    def stage_run(self, ctx: StageContext) -> list[str]:
        """Stub: execute the full workflow on a single local target.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        """
        logger.warning("[STUB] stage_run not yet implemented for target '%s'", ctx.target.id)
        return [f"[{ctx.target.id}] stage_run: stub — skipped"]

    def stage_results(self, ctx: StageContext) -> list[str]:
        """Stub: collect results, stop workloads, and gather logs.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        """
        logger.warning("[STUB] stage_results not yet implemented for target '%s'", ctx.target.id)
        return [f"[{ctx.target.id}] stage_results: stub — skipped"]
