# SPDX-FileCopyrightText: 2025-2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
TCC CLI subcommands.

Provides the ``tcc`` Click group and all its subcommands for managing
Time-Coordinated Computing (TCC) configurations.
"""

import json
import logging
import sys

import click
import yaml

from time_config_hub.orchestrator.time_hub_service import TimeHubService
from time_config_hub.exceptions import TCCConfigError
from time_config_hub.cli.exit_codes import TchExitCode

logger = logging.getLogger(__name__)


@click.group()
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
