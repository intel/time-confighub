"""
Exception classes for Time Config Hub.

This module defines all custom exceptions used throughout the Time Config Hub.

The exception hierarchy is:

- TSNConfigError: Base exception for all TSN-related errors
  - ConfigParseError: Configuration file parsing failures
  - TCCommandError: Traffic control command execution failures
  - InterfaceError: Network interface operation failures
  - ValidationError: Configuration validation failures

All exceptions inherit from TSNConfigError to allow for broad exception handling
while still providing specific error types for detailed error handling.
"""


class TSNConfigError(Exception):
    """
    Base exception for TSN configuration errors.

    All other TSN-related exceptions inherit from this base class.
    """

    pass


class ServiceError(TSNConfigError):
    """
    Exception raised for errors related to service management.

    Indicates issues with starting, stopping, or managing the TSN configuration
    daemon service.
    """

    pass


class ConfigParseError(TSNConfigError):
    """
    Exception raised when configuration file parsing fails.

    Indicates that a configuration file could not be parsed due to
    syntax errors or invalid format.
    """

    pass


class TCCommandError(TSNConfigError):
    """
    Exception raised when TC command execution fails.

    Indicates that a traffic control (tc) command failed to execute
    or returned an error status.
    """

    pass


class InterfaceError(TSNConfigError):
    """
    Exception raised when network interface operations fail.

    Indicates problems with network interface detection, validation,
    or configuration.
    """

    pass


class ValidationError(TSNConfigError):
    """
    Exception raised when configuration validation fails.

    Indicates that a configuration file or parameters failed
    validation checks.
    """

    pass
