# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Time Config Hub CLI

Command-line interface for managing real time configurations.

This module provides a comprehensive CLI for TCC and TSN configuration management, including:

- Applying configurations from files
- Viewing configuration status
- Resetting configurations to defaults
- Managing the daemon service
- Configuration validation and display
- Orchestration services with multiple topology and test configuration options [HEAMINGS: FOR TESTING ONLY]

The CLI supports both interactive and non-interactive usage patterns,
with proper error handling and logging capabilities.
"""

import json
import logging
import os
import sys
from typing import Optional

import click
import yaml

from .. import __version__
from time_config_hub.config.config_reader import load_app_config
from time_config_hub.orchestrator.orchestrator import Orchestrator
from time_config_hub.exceptions import TCCConfigError, TSNConfigError
from time_config_hub.cli.exit_codes import TchExitCode
from time_config_hub.config.logging import setup_logging

from time_config_hub.orchestrator.models import (
        DeploymentTopologyType,
        WORKFLOW_STAGES,
        OrchestratorConfig,
        ServiceCommand,
        ServiceRequest,
        ServiceType,
        Target,
)

from time_config_hub.orchestrator.ipc import send_orchestration_request

logger = logging.getLogger(__name__)


@click.group()
@click.version_option(__version__, "--version", "-V", prog_name="tch")
def cli():
    """
    Time Config Hub - Manage real time (TCC and TSN) configurations for Intel hardware.

    Example usage:
        tch --version
    """
    ctx = click.get_current_context()

    # Optional: allow help/version without root
    if ctx.invoked_subcommand not in (None,):
        if os.geteuid() != 0:
            click.echo("✗ This command requires sudo/root", err=True)
            raise SystemExit(TchExitCode.USER_INPUT_ERROR)

    app_config = load_app_config()
    setup_logging(app_config)
    ctx.ensure_object(dict)
    ctx.obj["app_config"] = app_config


#===============================================================================
# Commands for TCH Daemon Management
# Implemented as a subgroup under the main CLI (tch daemon <command>)
#===============================================================================

@cli.command()
@click.pass_context
def daemon_status(ctx):
    """
    Show the status of the daemon.

    Example usage:
        tch daemon-status

    :param ctx: Click context object
    """
    logger.info("Checking daemon status...")
    app_config = ctx.obj.get("app_config")
    general_config = app_config.get("General")
    listening_folders = general_config.get("ListeningFolder")

    result = False
    try:
        # Check systemd service status
        orch = Orchestrator(app_config=app_config)
        service_status = orch.service_manager.get_service_status()

        if service_status == "active":
            status_msg = "✓ Service status: active"
        elif service_status == "inactive":
            status_msg = "✗ Service status: inactive"
        else:
            status_msg = f"⚠ Service status: {service_status}"

        click.echo(status_msg)
        click.echo("")
        click.echo("Daemon Status")
        click.echo("=" * 40)
        click.echo(f"Listening Folders: {len(listening_folders)}")
        for directory in listening_folders:
            click.echo(f"  - {directory}")
        click.echo("")
        result = True
        exit_code = TchExitCode.SUCCESS

    except Exception:
        logger.exception("Unexpected error retrieving daemon status")
        click.echo("✗ Unexpected error retrieving daemon status", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        click.echo("=" * 40)
        if result:
            click.echo("✓ Daemon status retrieved successfully")
            sys.exit(exit_code)
        else:
            click.echo("✗ Failed to retrieve daemon status", err=True)
            sys.exit(exit_code)


@cli.command()
@click.pass_context
def daemon_start(ctx):
    """
    Start the daemon service.

    Example usage:
        tch daemon-start

    :param ctx: Click context object
    :raises subprocess.CalledProcessError: If systemctl command fails
    :raises FileNotFoundError: If systemctl is not available
    """
    logger.info("Starting daemon...")
    app_config = ctx.obj.get("app_config")

    result = False
    outcome_message = None

    try:
        orch = Orchestrator(app_config=app_config)

        # Avoid restarting if already running
        service_status = orch.service_manager.get_service_status()
        if service_status == "active":
            outcome_message = "✓ Daemon is already running"
            result = True
            exit_code = TchExitCode.SUCCESS
            return

        orch.service_manager.start_service()
        outcome_message = "✓ Daemon started successfully"
        result = True
        exit_code = TchExitCode.SUCCESS

    except Exception:
        logger.exception("Unexpected error starting daemon")
        click.echo("✗ Unexpected error starting daemon", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        if result:
            click.echo(outcome_message)
            sys.exit(exit_code)
        else:
            click.echo("✗ Failed to start daemon", err=True)
            sys.exit(exit_code)


@cli.command()
@click.pass_context
def daemon_stop(ctx):
    """
    Stop the daemon service.

    Example usage:
        tch daemon-stop

    :param ctx: Click context object
    :raises subprocess.CalledProcessError: If systemctl command fails
    :raises FileNotFoundError: If systemctl is not available
    """
    logger.info("Stopping TSN configuration daemon...")
    app_config = ctx.obj.get("app_config")

    result = False
    outcome_message = None
    try:
        orch = Orchestrator(app_config=app_config)

        service_status = orch.service_manager.get_service_status()
        if service_status != "active":
            outcome_message = "✓ Daemon is not running"
            result = True
            exit_code = TchExitCode.SUCCESS
            return

        orch.service_manager.stop_service()
        outcome_message = "✓ Daemon stopped successfully"
        result = True
        exit_code = TchExitCode.SUCCESS

    except Exception:
        logger.exception("Unexpected error stopping daemon")
        click.echo("✗ Unexpected error stopping daemon", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        if result:
            click.echo(outcome_message)
            sys.exit(exit_code)
        else:
            click.echo("✗ Failed to stop daemon", err=True)
            sys.exit(exit_code)


@cli.command()
@click.pass_context
def daemon_restart(ctx):
    """
    Restart the daemon service.

    Example usage:
        tch daemon-restart

    :param ctx: Click context object
    :raises subprocess.CalledProcessError: If systemctl command fails
    :raises FileNotFoundError: If systemctl is not available
    """
    logger.info("Restarting daemon...")
    app_config = ctx.obj.get("app_config")

    result = False
    try:
        orch = Orchestrator(app_config=app_config)
        orch.service_manager.restart_service()
        result = True
        exit_code = TchExitCode.SUCCESS

    except Exception:
        logger.exception("Unexpected error restarting daemon")
        click.echo("✗ Unexpected error restarting daemon", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        if result:
            click.echo("✓ Daemon restarted successfully")
            sys.exit(exit_code)
        else:
            click.echo("✗ Failed to restart daemon", err=True)
            sys.exit(exit_code)


#===============================================================================
# TCH Configuration Commands for TSN Domain
# Implemented as a subgroup under the main CLI (tch tsn <command>)
#===============================================================================

@cli.group()
def tsn():
    """Commands for managing TSN configurations."""
    pass

@tsn.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--interface", "-i", help="Network interface to configure")
@click.option("--dry-run", is_flag=True, help="Show commands without executing")
@click.pass_context
def apply(ctx, config_file: str, interface: Optional[str], dry_run: bool):
    """
    Apply TSN configuration from XML/YAML file.

    Example usage:
        tch tsn apply /path/to/config.yaml -i eth0 --dry-run
        tch tsn apply /path/to/config.xml

    :param ctx: Click context object
    :param str config_file: Path to configuration file
    :param Optional[str] interface: Network interface to configure
    :param bool dry_run: Show commands without executing
    :raises TSNConfigError: If configuration application fails
    """
    logger.info(f"Applying configuration from file: {config_file}")
    app_config = ctx.obj.get("app_config")

    result_ok = False

    try:
        orch = Orchestrator(app_config=app_config)

        if interface:
            click.echo(f"Target interface: {interface}")

        if dry_run:
            click.echo("DRY RUN MODE - No changes will be applied")

        req = ServiceRequest(
            command=ServiceCommand.APPLY,
            service_type=ServiceType.TSN,
            config_path=config_file,
            dry_run=dry_run,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise TSNConfigError(svc_result.errors[0] if svc_result.errors else "Apply failed")
        result_ok = True
        exit_code = TchExitCode.SUCCESS

    except TSNConfigError as e:
        logger.error(f"Failed to apply configuration: {e}")
        click.echo("✗ Failed to apply configuration (see logs for details)", err=True)
        exit_code = TchExitCode.USER_INPUT_ERROR

    except Exception:
        logger.exception("Unexpected error applying configuration")
        click.echo("✗ Unexpected error applying configuration", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        if result_ok:
            click.echo("✓ Configuration applied successfully")
            sys.exit(exit_code)
        else:
            sys.exit(exit_code)


@tsn.command()
@click.argument("interface")
@click.option(
    "--output_format",
    "-f",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Output format",
)
@click.pass_context
def status(ctx, interface: str, output_format: str):
    """
    Show current TSN configuration status.

    Example usage:
        tch tsn status -i eth0 --format json
        tch tsn status --format yaml

    :param ctx: Click context object
    :param Optional[str] interface: Network interface to show
    :param str output_format: Output format (table, json, yaml)
    :raises TSNConfigError: If status retrieval fails
    """
    logger.info("Retrieving TSN configuration status...")

    result = False
    try:
        app_config = ctx.obj.get("app_config")
        orch = Orchestrator(app_config=app_config)

        req = ServiceRequest(
            command=ServiceCommand.STATUS,
            service_type=ServiceType.TSN,
            interface=interface,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise TSNConfigError(svc_result.errors[0] if svc_result.errors else "Status failed")

        status_info = svc_result.data or {}

        if output_format == "json":
            click.echo(json.dumps(status_info, indent=2))
        elif output_format == "yaml":
            click.echo(yaml.dump(status_info, default_flow_style=False))
        else:
            # Table format
            click.echo("TSN Configuration Status")
            click.echo("=" * 40)
            for key, config in status_info.items():
                if config.strip() == "":
                    config = "Not Configured"
                click.echo(f"\n{key}:\n{config}")
            click.echo("=" * 40)
        result = True
        exit_code = TchExitCode.SUCCESS

    except TSNConfigError as e:
        logger.error(f"Configuration error: {e}")
        click.echo("✗ Failed to retrieve status (see logs for details)", err=True)
        exit_code = TchExitCode.USER_INPUT_ERROR

    except Exception:
        logger.exception("Unexpected error retrieving status")
        click.echo("✗ Unexpected error retrieving status", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        if result:
            click.echo("✓ Status retrieved successfully")
            sys.exit(exit_code)
        else:
            sys.exit(exit_code)


@tsn.command()
@click.argument("interface")
@click.option("--force", "-y", is_flag=True, help="Confirm reset without prompting")
@click.pass_context
def reset(ctx, interface: str, force: bool):
    """
    Reset TSN configuration to defaults.

    Example usage:
        tch tsn reset -i eth0

    :param ctx: Click context object
    :param Optional[str] interface: Network interface to reset
    :raises TSNConfigError: If configuration reset fails
    """
    logger.info("Resetting TSN configuration...")
    app_config = ctx.obj.get("app_config")

    result = False
    try:
        if interface:
            message = f"Reset TSN configuration for interface {interface}?"
        else:
            message = "Please provide an interface. Usage: tch reset -i <interface>"
            raise TSNConfigError("No interface specified for reset")

        # Confirm before resetting
        if not force and not click.confirm(message):
            click.echo("Operation cancelled")
            return

        app_config = ctx.obj.get("app_config")
        orch = Orchestrator(app_config=app_config)
        req = ServiceRequest(
            command=ServiceCommand.RESET,
            service_type=ServiceType.TSN,
            interface=interface,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise TSNConfigError(svc_result.errors[0] if svc_result.errors else "Reset failed")
        result = True
        exit_code = TchExitCode.SUCCESS

    except TSNConfigError as e:
        logger.error(f"Failed to reset configuration: {e}")
        click.echo("✗ Failed to reset configuration (see logs for details)", err=True)
        exit_code = TchExitCode.USER_INPUT_ERROR

    except Exception:
        logger.exception("Unexpected error resetting configuration")
        click.echo("✗ Unexpected error resetting configuration", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        if result:
            click.echo("✓ Configuration reset successfully")
            sys.exit(exit_code)
        else:
            sys.exit(exit_code)


@tsn.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.pass_context
def validate(ctx, config_file: str):
    """
    Validate TSN configuration file.

    Example usage:
        tch tsn validate /path/to/config.xml

    :param ctx: Click context object
    :param str config_file: Path to configuration file to validate
    """
    logger.info("Validating TSN configuration file...")
    app_config = ctx.obj.get("app_config")

    orch = Orchestrator(app_config=app_config)
    exit_code = TchExitCode.SUCCESS

    try:
        req = ServiceRequest(
            command=ServiceCommand.VALIDATE,
            service_type=ServiceType.TSN,
            config_path=config_file,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise TSNConfigError(svc_result.errors[0] if svc_result.errors else f"Configuration file {config_file} is invalid")

        logger.info(f"Configuration file {config_file} is valid")
        click.echo("✓ Configuration validated successfully\n")
        exit_code = TchExitCode.SUCCESS

    except TSNConfigError as exc:
        logger.error("Configuration validation failed")
        click.echo(f"✗ Validation failed: {exc}", err=True)
        exit_code = TchExitCode.USER_INPUT_ERROR

    except Exception as exc:  # surface any parsing/validation errors
        logger.exception("Configuration validation failed")
        click.echo(f"✗ Validation failed: {exc}", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        sys.exit(exit_code)


@cli.command()
@click.option(
    "--format",
    "-f",
    type=click.Choice(["table", "yaml", "json"]),
    default="table",
    help="Output format",
)
@click.pass_context
def config_show(ctx, format: str):
    """
    Show current CLI configuration settings.

    Example usage:
        tch config-show --format json
        tch config-show --format yaml
        tch config-show

    :param ctx: Click context object
    :param str format: Output format (table, json, yaml)
    """
    logger.info("Showing CLI configuration...")
    app_config = ctx.obj.get("app_config")
    general_config = app_config.get("General")

    result = False
    try:

        if format == "json":
            click.echo(json.dumps(app_config, indent=2))
        elif format == "yaml":
            click.echo(yaml.dump(app_config, default_flow_style=False))
        else:
            # Table format
            click.echo("TSN CLI Configuration")
            click.echo("=" * 40)
            click.echo("General Settings:")
            for key, value in general_config.items():
                click.echo(f"  {key}: {value}")
            click.echo("=" * 40)
        result = True
        exit_code = TchExitCode.SUCCESS

    except Exception:
        logger.exception("Unexpected error reading configuration")
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        if result:
            click.echo("✓ Configuration displayed successfully")
            sys.exit(exit_code)
        else:
            click.echo("✗ Unexpected Error reading configuration", err=True)
            sys.exit(exit_code)


#===============================================================================
# TCH Configuration Commands for TCC Domain
# Implemented as a subgroup under the main CLI (tch tcc <command>)
#===============================================================================

@cli.group()
def tcc():
    """Commands for managing TCC configurations."""
    pass

@tcc.command()
@click.option(
    "--output_format",
    "-f",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Output format",
)
@click.pass_context
def status(ctx, output_format: str):
    """
    Show current TCC configuration status.

    Example usage:
        tch tcc status --output_format table
        tch tcc status --output_format json
        tch tcc status --output_format yaml

    :param ctx: Click context object
    :param str output_format: Output format (table, json, yaml)
    :raises TCCConfigError: If status retrieval fails
    """
    logger.info("Retrieving TCC configuration status...")

    result = False
    try:
        app_config = ctx.obj.get("app_config")
        orch = Orchestrator(app_config=app_config)

        req = ServiceRequest(
            command=ServiceCommand.STATUS,
            service_type=ServiceType.TCC,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise TCCConfigError(svc_result.errors[0] if svc_result.errors else "Status failed")

        status_info = svc_result.data or {}

        if output_format == "json":
            click.echo(json.dumps(status_info, indent=2))
        elif output_format == "yaml":
            click.echo(yaml.dump(status_info, default_flow_style=False))
        else:
            click.echo("TCC Configuration Status")
            click.echo("=" * 40)
            for key, value in status_info.items():
                click.echo(f"{key}: {value}")
            click.echo("=" * 40)

        result = True
        exit_code = TchExitCode.SUCCESS

    except TCCConfigError as e:
        logger.error(f"Configuration error: {e}")
        click.echo("✗ Failed to retrieve status (see logs for details)", err=True)
        exit_code = TchExitCode.USER_INPUT_ERROR

    except Exception:
        logger.exception("Unexpected error retrieving status")
        click.echo("✗ Unexpected error retrieving status", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        if result:
            click.echo("✓ Status retrieved successfully")
            sys.exit(exit_code)
        else:
            sys.exit(exit_code)


@tcc.command()
@click.option("--force", "-y", is_flag=True, help="Confirm reset without prompting")
@click.pass_context
def reset(ctx, force: bool):
    """
    Reset TCC configuration to defaults.

    Example usage:
        tch tcc reset

    :param ctx: Click context object
    :raises TCCConfigError: If configuration reset fails
    """
    logger.info("Resetting TCC configuration back to system defaults...")
    app_config = ctx.obj.get("app_config")

    result = False
    try:
        orch = Orchestrator(app_config=app_config)

        # Confirm before resetting
        if not force and not click.confirm(
            "Are you sure you want to reset TCC configuration to defaults?"
        ):
            click.echo("Operation cancelled")
            return

        req = ServiceRequest(
            command=ServiceCommand.RESET,
            service_type=ServiceType.TCC,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise TCCConfigError(svc_result.errors[0] if svc_result.errors else "Reset failed")

        result = True
        exit_code = TchExitCode.SUCCESS

    except TCCConfigError as e:
        logger.error(f"Failed to reset configuration: {e}")
        click.echo("✗ Failed to reset configuration (see logs for details)", err=True)
        exit_code = TchExitCode.USER_INPUT_ERROR

    except Exception:
        logger.exception("Unexpected error resetting configuration")
        click.echo("✗ Unexpected error resetting configuration", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        if result:
            click.echo("✓ Configuration reset successfully")
            sys.exit(exit_code)
        else:
            sys.exit(exit_code)


@tcc.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Show commands without executing")
@click.pass_context
def apply(ctx, config_file: str, dry_run: bool):
    """
    Apply TCC configuration from XML/YAML file.

    Example usage:
        tch tcc apply /path/to/config.yaml --dry-run
        tch tcc apply /path/to/config.xml

    :param ctx: Click context object
    :param str config_file: Path to configuration file
    :param bool dry_run: Show commands without executing
    :raises TCCConfigError: If configuration application fails
    """
    logger.info(f"Applying configuration from file: {config_file}")
    app_config = ctx.obj.get("app_config")

    result = False

    try:
        orch = Orchestrator(app_config=app_config)

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
            raise TCCConfigError(svc_result.errors[0] if svc_result.errors else "Apply failed")
        result = True
        exit_code = TchExitCode.SUCCESS

    except TCCConfigError as e:
        logger.error(f"Failed to apply configuration: {e}")
        click.echo("✗ Failed to apply configuration (see logs for details)", err=True)
        exit_code = TchExitCode.USER_INPUT_ERROR

    except Exception:
        logger.exception("Unexpected error applying configuration")
        click.echo("✗ Unexpected error applying configuration", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        if result:
            click.echo("✓ Configuration applied successfully")
            sys.exit(exit_code)
        else:
            sys.exit(exit_code)


@tcc.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.pass_context
def validate(ctx, config_file: str):
    """
    Validate TCC configuration file.

    Example usage:
        tch tcc validate /path/to/config.xml

    :param ctx: Click context object
    :param str config_file: Path to configuration file to validate
    """
    logger.info("Validating TCC configuration file...")
    app_config = ctx.obj.get("app_config")

    orch = Orchestrator(app_config=app_config)
    exit_code = TchExitCode.SUCCESS

    try:
        req = ServiceRequest(
            command=ServiceCommand.VALIDATE,
            service_type=ServiceType.TCC,
            config_path=config_file,
        )
        svc_result = orch.execute(req)
        if not svc_result.success:
            raise TCCConfigError(svc_result.errors[0] if svc_result.errors else f"Configuration file {config_file} is invalid")

        logger.info(f"Configuration file {config_file} is valid")
        click.echo("✓ Configuration validated successfully\n")
        exit_code = TchExitCode.SUCCESS

    except TCCConfigError as exc:
        logger.error("Configuration validation failed")
        click.echo(f"✗ Validation failed: {exc}", err=True)
        exit_code = TchExitCode.USER_INPUT_ERROR

    except Exception as exc:  # surface any parsing/validation errors
        logger.exception("Configuration validation failed")
        click.echo(f"✗ Validation failed: {exc}", err=True)
        exit_code = TchExitCode.UNEXPECTED_ERROR

    finally:
        sys.exit(exit_code)


#[HEAMINGS FOR TESTING ONLY] Orchestrator command implementation with topology and test configuration options, sending request to Orchestrator daemon via IPC
#------------------------------------------------------------------------------
# Orchestrator Command Implementation
#   1) Accepts topology setup (either via config file or CLI flags),
#      test configuration, and orchestration configuration.
#   2) Handles user input validation and error handling for the
#      orchestration request.
#   3) Sends the orchestration request to the Orchestrator daemon via
#      the defined IPC mechanism (e.g. Unix socket).
#   4) Provides feedback to the user on the status of their
#      orchestration request (e.g. accepted, validation errors, etc.)
#------------------------------------------------------------------------------
@cli.command()
# --- Topology: Config file ---
@click.option(
    "--topology-setup-config",
    type=click.Path(exists=True),
    help="YAML file with talker/listener topology and SSH credentials",
)
# --- Topology: CLI flags (B2B with integrated Host) ---
@click.option("--talker", default=None, help="Talker IP address")
@click.option("--talker-user", default="root", show_default=True, help="Talker SSH user")
@click.option("--talker-password", default="demo123", help="Talker SSH password")
@click.option("--talker-port", default=22, type=int, show_default=True, help="Talker SSH port")
@click.option("--listeners", multiple=True, help="Listener IP address(es), repeatable")
@click.option("--listeners-user", default="root", show_default=True, help="Listeners SSH user")
@click.option("--listeners-password", default="demo123", help="Listeners SSH password")
@click.option("--listeners-port", default=22, type=int, show_default=True, help="Listeners SSH port")

# --- Orchestrator: Test Configuration ---
@click.option("--tcc-config", type=click.Path(exists=True), required=False, help="Path to TCC config XML file")
@click.option("--tsn-config", type=click.Path(exists=True), required=False, help="Path to TSN config XML file")
@click.option("--test-duration", type=int, default=None, help="Test duration in seconds")
@click.option("--timeout", type=int, default=None, help="Max wait time before aborting (seconds)")
@click.option(
    "--orchestration-config",
    type=click.Path(exists=True),
    default=None,
    help="YAML file describing workload, benchmark, and stage selections",
)
# --- Orchestrator: Stage selection flags ---
@click.option("--install", "stage_install", is_flag=True, default=False, help="Run the install stage")
@click.option("--apply-config", "stage_apply_config", is_flag=True, default=False, help="Run the apply_config stage")
@click.option("--run", "stage_run", is_flag=True, default=False, help="Run the run stage")
@click.option("--results", "stage_results", is_flag=True, default=False, help="Run the results stage")
# --- Orchestrator: Option flags ---
@click.option("--dry-run", is_flag=True, help="Show orchestration plan without executing")
@click.option("--verbose", is_flag=True, help="Enable verbose logging")
@click.option("--logfile", type=click.Path(), default=None, help="Path to orchestration log file")
@click.pass_context
def orchestrate(
    ctx,
    topology_setup_config,
    talker, talker_user, talker_password, talker_port,
    listeners, listeners_user, listeners_password, listeners_port,
    tcc_config, tsn_config, test_duration, timeout,
    orchestration_config,
    stage_install, stage_apply_config, stage_run, stage_results,
    dry_run, verbose, logfile,
):
    """
    Run an orchestrated TIME deployment across one or more targets.

    Topology can be specified via a YAML config file (--topology-setup-config)
    or via CLI flags (--talker / --listeners) for simple B2B with integrated Host setup.

    Examples:
        # LOCAL: no topology flags (runs on this machine)
        cmd> tch orchestrate --tcc-config tcc.xml --tsn-config tsn.xml

        # B2B: Host on Talker, one Listener
        cmd> tch orchestrate --tcc-config tcc.xml --tsn-config tsn.xml \\
            --talker 192.168.1.10 --listeners 192.168.1.20

        # B2B via config file
        cmd> tch orchestrate --tcc-config tcc.xml --tsn-config tsn.xml \\
            --topology-setup-config topology.yaml

        # Dry run with orchestration config
        cmd> tch orchestrate --tcc-config tcc.xml --tsn-config tsn.xml \\
            --talker 192.168.1.10 --listeners 192.168.1.20 \\
            --orchestration-config orch.yaml --dry-run

    :param ctx: Click context object
    :param Optional[str] topology_setup_config: Path to YAML file defining topology and SSH credentials
    :param Optional[str] talker: Talker IP address (for CLI topology)
    :param Optional[str] talker_user: Talker SSH username (for CLI topology)
    :param Optional[str] talker_password: Talker SSH password (for CLI topology)
    :param int talker_port: Talker SSH port (for CLI topology)
    :param Optional[Tuple[str]] listeners: Listener IP addresses (for CLI topology)
    :param Optional[str] listeners_user: Listeners SSH username (for CLI topology)
    :param Optional[str] listeners_password: Listeners SSH password (for CLI topology)
    :param int listeners_port: Listeners SSH port (for CLI topology)
    :param str tcc_config: Path to TCC config XML file
    :param str tsn_config: Path to TSN config XML file
    :param Optional[int] test_duration: Expected test duration in seconds (for progress reporting)
    :param Optional[int] timeout: Max wait time before aborting in seconds (for timeout handling)
    :param Optional[str] orchestration_config: Path to YAML file defining workload, benchmark, and stage selections
    :param bool stage_install: If true, include the install stage
    :param bool stage_apply_config: If true, include the apply_config stage
    :param bool stage_run: If true, include the run stage
    :param bool stage_results: If true, include the results stage
    :param bool dry_run: If true, show orchestration plan without executing
    :param bool verbose: If true, enable verbose logging
    :param Optional[str] logfile: If set, path to log file for orchestration logs
    """

    # Setup logging based on user flags
    if verbose:
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.setLevel(logging.DEBUG)
    if logfile:
        log_fh = logging.FileHandler(logfile)
        log_fh.setLevel(logging.DEBUG)
        log_fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logging.getLogger().addHandler(log_fh)

    # Conflict Check: cannot use topology config file with CLI topology flags.
    # Rationale: Assumption is dangerous that user will mix methods.
    #           For simplicity and to avoid confusion, only one method shall be used to define topology.
    has_cli_topology = talker or listeners
    if topology_setup_config and has_cli_topology:
        click.echo(
            "✗ Cannot use --topology-setup-config together with --talker/--listeners flags",
            err=True,
        )
        sys.exit(TchExitCode.USER_INPUT_ERROR)

    # 1. Setup targets and topology type based on user input method
    targets = []
    topology_type = DeploymentTopologyType.SINGLE_LOCAL

    if topology_setup_config:
        # Method 1: YAML config file
        targets, topology_type = _parse_topology_config(topology_setup_config)

    elif has_cli_topology:
        # Method 2: CLI flags → B2B
        if not talker:
            click.echo("✗ --talker is required when using --listeners", err=True)
            sys.exit(TchExitCode.USER_INPUT_ERROR)
        if not listeners:
            click.echo("✗ --listeners is required when using --talker", err=True)
            sys.exit(TchExitCode.USER_INPUT_ERROR)

        targets.append(Target(
            id="talker",
            ip_address=talker,
            ssh_user=talker_user,
            ssh_password=talker_password,
            ssh_port=talker_port,
        ))
        for i, lip in enumerate(listeners):
            targets.append(Target(
                id=f"listener-{i + 1}",
                ip_address=lip,
                ssh_user=listeners_user,
                ssh_password=listeners_password,
                ssh_port=listeners_port,
            ))

        if len(listeners) == 1:
            topology_type = DeploymentTopologyType.B2B
            logger.info("Configured 1 talker and 1 listener → using B2B topology")
        else:
            topology_type = DeploymentTopologyType.MULTI_DUT
            logger.info(f"Configured 1 talker and {len(listeners)} listeners → using B2B topology with multiple listeners")

    else:
        # No topology flags → LOCAL
        targets.append(Target(id="local", ip_address="127.0.0.1"))
        topology_type = DeploymentTopologyType.SINGLE_LOCAL

    # 2. Parse orchestration config (stages, workload, benchmark)

    # ORCHESTRATION STAGES PIPELINE:
    #   1) validate_request: validate user input and config files (topology, TCC, TSN, orchestration)
    #   2) setup: prepare environment on DUTs (e.g. install dependencies, copy files)
    #   3) config: apply TCC and TSN configurations
    #   4) workflow: execute defined workflow (e.g. run tests, collect data)
    #   5) test: run post-configuration tests (e.g. connectivity, performance checks)
    #   6) teardown: clean up environment on DUTs (e.g. remove files, uninstall dependencies, reset configs)
    all_stages = list(WORKFLOW_STAGES)
    valid_stages = set(all_stages)

    # Stage flags take precedence: build ordered list from flags (preserving ORCHESTRATION_STAGES order)
    _flag_map = {
        "install": stage_install,
        "apply_config": stage_apply_config,
        "run": stage_run,
        "results": stage_results,
    }
    _selected_flags = [s for s in WORKFLOW_STAGES if _flag_map.get(s)]

    stages_to_run = []
    if _selected_flags:
        stages_to_run = _selected_flags
    elif orchestration_config:
        try:
            with open(orchestration_config, "r") as f:
                orch_data = yaml.safe_load(f) or {}
        except OSError as e:
            click.echo(f"✗ Cannot open orchestration config '{orchestration_config}': {e}", err=True)
            sys.exit(TchExitCode.USER_INPUT_ERROR)
        except yaml.YAMLError as e:
            click.echo(f"✗ Invalid YAML in orchestration config '{orchestration_config}': {e}", err=True)
            sys.exit(TchExitCode.USER_INPUT_ERROR)
        stages_to_run = orch_data.get("stages", [])

        # TODO: User configurable plugins
        # workload = orch_data.get("workload", "AI Workload")
        # benchmark = orch_data.get("benchmark", "RTC Test Bench")

        invalid = set(stages_to_run) - valid_stages
        if invalid:
            click.echo(
                f"✗ Invalid stage(s): {', '.join(sorted(invalid))}. "
                f"Valid stages: {', '.join(all_stages)}",
                err=True,
            )
            sys.exit(TchExitCode.USER_INPUT_ERROR)
    else:
        stages_to_run = all_stages  # default to all stages if no flags or orchestration config provided

    click.echo(f">>>Orchestration stages to run: {', '.join(stages_to_run)}")
    # 3. Validate TCC and TSN config files (click.Path(exists=True) already ensures they exist)
    app_config = ctx.obj.get("app_config")
    orch = Orchestrator(app_config=app_config)
    try:
        if tcc_config:
            tcc_req = ServiceRequest(command=ServiceCommand.VALIDATE, service_type=ServiceType.TCC, config_path=tcc_config)
            if not orch.execute(tcc_req).success:
                click.echo(f"✗ TCC config file '{tcc_config}' is invalid", err=True)
                # TEMP-BYPASS: since TCC config validation is not fully implemented,
                # we will log the error but allow orchestration to proceed for now.
                #sys.exit(TchExitCode.USER_INPUT_ERROR)
        if tsn_config:
            tsn_req = ServiceRequest(command=ServiceCommand.VALIDATE, service_type=ServiceType.TSN, config_path=tsn_config)
            if not orch.execute(tsn_req).success:
                click.echo(f"✗ TSN config file '{tsn_config}' is invalid", err=True)
                # TEMP-BYPASS: since TSN config validation is not fully implemented,
                # we will log the error but allow orchestration to proceed for now.
                #sys.exit(TchExitCode.USER_INPUT_ERROR)
    except TSNConfigError as e:
        click.echo(f"✗ Config validation failed: {e}", err=True)
        sys.exit(TchExitCode.USER_INPUT_ERROR)

    # 4. Build OrchestratorConfig
    orchestrator_request_config = OrchestratorConfig(
        topology_type=topology_type,
        targets=targets,
        tcc_config=tcc_config,
        tsn_config=tsn_config,
        stages_to_run=stages_to_run,
        dry_run=dry_run,
        test_duration=test_duration,
        timeout=timeout,
    )

    # Show orchestration plan summary
    click.echo("\nOrchestration Plan Summary")
    click.echo("=" * 40)
    click.echo(f"Topology               : {topology_type.value}")
    click.echo(f"Targets                : {len(targets)}")
    for t in targets:
        click.echo(f"  [{t.id}] {t.ip_address}:{t.ssh_port}")
    click.echo(f"Orchestration Stages   : {', '.join(stages_to_run)}")
    click.echo(f"TCC                    : {tcc_config}")
    click.echo(f"TSN                    : {tsn_config}")
    if test_duration:
        click.echo(f"Duration               : {test_duration}s")
    if timeout:
        click.echo(f"Timeout                : {timeout}s")
    if dry_run:
        click.echo("DRY RUN Mode           : No changes will be applied")
    click.echo("=" * 40)
    click.echo("")

    if dry_run:
        click.echo("✓ Dry run complete — no actions were executed")
        sys.exit(TchExitCode.SUCCESS)

    logger.info(
        "Sending orchestration request: topology=%s, targets=%d",
        topology_type.value, len(targets),
    )

    # Send request to orchestrator daemon
    try:
        result = send_orchestration_request(orchestrator_request_config)
        if result is None:
            click.echo(
                "✗ Orchestration failed: no response received from orchestrator daemon",
                err=True,
            )
            sys.exit(TchExitCode.UNEXPECTED_ERROR)

        for line in result.logs:
            click.echo(f"  {line}")

        if result.success:
            click.echo("\n✓ Orchestration completed successfully")
            sys.exit(TchExitCode.SUCCESS)
        else:
            if result.errors:
                for err in result.errors:
                    click.echo(f"✗ {err}", err=True)
            click.echo("\n✗ Orchestration failed", err=True)
            sys.exit(TchExitCode.UNEXPECTED_ERROR)

    except ConnectionRefusedError:
        click.echo(
            "✗ Could not connect to Orchestrator daemon. Is tch.service running?",
            err=True,
        )
        sys.exit(TchExitCode.UNEXPECTED_ERROR)

    except Exception:
        logger.exception("Unexpected error during orchestration")
        click.echo("✗ Unexpected error during orchestration", err=True)
        sys.exit(TchExitCode.UNEXPECTED_ERROR)


def _parse_topology_config(config_path: str) -> tuple[list[Target], DeploymentTopologyType]:
    """
    Parse a topology YAML file and return (targets, topology_type).

    Example topology YAML structure:
        defaults:
            ssh_user: user
            ssh_password: user123
            ssh_port: 22
        talker:
            ip: 192.168.1.10    # required
            ssh_user: root
            ssh_password: talker123
        listeners:
            ip: 192.168.1.20    # required, can be a list for multiple listeners
            ssh_user: root
            ssh_password: listener123

    :param config_path: Path to the topology YAML file
    :raises TSNConfigError: If the file cannot be opened or is empty/invalid
    """

    try:
        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
    except OSError as e:
        raise TSNConfigError(f"Cannot open topology config '{config_path}': {e}") from e
    except yaml.YAMLError as e:
        raise TSNConfigError(f"Invalid YAML in topology config '{config_path}': {e}") from e

    if not data:
        raise TSNConfigError(f"Topology config '{config_path}' is empty or contains no valid data")

    # Load defaults and apply to targets if user-specific values not provided.
    defaults = data.get("defaults", {})
    def_user = defaults.get("ssh_user", "root")
    def_pass = defaults.get("ssh_password", "demo123")
    def_port = defaults.get("ssh_port", 22)

    targets = []

    # Talker
    talker_data = data.get("talker")
    if talker_data:
        talker_ip = talker_data.get("ip")
        if not talker_ip:
            raise TSNConfigError("Talker entry is missing required 'ip' field")
        targets.append(Target(
            id="talker",
            ip_address=talker_ip,
            ssh_user=talker_data.get("ssh_user", def_user),
            ssh_password=talker_data.get("ssh_password", def_pass),
            ssh_port=talker_data.get("ssh_port", def_port),
        ))

    # Listeners. This is Topology-dependent: single dict or list of dicts
    listeners_data = data.get("listeners", [])
    if isinstance(listeners_data, dict):
        listeners_data = [listeners_data]
    for i, ld in enumerate(listeners_data):
        listener_ip = ld.get("ip")
        if not listener_ip:
            raise TSNConfigError(f"Listener {i + 1} is missing required 'ip' field")
        targets.append(Target(
            id=f"listener-{i + 1}",
            ip_address=listener_ip,
            ssh_user=ld.get("ssh_user", def_user),
            ssh_password=ld.get("ssh_password", def_pass),
            ssh_port=ld.get("ssh_port", def_port),
        ))

    logger.info(f"Parsed topology config: {len(targets)} targets found")
    logger.info(f"Targets: {[t.ip_address for t in targets]}")
    logger.debug(f"Defaults: user={def_user}, port={def_port}")

    # Auto-detect topology type based on roles present
    has_talker = talker_data is not None
    has_listeners = len(listeners_data) > 0

    if not has_talker and not has_listeners:
        topology_type = DeploymentTopologyType.SINGLE_LOCAL
        targets.append(Target(id="local", ip_address="127.0.0.1"))
    elif has_talker and has_listeners:
        topology_type = DeploymentTopologyType.B2B
    else:
        topology_type = DeploymentTopologyType.MULTI_DUT

    return targets, topology_type


def main():
    """
    Entry point for the CLI.

    :return: None
    :rtype: None
    """
    cli()


# Register sub-command groups defined in separate modules
from time_config_hub.cli.perf import perf_group  # noqa: E402
cli.add_command(perf_group)


if __name__ == "__main__":
    main()
