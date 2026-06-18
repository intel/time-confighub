# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
libs.common.status_codes — unified status codes shared across all TCH libs.

All public lib functions return a dict keyed on ``status_code`` (an int from
this enum), ``output`` (captured stdout/stderr), ``error`` (human-readable
failure message, empty on success), and ``data`` (payload or None).
"""

from enum import IntEnum


class TchStatusCode(IntEnum):
    """Unified status codes for all TCH lib functions.

    :cvar SUCCESS: Operation completed successfully.
    :cvar ERROR: Unexpected / general error.
    :cvar PERMISSION_DENIED: Insufficient permissions (e.g. root required).
    :cvar USER_INPUT_ERROR: Invalid parameters or arguments.
    :cvar NOT_FOUND: Resource not found (profile, file, interface, service).
    :cvar TIMEOUT: Operation timed out.
    :cvar ALREADY_RUNNING: Process or service is already running.
    :cvar NOT_RUNNING: Process or service is not running (expected to be).
    :cvar REMOTE_ERROR: SSH / remote dispatch failure.
    :cvar PARTIAL_FAILURE: Composite operation where some sub-steps failed.
    """

    SUCCESS = 0
    ERROR = 1
    PERMISSION_DENIED = 2
    USER_INPUT_ERROR = 3
    NOT_FOUND = 4
    TIMEOUT = 5
    ALREADY_RUNNING = 6
    NOT_RUNNING = 7
    REMOTE_ERROR = 8
    PARTIAL_FAILURE = 9
