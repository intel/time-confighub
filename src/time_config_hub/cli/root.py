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

The CLI supports both interactive and non-interactive usage patterns,
with proper error handling and logging capabilities.
"""

import json
import logging
import os
import sys

import click
import yaml

from time_config_hub import __version__
from time_config_hub.config.config_reader import load_app_config
from time_config_hub.config.logging import setup_logging
from time_config_hub.cli.exit_codes import TchExitCode
from time_config_hub.cli.tcc import tcc
from time_config_hub.cli.tsn import tsn
from time_config_hub.orchestrator.orchestrator import Orchestrator


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
#
# Design Note:
#   System service management commands (start/stop/restart/status) are implemented
#   directly in the CLI through Orchestrator.service_manager rather than through
#   the IPC mechanism to ensure they can be executed even when the daemon
#   is not running (where IPC would fail).
#
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
        orchestrator = Orchestrator(app_config)
        service_status = orchestrator.service_manager.get_service_status()

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
        orchestrator = Orchestrator(app_config)

        # Avoid restarting if already running
        service_status = orchestrator.service_manager.get_service_status()
        if service_status == "active":
            outcome_message = "✓ Daemon is already running"
            result = True
            exit_code = TchExitCode.SUCCESS
            return

        orchestrator.service_manager.start_service()
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
        orchestrator = Orchestrator(app_config)

        service_status = orchestrator.service_manager.get_service_status()
        if service_status != "active":
            outcome_message = "✓ Daemon is not running"
            result = True
            exit_code = TchExitCode.SUCCESS
            return

        orchestrator.service_manager.stop_service()
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
        orchestrator = Orchestrator(app_config)
        orchestrator.service_manager.restart_service()
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
# Register TSN and TCC subcommand groups (defined in tsn.py / tcc.py)
#===============================================================================

cli.add_command(tsn)
cli.add_command(tcc)


def main():
    """
    Entry point for the CLI.

    :return: None
    :rtype: None
    """
    cli()


if __name__ == "__main__":
    main()
