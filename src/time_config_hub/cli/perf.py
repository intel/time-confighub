# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Perf CLI Command Group

End-to-end Perf measurement pipeline commands for Intel TCC platforms.

BKM: Setup (System Clock, NIC Mac) -> Config RTC App -> Time Sync -> Start Workload -> Run Test (Test Duration) -> Collect/Show Report

Q: Should we expose the configuration steps of 'RUN RTC Testbench' in a single command: RUN TEST or separate commands for each stage: APPLY CONFIG, START WORKLOAD, RUN TEST?

Option 1: Encapsulate TimeSync+StartWorkload+RunTest into a single 'RUN TEST' command
Option 2: Have a dedicated command for TimeSync, StartWorkload and RunTest, allowing more granular control and visibility into each stage

Ingredient Required per command:
install: OrchestratorConfig with topology and config details for install stage
        - topology: Single, B2B
        - targets: id, ip_address, ssh_user, ssh_password, ssh_port (for remote targets)
        - install_config: any specific config needed for installation

system config apply: TCC, TSN or both
        - config file (YAML): define TCC and TSN XML file path

system config show: Show TCC + TSN last applied config details. If not available, show the current system config (only the supported fields, not the full system config dump)

tch perf app config update: RTC testbench app config


Command tree::

    tch perf install                         # Install dependencies and tools on the local target (or all targets in multi-DUT mode)
    tch perf system  config apply  -f FILE   # TCC tuning, TSN config
    tch perf app     config update -f FILE   # RTC testbench app config
    tch perf timesync start|stop|status
    tch perf workload start|stop|status
    tch perf test     run|status
    tch perf report   collect|show
    tch perf pipeline                     # full fixed pipeline: apply_config → run → results
                                          # full fixed pipeline with install: install → apply_config → run → results


Service routing:
    - Direct commands (system, app, timesync, workload, test, report) are dispatched
      via Orchestrator.execute(ServiceRequest) without touching the IPC socket.
    - perf pipeline sends ServiceRequest(command=ORCHESTRATE) via the Unix socket
      so the daemon owns the long-running pipeline.
"""

import json
import logging
import sys
from typing import Optional

import click
import yaml

from time_config_hub.cli.exit_codes import TchExitCode
from time_config_hub.orchestrator.orchestrator import Orchestrator
from time_config_hub.orchestrator.ipc import send_service_request
from time_config_hub.orchestrator.models import (
    DeploymentTopologyType,
    OrchestratorConfig,
    ServiceCommand,
    ServiceRequest,
    ServiceType,
    Target,
)

logger = logging.getLogger(__name__)

# Fixed stage pipeline for perf pipeline (install is a separate command)
_PERF_PIPELINE_STAGES = ["apply_config", "run", "results"]


# =============================================================================
# Root group
# =============================================================================

@click.group("perf")
def perf_group():
    """Perf measurement pipeline for Intel TCC platforms."""


# =============================================================================
# perf install
# =============================================================================

@perf_group.command("install")
@click.option("--dry-run", is_flag=True, help="Show actions without executing")
@click.pass_context
def perf_install(ctx, dry_run: bool):
    """Install Perf tooling and dependencies on the local target.

    Example usage::

        tch perf install
        tch perf install --dry-run

    :param ctx: Click context object
    :param bool dry_run: Show actions without executing
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        req = ServiceRequest(
            command=ServiceCommand.ORCHESTRATE,
            service_type=ServiceType.BOTH,
            dry_run=dry_run,
            orchestrator_config=OrchestratorConfig(
                topology_type=DeploymentTopologyType.SINGLE_LOCAL,
                targets=[Target(id="local", ip_address="127.0.0.1")],
                tcc_config="",
                tsn_config="",
                stages_to_run=["install"],
                dry_run=dry_run,
            ),
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "Install failed")
        for line in svc_result.logs:
            click.echo(f"  {line}")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error during install")
        click.echo("✗ Install failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo("✓ Install completed successfully")
        sys.exit(exit_code)


# =============================================================================
# perf system  →  config  →  apply
# =============================================================================

@perf_group.group("system")
def perf_system():
    """System-level TCC tuning configuration."""


@perf_system.group("config")
def perf_system_config():
    """System configuration sub-commands."""


@perf_system_config.command("apply")
@click.option("-f", "--file", "config_file",
              type=click.Path(exists=True), required=True,
              help="Path to TCC system configuration YAML/XML file")
@click.option("--dry-run", is_flag=True, help="Show actions without executing")
@click.pass_context
def perf_system_config_apply(ctx, config_file: str, dry_run: bool):
    """Apply TCC system (tuning) configuration from file.

    Routes to: ServiceType.TCC / ServiceCommand.APPLY

    Example usage::

        tch perf system config apply -f tcc-system.yaml
        tch perf system config apply -f tcc-system.yaml --dry-run

    :param ctx: Click context object
    :param str config_file: Path to TCC configuration file
    :param bool dry_run: Show actions without executing
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        if dry_run:
            click.echo("DRY RUN MODE - No changes will be applied")
        req = ServiceRequest(
            command=ServiceCommand.APPLY,
            service_type=ServiceType.TCC,
            config_path=config_file,
            dry_run=dry_run,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "TCC system config apply failed")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error applying system config")
        click.echo("✗ System config apply failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo("✓ System (TCC) configuration applied successfully")
        sys.exit(exit_code)


# =============================================================================
# perf app  →  config  →  update
# =============================================================================

@perf_group.group("app")
def perf_app():
    """RTC testbench application configuration."""


@perf_app.group("config")
def perf_app_config():
    """Application configuration sub-commands."""


@perf_app_config.command("update")
@click.option("-f", "--file", "config_file",
              type=click.Path(exists=True), required=True,
              help="Path to RTC testbench application configuration YAML file")
@click.option("--dry-run", is_flag=True, help="Show actions without executing")
@click.pass_context
def perf_app_config_update(ctx, config_file: str, dry_run: bool):
    """Update RTC testbench application configuration from file.

    Routes to: ServiceType.RTC / ServiceCommand.APPLY

    Example usage::

        tch perf app config update -f rtc-app.yaml
        tch perf app config update -f rtc-app.yaml --dry-run

    :param ctx: Click context object
    :param str config_file: Path to RTC testbench configuration file
    :param bool dry_run: Show actions without executing
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        if dry_run:
            click.echo("DRY RUN MODE - No changes will be applied")
        req = ServiceRequest(
            command=ServiceCommand.APPLY,
            service_type=ServiceType.RTC,
            config_path=config_file,
            dry_run=dry_run,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "RTC app config update failed")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error updating app config")
        click.echo("✗ App config update failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo("✓ Application (RTC testbench) configuration updated successfully")
        sys.exit(exit_code)


# =============================================================================
# perf timesync
# =============================================================================

@perf_group.group("timesync")
def perf_timesync():
    """PTP / time synchronisation commands."""


@perf_timesync.command("start")
@click.option("--role",
              type=click.Choice(["grandmaster", "slave"]),
              default="grandmaster", show_default=True,
              help="PTP role for this target")
@click.option("--dry-run", is_flag=True, help="Show actions without executing")
@click.pass_context
def perf_timesync_start(ctx, role: str, dry_run: bool):
    """Start PTP time synchronisation service.

    Routes to: ServiceType.TIMESYNC / ServiceCommand.START

    Example usage::

        tch perf timesync start
        tch perf timesync start --role slave

    :param ctx: Click context object
    :param str role: PTP role — grandmaster or slave
    :param bool dry_run: Show actions without executing
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        req = ServiceRequest(
            command=ServiceCommand.START,
            service_type=ServiceType.TIMESYNC,
            interface=role,   # role conveyed via interface field
            dry_run=dry_run,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "Timesync start failed")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error starting timesync")
        click.echo("✗ Timesync start failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo(f"✓ PTP timesync started (role={role})")
        sys.exit(exit_code)


@perf_timesync.command("stop")
@click.pass_context
def perf_timesync_stop(ctx):
    """Stop PTP time synchronisation service.

    Routes to: ServiceType.TIMESYNC / ServiceCommand.STOP

    Example usage::

        tch perf timesync stop

    :param ctx: Click context object
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        req = ServiceRequest(
            command=ServiceCommand.STOP,
            service_type=ServiceType.TIMESYNC,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "Timesync stop failed")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error stopping timesync")
        click.echo("✗ Timesync stop failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo("✓ PTP timesync stopped")
        sys.exit(exit_code)


@perf_timesync.command("status")
@click.option("--format", "-f", "output_format",
              type=click.Choice(["table", "json", "yaml"]),
              default="table", show_default=True)
@click.pass_context
def perf_timesync_status(ctx, output_format: str):
    """Show PTP time synchronisation status.

    Routes to: ServiceType.TIMESYNC / ServiceCommand.STATUS

    Example usage::

        tch perf timesync status
        tch perf timesync status --format json

    :param ctx: Click context object
    :param str output_format: Output format (table, json, yaml)
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        req = ServiceRequest(
            command=ServiceCommand.STATUS,
            service_type=ServiceType.TIMESYNC,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "Timesync status failed")
        _print_result(svc_result.data or {}, output_format, "PTP Timesync Status")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error retrieving timesync status")
        click.echo("✗ Timesync status failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo("✓ Status retrieved successfully")
        sys.exit(exit_code)


# =============================================================================
# perf workload
# =============================================================================

@perf_group.group("workload")
def perf_workload():
    """AI workload and RTC testbench transmitter/receiver control."""


@perf_workload.command("start")
@click.option("--role",
              type=click.Choice(["talker", "listener", "all"]),
              default="all", show_default=True,
              help="Workload role to start")
@click.option("--dry-run", is_flag=True, help="Show actions without executing")
@click.pass_context
def perf_workload_start(ctx, role: str, dry_run: bool):
    """Start AI and/or testbench workloads.

    Routes to: ServiceType.WORKLOAD / ServiceCommand.START

    Example usage::

        tch perf workload start
        tch perf workload start --role talker

    :param ctx: Click context object
    :param str role: Workload role — talker, listener, or all
    :param bool dry_run: Show actions without executing
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        req = ServiceRequest(
            command=ServiceCommand.START,
            service_type=ServiceType.WORKLOAD,
            interface=role,
            dry_run=dry_run,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "Workload start failed")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error starting workload")
        click.echo("✗ Workload start failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo(f"✓ Workload started (role={role})")
        sys.exit(exit_code)


@perf_workload.command("stop")
@click.option("--role",
              type=click.Choice(["talker", "listener", "all"]),
              default="all", show_default=True,
              help="Workload role to stop")
@click.pass_context
def perf_workload_stop(ctx, role: str):
    """Stop AI and/or testbench workloads.

    Routes to: ServiceType.WORKLOAD / ServiceCommand.STOP

    Example usage::

        tch perf workload stop
        tch perf workload stop --role listener

    :param ctx: Click context object
    :param str role: Workload role — talker, listener, or all
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        req = ServiceRequest(
            command=ServiceCommand.STOP,
            service_type=ServiceType.WORKLOAD,
            interface=role,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "Workload stop failed")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error stopping workload")
        click.echo("✗ Workload stop failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo(f"✓ Workload stopped (role={role})")
        sys.exit(exit_code)


@perf_workload.command("status")
@click.option("--format", "-f", "output_format",
              type=click.Choice(["table", "json", "yaml"]),
              default="table", show_default=True)
@click.pass_context
def perf_workload_status(ctx, output_format: str):
    """Show running workload status.

    Routes to: ServiceType.WORKLOAD / ServiceCommand.STATUS

    Example usage::

        tch perf workload status
        tch perf workload status --format json

    :param ctx: Click context object
    :param str output_format: Output format (table, json, yaml)
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        req = ServiceRequest(
            command=ServiceCommand.STATUS,
            service_type=ServiceType.WORKLOAD,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "Workload status failed")
        _print_result(svc_result.data or {}, output_format, "Workload Status")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error retrieving workload status")
        click.echo("✗ Workload status failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo("✓ Status retrieved successfully")
        sys.exit(exit_code)


# =============================================================================
# perf test
# =============================================================================

@perf_group.group("test")
def perf_test():
    """Test execution commands."""


@perf_test.command("run")
@click.option("--duration", type=int, default=None,
              help="Test duration in seconds")
@click.option("--timeout", type=int, default=None,
              help="Max wait before aborting (seconds)")
@click.option("--dry-run", is_flag=True, help="Show actions without executing")
@click.pass_context
def perf_test_run(ctx, duration: Optional[int], timeout: Optional[int], dry_run: bool):
    """Execute the Perf test run stage on the local target.

    Sends the ``run`` workflow stage to the orchestrator, which starts PTP sync,
    launches the AI workload, and starts the RTC testbench transmitter.

    Routes to: ServiceCommand.ORCHESTRATE / stages=[\"run\"]

    Example usage::

        tch perf test run --duration 60
        tch perf test run --dry-run

    :param ctx: Click context object
    :param Optional[int] duration: Test duration in seconds
    :param Optional[int] timeout: Max wait before aborting
    :param bool dry_run: Show actions without executing
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        req = ServiceRequest(
            command=ServiceCommand.ORCHESTRATE,
            service_type=ServiceType.BOTH,
            dry_run=dry_run,
            orchestrator_config=OrchestratorConfig(
                topology_type=DeploymentTopologyType.SINGLE_LOCAL,
                targets=[Target(id="local", ip_address="127.0.0.1")],
                tcc_config="",
                tsn_config="",
                stages_to_run=["run"],
                dry_run=dry_run,
                test_duration=duration,
                timeout=timeout,
            ),
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "Test run failed")
        for line in svc_result.logs:
            click.echo(f"  {line}")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error during test run")
        click.echo("✗ Test run failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo("✓ Test run completed successfully")
        sys.exit(exit_code)


@perf_test.command("status")
@click.option("--format", "-f", "output_format",
              type=click.Choice(["table", "json", "yaml"]),
              default="table", show_default=True)
@click.pass_context
def perf_test_status(ctx, output_format: str):
    """Show status of the running or last completed test.

    Routes to: ServiceType.TEST / ServiceCommand.STATUS

    Example usage::

        tch perf test status
        tch perf test status --format json

    :param ctx: Click context object
    :param str output_format: Output format (table, json, yaml)
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        req = ServiceRequest(
            command=ServiceCommand.STATUS,
            service_type=ServiceType.TEST,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "Test status failed")
        _print_result(svc_result.data or {}, output_format, "Test Status")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error retrieving test status")
        click.echo("✗ Test status failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo("✓ Status retrieved successfully")
        sys.exit(exit_code)


# =============================================================================
# perf report
# =============================================================================

@perf_group.group("report")
def perf_report():
    """Result collection and reporting commands."""


@perf_report.command("collect")
@click.option("--output-dir", type=click.Path(), default=None,
              help="Local directory to store collected logs and metrics")
@click.pass_context
def perf_report_collect(ctx, output_dir: Optional[str]):
    """Collect logs and metrics from targets after a test run.

    Routes to: ServiceType.REPORT / ServiceCommand.COLLECT

    Example usage::

        tch perf report collect
        tch perf report collect --output-dir /tmp/perf-results

    :param ctx: Click context object
    :param Optional[str] output_dir: Directory to store collected data
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        req = ServiceRequest(
            command=ServiceCommand.COLLECT,
            service_type=ServiceType.REPORT,
            config_path=output_dir,   # output destination via config_path convention
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "Report collect failed")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error collecting report")
        click.echo("✗ Report collection failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo("✓ Report collected successfully")
            if output_dir:
                click.echo(f"  Saved to: {output_dir}")
        sys.exit(exit_code)


@perf_report.command("show")
@click.option("--format", "-f", "output_format",
              type=click.Choice(["table", "json", "yaml"]),
              default="table", show_default=True)
@click.pass_context
def perf_report_show(ctx, output_format: str):
    """Display the most recent Perf report.

    Routes to: ServiceType.REPORT / ServiceCommand.STATUS

    Example usage::

        tch perf report show
        tch perf report show --format json

    :param ctx: Click context object
    :param str output_format: Output format (table, json, yaml)
    """
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    result_ok = False
    try:
        req = ServiceRequest(
            command=ServiceCommand.STATUS,
            service_type=ServiceType.REPORT,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise RuntimeError(svc_result.errors[0] if svc_result.errors else "Report show failed")
        _print_result(svc_result.data or {}, output_format, "Perf Report")
        result_ok = True
        exit_code = TchExitCode.SUCCESS
    except Exception:
        logger.exception("Unexpected error showing report")
        click.echo("✗ Report show failed", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR
    finally:
        if result_ok:
            click.echo("✓ Report displayed successfully")
        sys.exit(exit_code)


# =============================================================================
# perf pipeline  —  full fixed pipeline via IPC daemon
# =============================================================================

@perf_group.command("pipeline")
# -- Config files --
@click.option("--tcc-config", type=click.Path(exists=True), required=True,
              help="Path to TCC system configuration file")
@click.option("--tsn-config", type=click.Path(exists=True), default=None,
              help="Path to TSN configuration file (optional)")
# -- Topology: config file --
@click.option("--topology-config", type=click.Path(exists=True), default=None,
              help="YAML file defining target topology and SSH credentials")
# -- Topology: CLI flags (B2B / MULTI_DUT) --
@click.option("--talker", default=None,
              help="Talker IP address (required with --listeners)")
@click.option("--talker-user", default="root", show_default=True)
@click.option("--talker-password", default=None,
              help="Talker SSH password (required for remote targets)")
@click.option("--talker-port", default=22, type=int, show_default=True)
@click.option("--listeners", multiple=True,
              help="Listener IP address(es); repeatable for MULTI_DUT")
@click.option("--listeners-user", default="root", show_default=True)
@click.option("--listeners-password", default=None)
@click.option("--listeners-port", default=22, type=int, show_default=True)
# -- Run options --
@click.option("--test-duration", type=int, default=None,
              help="Expected test duration in seconds (for progress reporting)")
@click.option("--timeout", type=int, default=None,
              help="Max allowed run time in seconds before aborting")
@click.option("--dry-run", is_flag=True,
              help="Print pipeline plan without executing")
@click.pass_context
def perf_pipeline(
    ctx,
    tcc_config, tsn_config,
    topology_config,
    talker, talker_user, talker_password, talker_port,
    listeners, listeners_user, listeners_password, listeners_port,
    test_duration, timeout, dry_run,
):
    """Run the full Perf pipeline end-to-end via the orchestrator daemon.

    Executes the fixed stage sequence: apply_config → run → results.
    Use ``tch perf install`` beforehand to set up dependencies.

    Topology defaults to SINGLE_LOCAL when no topology flags are given.
    Provide either ``--topology-config`` OR ``--talker``/``--listeners``
    flags, not both.

    Example usage::

        # Local (single machine)
        tch perf pipeline --tcc-config tcc.xml

        # B2B via CLI flags
        tch perf pipeline --tcc-config tcc.xml \\
            --talker 192.168.1.10 --talker-password pass \\
            --listeners 192.168.1.20 --listeners-password pass

        # B2B via topology file
        tch perf pipeline --tcc-config tcc.xml --topology-config topology.yaml

        # Dry run
        tch perf pipeline --tcc-config tcc.xml --dry-run

    :param ctx: Click context object
    :param str tcc_config: Path to TCC system configuration file
    :param Optional[str] tsn_config: Path to TSN configuration file
    :param Optional[str] topology_config: Path to topology YAML file
    :param Optional[str] talker: Talker IP address
    :param str talker_user: Talker SSH username
    :param Optional[str] talker_password: Talker SSH password
    :param int talker_port: Talker SSH port
    :param tuple listeners: Listener IP address(es)
    :param str listeners_user: Listeners SSH username
    :param Optional[str] listeners_password: Listeners SSH password
    :param int listeners_port: Listeners SSH port
    :param Optional[int] test_duration: Expected test duration in seconds
    :param Optional[int] timeout: Max allowed run time in seconds
    :param bool dry_run: Print pipeline plan without executing
    """
    # -- Conflict check: topology file and CLI flags are mutually exclusive ---
    has_cli_topology = bool(talker or listeners)
    if topology_config and has_cli_topology:
        click.echo(
            "✗ Cannot use --topology-config together with --talker/--listeners flags",
            err=True,
        )
        sys.exit(TchExitCode.USER_INPUT_ERROR)

    # -- Build target list and detect topology type -----------------------
    targets: list[Target] = []
    topology_type = DeploymentTopologyType.SINGLE_LOCAL

    if topology_config:
        targets, topology_type = _parse_perf_topology(topology_config)

    elif has_cli_topology:
        if not talker:
            click.echo("✗ --talker is required when using --listeners", err=True)
            sys.exit(TchExitCode.USER_INPUT_ERROR)
        if not listeners:
            click.echo("✗ --listeners is required when using --talker", err=True)
            sys.exit(TchExitCode.USER_INPUT_ERROR)
        if not talker_password:
            click.echo("✗ --talker-password is required for remote targets", err=True)
            sys.exit(TchExitCode.USER_INPUT_ERROR)

        targets.append(Target(
            id="talker", ip_address=talker,
            ssh_user=talker_user, ssh_password=talker_password, ssh_port=talker_port,
        ))
        for i, lip in enumerate(listeners):
            targets.append(Target(
                id=f"listener-{i + 1}", ip_address=lip,
                ssh_user=listeners_user,
                ssh_password=listeners_password or talker_password,
                ssh_port=listeners_port,
            ))
        topology_type = (
            DeploymentTopologyType.B2B if len(listeners) == 1
            else DeploymentTopologyType.MULTI_DUT
        )
    else:
        targets.append(Target(id="local", ip_address="127.0.0.1"))
        topology_type = DeploymentTopologyType.SINGLE_LOCAL

    # -- Pipeline summary --------------------------------------------------
    click.echo("\nPerf Pipeline Summary")
    click.echo("=" * 40)
    click.echo(f"Topology   : {topology_type.value}")
    click.echo(f"Targets    : {len(targets)}")
    for t in targets:
        click.echo(f"  [{t.id}] {t.ip_address}")
    click.echo(f"Stages     : {' → '.join(_PERF_PIPELINE_STAGES)}")
    click.echo(f"TCC Config : {tcc_config}")
    click.echo(f"TSN Config : {tsn_config or '(none)'}")
    if test_duration:
        click.echo(f"Duration   : {test_duration}s")
    if timeout:
        click.echo(f"Timeout    : {timeout}s")
    if dry_run:
        click.echo("Dry Run    : enabled — no actions will be executed")
    click.echo("=" * 40)

    if dry_run:
        click.echo("✓ Dry run complete — no actions executed")
        sys.exit(TchExitCode.SUCCESS)

    # -- Build and send ServiceRequest via IPC ----------------------------
    orch_config = OrchestratorConfig(
        topology_type=topology_type,
        targets=targets,
        tcc_config=tcc_config,
        tsn_config=tsn_config or "",
        stages_to_run=_PERF_PIPELINE_STAGES,
        dry_run=dry_run,
        test_duration=test_duration,
        timeout=timeout,
    )
    request = ServiceRequest(
        command=ServiceCommand.ORCHESTRATE,
        service_type=ServiceType.BOTH,
        orchestrator_config=orch_config,
    )

    try:
        result = send_service_request(request)
        for line in result.logs:
            click.echo(f"  {line}")
        if result.success:
            click.echo("\n✓ Perf pipeline completed successfully")
            sys.exit(TchExitCode.SUCCESS)
        else:
            for err in result.errors:
                click.echo(f"✗ {err}", err=True)
            click.echo("\n✗ Perf pipeline failed", err=True)
            sys.exit(TchExitCode.UNEXPECTED_ERROR)

    except ConnectionRefusedError:
        click.echo(
            "✗ Could not connect to Orchestrator daemon. Is tch.service running?",
            err=True,
        )
        sys.exit(TchExitCode.UNEXPECTED_ERROR)

    except Exception:
        logger.exception("Unexpected error during KPI orchestration")
        click.echo("✗ Unexpected error during KPI orchestration", err=True)
        sys.exit(TchExitCode.UNEXPECTED_ERROR)


# =============================================================================
# Internal helpers
# =============================================================================

def _parse_perf_topology(config_path: str) -> tuple[list[Target], DeploymentTopologyType]:
    """Parse a topology YAML file and return (targets, topology_type).

    Expected YAML structure::

        defaults:
            ssh_user: root
            ssh_password: demo123
            ssh_port: 22
        talker:
            ip: 192.168.1.10
            ssh_password: talker-pass
        listeners:
            - ip: 192.168.1.20
              ssh_password: listener-pass

    :param str config_path: Path to the topology YAML file
    :return: Tuple of (targets list, detected topology type)
    :rtype: tuple[list[Target], DeploymentTopologyType]
    :raises click.ClickException: If the file is unreadable or invalid
    """
    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        raise click.ClickException(f"Cannot read topology config '{config_path}': {e}")

    if not data:
        raise click.ClickException(f"Topology config '{config_path}' is empty")

    defaults = data.get("defaults", {})
    def_user = defaults.get("ssh_user", "root")
    def_pass = defaults.get("ssh_password")
    def_port = defaults.get("ssh_port", 22)

    targets: list[Target] = []

    talker_data = data.get("talker")
    if talker_data:
        if not talker_data.get("ip"):
            raise click.ClickException("Talker entry is missing required 'ip' field")
        targets.append(Target(
            id="talker",
            ip_address=talker_data["ip"],
            ssh_user=talker_data.get("ssh_user", def_user),
            ssh_password=talker_data.get("ssh_password", def_pass),
            ssh_port=talker_data.get("ssh_port", def_port),
        ))

    listeners_data = data.get("listeners", [])
    if isinstance(listeners_data, dict):
        listeners_data = [listeners_data]
    for i, ld in enumerate(listeners_data):
        if not ld.get("ip"):
            raise click.ClickException(f"Listener {i + 1} is missing required 'ip' field")
        targets.append(Target(
            id=f"listener-{i + 1}",
            ip_address=ld["ip"],
            ssh_user=ld.get("ssh_user", def_user),
            ssh_password=ld.get("ssh_password", def_pass),
            ssh_port=ld.get("ssh_port", def_port),
        ))

    if len(targets) == 0:
        topology_type = DeploymentTopologyType.SINGLE_LOCAL
        targets.append(Target(id="local", ip_address="127.0.0.1"))
    elif len(targets) == 2:
        topology_type = DeploymentTopologyType.B2B
    else:
        topology_type = DeploymentTopologyType.MULTI_DUT

    return targets, topology_type


def _print_result(data: dict, output_format: str, title: str) -> None:
    """Render a status/data dict in the requested output format.

    :param dict data: Data to display
    :param str output_format: One of table, json, yaml
    :param str title: Section title for table format
    """
    if output_format == "json":
        click.echo(json.dumps(data, indent=2))
    elif output_format == "yaml":
        click.echo(yaml.dump(data, default_flow_style=False))
    else:
        click.echo(title)
        click.echo("=" * 40)
        for key, value in data.items():
            click.echo(f"  {key}: {value}")
        click.echo("=" * 40)
