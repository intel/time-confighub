# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Exception classes for Time Config Hub.

This module defines all custom exceptions used throughout the Time Config Hub.

The exception hierarchy is:

Exception
|_ TCHConfigError (base for all TCH errors)
    |_ CommonConfigError (base for shared/common configuration concerns)
        |_ ConfigParseError (configuration file parsing failures)
        |_ ValidationError (configuration validation failures)
    |_ TSNConfigError (base for TSN domain errors)
        |_ TCCommandError (traffic control command execution failures)
        |_ InterfaceError (network interface operation failures)
    |_ TCCConfigError (base for TCC domain errors)
    |_ ServiceError (service management errors)

All exceptions inherit from TCHConfigError to allow for broad exception handling
while still providing specific error types for detailed error handling.
"""


class TCHConfigError(Exception):
    """
    Base exception for all Time Config Hub errors.
    All other exceptions in the Time Config Hub should inherit from this base class.
    """
    pass


class CommonConfigError(TCHConfigError):
    """Base exception for shared/common configuration concerns.""" 
    pass


class ConfigParseError(CommonConfigError):
    """
    Exception raised when configuration file parsing fails.

    Indicates that a configuration file could not be parsed due to
    syntax errors or invalid format.
    """
    pass


class ValidationError(CommonConfigError):
    """
    Exception raised when configuration validation fails.

    Indicates that a configuration file or parameters failed
    validation checks.
    """
    pass


class TSNConfigError(TCHConfigError):
    """
    Base exception for TSN domain errors.

    All other TSN-related exceptions inherit from this base class.
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


class ServiceError(TCHConfigError):
    """
    Exception raised for errors related to service management.

    Indicates issues with starting, stopping, or managing the TCH configuration
    daemon service.
    """
    pass


class TCCConfigError(TCHConfigError):
    """
    Base exception for TCC domain errors.

    All other TCC-related exceptions inherit from this base class.
    """
    pass
