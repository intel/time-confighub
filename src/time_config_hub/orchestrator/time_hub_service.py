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
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, Optional

from time_config_hub.config.config_reader import load_app_config
from time_config_hub.services.common.service_interfaces import (
    AIWorkloadServiceInterface,
    InstallerServiceInterface,
    PtpServiceInterface,
    TCCServiceInterface,
    TSNServiceInterface,
    TestbenchServiceInterface,
)
from time_config_hub.infra.linux.service_manager import ServiceManager
from time_config_hub.services.ai_workload.service import AIWorkloadService
from time_config_hub.services.installer.service import InstallerService
from time_config_hub.services.ptp.service import PtpService
from time_config_hub.services.tcc.service import TCCService
from time_config_hub.services.testbench.service import TestbenchService
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
    """Unified service facade over TSN, TCC, PTP, testbench, AI workload and
    installer services for a **single target**.

    ``TimeHubService`` is a pure service facade — it has no knowledge of
    topology or multi-DUT orchestration.  The orchestrator layer is
    responsible for constructing one instance per target via
    :class:`~.service_factory.ServiceFactory`.

    :param app_config: Application configuration dictionary.
    :param tsn_service: Optional TSN service override (tests / custom impl).
    :param tcc_service: Optional TCC service override.
    :param ptp_service: Optional PTP service override.
    :param testbench_service: Optional testbench service override.
    :param ai_workload_service: Optional AI workload service override.
    :param installer_service: Optional installer service override.
    """

    def __init__(
        self,
        app_config: Dict[str, Any],
        tsn_service: Optional[TSNServiceInterface] = None,
        tcc_service: Optional[TCCServiceInterface] = None,
        ptp_service: Optional[PtpServiceInterface] = None,
        testbench_service: Optional[TestbenchServiceInterface] = None,
        ai_workload_service: Optional[AIWorkloadServiceInterface] = None,
        installer_service: Optional[InstallerServiceInterface] = None,
    ):
        logger.debug("Initializing Time Config Hub Service...")
        self.app_config = app_config

        # config_dir suppose to store applied configuration backups
        self.config_dir = Path(app_config.get("General", {}).get("ConfigDirectory", ""))
        self.verbose = app_config.get("General", {}).get("Verbosity")
        self.service_manager = ServiceManager()

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self._tsn_service: TSNServiceInterface = tsn_service or TSNService(app_config)
        self._tcc_service: TCCServiceInterface = tcc_service or TCCService(app_config)
        self._ptp_service: PtpServiceInterface = ptp_service or PtpService()
        self._testbench_service: TestbenchServiceInterface = testbench_service or TestbenchService()
        self._ai_workload_service: AIWorkloadServiceInterface = ai_workload_service or AIWorkloadService()
        self._installer_service: InstallerServiceInterface = installer_service or InstallerService()

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
        return cls(app_config=load_app_config())

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
    # TSN convenience methods (used by CLI / watch_handler)
    # ------------------------------------------------------------------

    def apply_config(self, config_file: str, dry_run: bool = False) -> None:
        """Apply TSN configuration from a file.

        :param str config_file: Path to configuration file (XML or YAML).
        :param bool dry_run: If True, show generated commands without execution.
        """
        self._tsn_service.apply(config_file, dry_run=dry_run)

    def get_status(self, interface: str) -> Dict[str, Any]:
        """Return current TSN configuration status for an interface.

        :param str interface: Network interface name.
        :return: Status dictionary.
        :rtype: dict
        """
        return self._tsn_service.status(interface=interface)

    def reset_config(self, interface: str) -> bool:
        """Reset TSN configuration to defaults for an interface.

        :param str interface: Network interface name.
        :return: True on success.
        :rtype: bool
        """
        return self._tsn_service.reset(interface=interface)

    def validate_config(self, config_file: str) -> bool:
        """Validate a TSN configuration file without applying it.

        :param str config_file: Path to configuration file.
        :return: True if the file is valid.
        :rtype: bool
        """
        return self._tsn_service.validate(config_file)

    def file_event_handler(self, event_type: str, file_path: str) -> None:
        """Handle file-watcher events for TSN flows.

        :param str event_type: Event type string (e.g. ``"modified"``).
        :param str file_path: Path to the changed file.
        """
        self._tsn_service.file_event_handler(event_type, file_path)

    # ------------------------------------------------------------------
    # TCC convenience methods (used by CLI)
    # ------------------------------------------------------------------

    def apply_tcc_config(self, config_file: str, dry_run: bool = False) -> None:
        """Apply TCC configuration from a file.

        :param str config_file: Path to configuration file.
        :param bool dry_run: If True, validate without applying.
        """
        self._tcc_service.apply(config_file=config_file, dry_run=dry_run)

    def get_tcc_status(self) -> Dict[str, Any]:
        """Return current TCC configuration status.

        :return: Status dictionary.
        :rtype: dict
        """
        return self._tcc_service.status()

    def reset_tcc_config(self) -> bool:
        """Reset TCC configuration metadata to defaults.

        :return: True on success.
        :rtype: bool
        """
        return self._tcc_service.reset()

    def validate_tcc_config(self, config_file: str) -> bool:
        """Validate a TCC configuration file without applying it.

        :param str config_file: Path to configuration file.
        :return: True if the file is valid.
        :rtype: bool
        """
        return self._tcc_service.validate(config_file=config_file)

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
        output: list[str] = []
        with _stage_span("install", ctx, output):
            output += self._installer_service.install(
                transport=self._make_transport(ctx),
                dry_run=ctx.dry_run,
            )
        return output

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
                    self.apply_tcc_config(ctx.tcc_config_path, dry_run=dry_run)
                    output.append(f"TCC config applied from '{ctx.tcc_config_path}'")
                if ctx.tsn_config_path:
                    self.apply_config(ctx.tsn_config_path, dry_run=dry_run)
                    output.append(f"TSN config applied from '{ctx.tsn_config_path}'")
            else:
                # TODO: Transfer and apply TCC/TSN config for remote targets
                logger.info("<<<<Applying config for remote target '%s'", target.id)
                transport = self._make_transport(ctx)
                if ctx.tcc_config_path:
                    transport.put_file(ctx.tcc_config_path, "/tmp/tcc.xml")
                    transport.run(["tch", "tcc", "apply", "/tmp/tcc.xml"])
                if ctx.tsn_config_path:
                    transport.put_file(ctx.tsn_config_path, "/tmp/tsn.xml")
                    transport.run(["tch", "tsn", "apply", "/tmp/tsn.xml"])
            output.append(f"[{target.id}] Configuration applied")
        return output

    def stage_run(self, ctx: StageContext) -> list[str]:
        """Execute the workflow on a single local target.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        """
        output: list[str] = []
        with _stage_span("run", ctx, output):
            transport = self._make_transport(ctx)
            output += self._ptp_service.start_grandmaster(transport=transport, dry_run=ctx.dry_run)
            output += self._ptp_service.verify_grandmaster_status(transport=transport, dry_run=ctx.dry_run)
            output += self._ptp_service.start_phc2sys(transport=transport, dry_run=ctx.dry_run)
            output += self._ai_workload_service.start(transport=transport, dry_run=ctx.dry_run)
            output += self._testbench_service.start_transmitter(transport=transport, dry_run=ctx.dry_run)
        return output

    def stage_results(self, ctx: StageContext) -> list[str]:
        """Collect results, stop workloads, and gather logs for this target's role.

        Dispatches on ``ctx.target.role``:

        - ``None`` (single local target) — stop TX + collect testbench and AI logs.
        - ``"talker"`` — stop testbench transmitter → collect testbench logs.
        - ``"listener"`` — stop testbench receiver → collect testbench logs
          → collect AI workload logs.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        :raises ValueError: If ``ctx.target.role`` is an unexpected value.
        """
        transport = self._make_transport(ctx)
        role = ctx.target.role
        output: list[str] = []
        with _stage_span("results", ctx, output):
            if role is None or role == "talker":
                output += self._testbench_service.stop_transmitter(transport=transport, dry_run=ctx.dry_run)
                output += self._testbench_service.collect_logs(transport=transport, dry_run=ctx.dry_run)
                if role is None:  # single local target — also collect AI workload logs
                    output += self._ai_workload_service.collect_logs(transport=transport, dry_run=ctx.dry_run)
            elif role == "listener":
                output += self._testbench_service.stop_receiver(transport=transport, dry_run=ctx.dry_run)
                output += self._testbench_service.collect_logs(transport=transport, dry_run=ctx.dry_run)
                output += self._ai_workload_service.collect_logs(transport=transport, dry_run=ctx.dry_run)
            else:
                raise ValueError(
                    f"stage_results: unsupported role '{role}'. "
                    "Expected None, 'talker', or 'listener'."
                )
        return output

    def stage_run_ptp_phase(self, ctx: StageContext) -> list[str]:
        """Run the full PTP setup phase for this target's role.

        Delegates to :meth:`PtpService.run_ptp_phase` with the role from
        ``ctx.target.role``.  The service handles all internal sequencing
        (start → verify → phc2sys), so both talker and listener can run
        this step in parallel; the step barrier is only cleared once both
        have confirmed lock.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        """
        output: list[str] = []
        with _stage_span("run_ptp_phase", ctx, output):
            output += self._ptp_service.run_ptp_phase(
                transport=self._make_transport(ctx),
                role=ctx.target.role,
                dry_run=ctx.dry_run,
            )
        return output

    def stage_run_workloads(self, ctx: StageContext) -> list[str]:
        """Start workloads for this target's role.

        Dispatches on ``ctx.target.role``:

        - ``"listener"`` — start AI workload → start testbench receiver.
        - ``"talker"`` — start testbench transmitter (last to start).

        Two sequential steps in the multi-target registry enforce the
        listener-before-talker ordering; this method only handles what
        runs on each role, not the cross-target sequence.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        :raises ValueError: If ``ctx.target.role`` is an unexpected value.
        """
        transport = self._make_transport(ctx)
        role = ctx.target.role
        output: list[str] = []
        with _stage_span("run_workloads", ctx, output):
            if role == "listener":
                output += self._ai_workload_service.start(transport=transport, dry_run=ctx.dry_run)
                output += self._testbench_service.start_receiver(transport=transport, dry_run=ctx.dry_run)
            elif role == "talker":
                output += self._testbench_service.start_transmitter(transport=transport, dry_run=ctx.dry_run)
            else:
                raise ValueError(
                    f"stage_run_workloads: unsupported role '{role}'. "
                    "Expected 'talker' or 'listener'."
                )
        return output

    def stage_verify_hw(self, ctx: StageContext) -> list[str]:
        """Verify hardware readiness on this target before PTP startup.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        """
        output: list[str] = []
        with _stage_span("verify_hw", ctx, output):
            transport = self._make_transport(ctx)
            self._installer_service.verify_connectivity(transport)
            # TODO: add NIC / driver readiness checks via transport
        return output

    def stage_start_ptp(self, ctx: StageContext) -> list[str]:
        """Start the PTP daemon for this target's role.

        Dispatches on ``ctx.target.role``:

        - ``"listener"`` — start ptp4l slave → verify lock → start phc2sys.
        - ``"talker"`` — start ptp4l grandmaster → verify status → start phc2sys.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        :raises ValueError: If ``ctx.target.role`` is an unexpected value.
        """
        output: list[str] = []
        with _stage_span("start_ptp", ctx, output):
            output += self._ptp_service.run_ptp_phase(
                transport=self._make_transport(ctx),
                role=ctx.target.role,
                dry_run=ctx.dry_run,
            )
        return output

    def stage_validate_timesync(self, ctx: StageContext) -> list[str]:
        """Poll for PTP lock and validate the sub-microsecond offset target.

        If ``ctx.barrier`` is set (multi-DUT step), both targets call
        ``ctx.barrier.wait()`` after local sync is confirmed so the
        orchestrator only advances once *all* targets have simultaneously
        achieved the required sync quality.

        :param StageContext ctx: Current stage execution context.
        :return: Output log lines.
        :rtype: list[str]
        :raises TimeoutError: If the microsecond offset target is not achieved
            within the configured deadline.
        :raises threading.BrokenBarrierError: If a peer target fails before
            reaching the barrier.
        """
        output: list[str] = []
        with _stage_span("validate_timesync", ctx, output):
            transport = self._make_transport(ctx)
            output += self._ptp_service.verify_slave_lock(transport=transport, dry_run=ctx.dry_run)
            # Mutual rendezvous: both targets must confirm sync before proceeding.
            if ctx.barrier is not None:
                output.append(f"[{ctx.target.id}] timesync confirmed — waiting at barrier")
                logger.info(
                    "[barrier] waiting  thread='%s'  n_waiting=%d/%d  broken=%s",
                    threading.current_thread().name,
                    ctx.barrier.n_waiting,
                    ctx.barrier.parties,
                    ctx.barrier.broken,
                )
                # Wait for all targets to reach this point.  If any target fails before the barrier,
                # the barrier is broken and all waiting threads receive a BrokenBarrierError.

                ctx.barrier.wait()
                logger.info(
                    "[barrier] passed   thread='%s'  parties=%d",
                    threading.current_thread().name,
                    ctx.barrier.parties,
                )
                output.append(f"[{ctx.target.id}] all targets confirmed timesync — proceeding")
        return output
