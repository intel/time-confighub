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
from typing import Optional

import click
import yaml

from . import __version__
from .config_reader import load_app_config
from .time_hub_service import TimeHubService
from .exceptions import TCCConfigError, TSNConfigError
from .exit_codes import TchExitCode
from .logging_setup import setup_logging

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
        config_hub = TimeHubService(app_config)
        service_status = config_hub.service_manager.get_service_status()

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
        config_hub = TimeHubService(app_config)

        # Avoid restarting if already running
        service_status = config_hub.service_manager.get_service_status()
        if service_status == "active":
            outcome_message = "✓ Daemon is already running"
            result = True
            exit_code = TchExitCode.SUCCESS
            return

        config_hub.service_manager.start_service()
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
        config_hub = TimeHubService(app_config)

        service_status = config_hub.service_manager.get_service_status()
        if service_status != "active":
            outcome_message = "✓ Daemon is not running"
            result = True
            exit_code = TchExitCode.SUCCESS
            return

        config_hub.service_manager.stop_service()
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
        config_hub = TimeHubService(app_config)
        config_hub.service_manager.restart_service()
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

    result = False

    try:
        # ConfigDirectory from config file points to TSN traffic config directory
        config_hub = TimeHubService(app_config)

        if interface:
            click.echo(f"Target interface: {interface}")

        if dry_run:
            click.echo("DRY RUN MODE - No changes will be applied")

        config_hub.apply_config(config_file, dry_run=dry_run)
        result = True
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
        if result:
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

        # ConfigDirectory from config file points to TSN traffic config directory
        config_hub = TimeHubService(app_config)

        status_info = config_hub.get_status(interface=interface)

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

        # ConfigDirectory from config file points to TSN traffic config directory
        config_hub = TimeHubService(app_config)
        config_hub.reset_config(interface=interface)
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

    # ConfigDirectory from config file points to TSN traffic config directory
    config_hub = TimeHubService(app_config)
    exit_code = TchExitCode.SUCCESS

    try:    
        if not config_hub.validate_config(config_file):
            raise TSNConfigError(f"Configuration file {config_file} is invalid")

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
        config_hub = TimeHubService(app_config)

        status_info = config_hub.get_tcc_status()

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
        config_hub = TimeHubService(app_config)

        # Confirm before resetting
        if not force and not click.confirm(
            "Are you sure you want to reset TCC configuration to defaults?"
        ):
            click.echo("Operation cancelled")
            return

        config_hub.reset_tcc_config()

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
        # ConfigDirectory from config file points to TSN traffic config directory
        config_hub = TimeHubService(app_config)

        if dry_run:
            click.echo("DRY RUN MODE - No changes will be applied")

        config_hub.apply_tcc_config(config_file, dry_run=dry_run)
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

    # ConfigDirectory from config file points to TSN traffic config directory
    config_hub = TimeHubService(app_config)
    exit_code = TchExitCode.SUCCESS

    try:
        if not config_hub.validate_tcc_config(config_file):
            raise TCCConfigError(f"Configuration file {config_file} is invalid")

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


def main():
    """
    Entry point for the CLI.

    :return: None
    :rtype: None
    """
    cli()


if __name__ == "__main__":
    main()
