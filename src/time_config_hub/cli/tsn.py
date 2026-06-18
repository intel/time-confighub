# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
TSN CLI subcommands.

Provides the ``tsn`` Click group and all its subcommands for managing
Time-Sensitive Networking (TSN) configurations.
"""

import json
import logging
import sys
from typing import Optional

import click
import yaml

from time_config_hub.orchestrator.time_hub_service import TimeHubService
from time_config_hub.exceptions import TSNConfigError
from time_config_hub.cli.exit_codes import TchExitCode

logger = logging.getLogger(__name__)


@click.group()
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
