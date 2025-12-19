"""
Service management utilities for Time Config Hub daemon.

This module provides functions and classes to deploy, start, stop, restart,
and check the status of the Time Config Hub systemd service. It handles
service file deployment, systemd interactions, and error management.
"""

import logging
import shutil
import subprocess
from importlib import resources

from .definitions import TCH_DAEMON_SERVICE_FILE
from .exceptions import ServiceError

logger = logging.getLogger(__name__)

SERVICE_NAME = "tch.service"


def _run_systemctl(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a systemctl command and raise ServiceError on failure.

    :param list[str] args: Arguments to pass to ``systemctl``.
    :return: Completed process result.
    :rtype: subprocess.CompletedProcess[str]
    :raises ServiceError:
        If ``systemctl`` is not found or the command returns a non-zero exit code.
    """
    cmd = ["systemctl", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        # Handles missing `systemctl` command
        logger.error("systemctl command not found. This command requires systemd.")
        raise ServiceError("systemctl command not found") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        if stderr:
            logger.error(f"systemctl failed ({' '.join(cmd)}): {stderr}")
        else:
            logger.error(
                f"systemctl failed ({' '.join(cmd)}) with exit code {result.returncode}"
            )
        raise ServiceError(f"systemctl failed: {' '.join(cmd)}")

    return result


def setup_service_file():
    """
    Deploy the systemd service file for the Time Config Hub daemon and
    reload systemd.

    This function locates the service file within the package resources,
    copies it to the systemd directory, and reloads the systemd daemon to
    register the service. Handles permission errors and unexpected exceptions,
    raising ServiceError on failure.

    :raises ServiceError: If deployment fails due to permission or other errors.
    """
    logger.debug("Setting up systemd service file...")
    try:
        # Locate the service file inside your package
        src = resources.files("time_config_hub.templates") / SERVICE_NAME

        # Destination path
        dst = TCH_DAEMON_SERVICE_FILE

        # Copy the tch.service file to /etc/systemd/system/tch.service
        shutil.copy(str(src), dst)

        _run_systemctl(["daemon-reload"])
        logger.debug(
            f"Deployed systemd service file successfully: {TCH_DAEMON_SERVICE_FILE}"
        )

    except (OSError, PermissionError) as e:
        logger.error("Failed to deploy service file due to permission error")
        raise ServiceError(
            "Failed to deploy service file due to permission error"
        ) from e

    except Exception as e:
        logger.exception("Unexpected error deploying service file")
        raise ServiceError("Unexpected error deploying service file") from e


class ServiceManager:
    """
    Manage the Time Config Hub systemd service lifecycle.

    Provides methods to start, stop, restart, and check the status of the
    Time Config Hub daemon service. Handles deployment of the service file,
    systemd interactions, and error management.
    """

    def start_service(self):
        """
        Deploy, enable, and start the Time Config Hub systemd service.

        This method sets up the service file, enables the service for auto-start,
        and starts the service using systemd. It checks the service status after
        starting and raises ServiceError if any step fails.

        :raises ServiceError: If enabling or starting the service fails,
            or if systemctl is not found.
        """
        logger.debug("Starting service...")

        # Setup service file
        setup_service_file()

        # Enable service for auto-start
        _run_systemctl(["enable", "--now", SERVICE_NAME])

        status = self.get_service_status()
        if status != "active":
            logger.error(f"Failed to enable service: {status}")
            raise ServiceError("Service failed to enable")

        logger.debug("Service started successfully")

    def stop_service(self):
        """
        Stops the 'tch.service' systemd service.

        Attempts to stop the service using 'systemctl stop'. If the stop command fails,
        logs the error and raises a ServiceError. After stopping, checks the service
        service status to ensure it is inactive; if not, raises a ServiceError.
        Handles exceptions for command failures and missing 'systemctl' command.

        Raises:
            ServiceError: If the service fails to stop or is not inactive
                after stopping, or if 'systemctl' is not found.
            subprocess.CalledProcessError: If a subprocess command fails unexpectedly.
        """
        logger.debug("Stopping service...")

        _run_systemctl(["stop", SERVICE_NAME])

        status = self.get_service_status()
        if status != "inactive":
            logger.error(f"Service not inactive after stop: {status}")
            raise ServiceError("Service failed to stop properly")

        logger.debug("Service stopped successfully")

    def restart_service(self):
        """
        Restarts the 'tch.service' systemd service.

        Attempts to restart the service using 'systemctl'. If the restart fails or
        the service does not become active, logs the error and raises a ServiceError.
        Handles cases where 'systemctl' is not found or the command fails.

        Raises:
            ServiceError: If the service fails to restart or is not active
                after restart, or if 'systemctl' is not found.
            subprocess.CalledProcessError: If a subprocess command fails unexpectedly.
        """
        logger.debug("Restarting service...")

        _run_systemctl(["restart", SERVICE_NAME])

        status = self.get_service_status()
        if status != "active":
            logger.error(f"Service not active after restart: {status}")
            raise ServiceError("Service failed to restart properly")

        logger.debug("Service restarted successfully")

    def get_service_status(self) -> str:
        """Get the raw systemd status for ``tch.service``.

        This returns only the status token from ``systemctl is-active``, such as
        ``active``, ``inactive``, ``failed``, or ``unknown``.

        :return: Service status token.
        :rtype: str
        :raises ServiceError: If the systemctl command is not found on the system.
        """
        logger.debug("Getting service status...")
        try:
            # Note: `systemctl is-active` returns non-zero for inactive/failed,
            # so do not treat non-zero as an error here.
            result = subprocess.run(
                ["systemctl", "is-active", SERVICE_NAME],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            # Handles missing `systemctl` command
            logger.error("systemctl command not found. This command requires systemd.")
            raise ServiceError("systemctl command not found") from exc

        status = (result.stdout or "").strip()
        logger.debug(f"Service status retrieved: {status}")
        return status
