"""Command execution utilities for Time Config Hub.

This module provides the base Command class for executing system commands
with proper error handling and logging. For ethtool-specific operations,
use the EthtoolCommand class from the ethtool module.

Note:
    All commands are executed with proper error handling and logging.
    Failed commands will raise RuntimeError with detailed error information.
"""

import logging
import subprocess

# Configure logging for this module
logger = logging.getLogger(__name__)


class BaseCommand:
    """Base class for executing system commands with error handling and logging.

    This class provides a foundation for executing system commands with proper
    error handling, logging, and return code validation.

    :cvar SUCCESS_CODES: List of return codes considered successful
    :type SUCCESS_CODES: List[int]
    """

    SUCCESS_CODES = [0]

    @classmethod
    def run(
        cls, command: str, check_success: bool = True
    ) -> subprocess.CompletedProcess:
        """Execute a system command with error handling and logging.

        :param str command: Command string to execute
        :param bool check_success: Whether to check return code for success
            (default: True)
        :return: CompletedProcess object with command results
        :rtype: subprocess.CompletedProcess
        :raises ValueError: if command is empty or invalid
        :raises RuntimeError: if command execution fails or returns error code
        """
        TIMEOUT = 30  # seconds
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")

        command = command.strip()
        logger.debug(f"Executing command: {command}")

        try:
            cmd = command.split()
            if not cmd:
                raise ValueError("Invalid command format")

            # Execute the command
            output = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=TIMEOUT,  # Add timeout to prevent hanging
            )
            return_code = output.returncode
            stdout = output.stdout
            stderr = output.stderr

            msg = (
                f"Command completed - Return code: {return_code}:\n"
                f"stdout: {stdout}{'...' if len(stdout) > 500 else ''}\n"
                f"stderr: {stderr}{'...' if len(stderr) > 500 else ''}\n"
            )
            logger.debug(msg)

        except subprocess.TimeoutExpired as e:
            logger.error(f"Command timed out after {TIMEOUT} seconds: {command}")
            raise RuntimeError(f"Command timed out: {command}") from e
        except FileNotFoundError as e:
            logger.error(f"Command not found: {command}")
            raise RuntimeError(f"Command not found: {command}") from e
        except Exception as e:
            logger.error(f"Command execution failed: {command} - {e}")
            raise RuntimeError(f"Command execution failed: {command}") from e

        # Check success if requested
        if check_success and return_code not in cls.SUCCESS_CODES:
            error_msg = (
                f"Command failed with return code {return_code}: {command}\n"
                f"stdout: {stdout}\n"
                f"stderr: {stderr}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.debug(f"Command completed successfully: {command}")
        return output
