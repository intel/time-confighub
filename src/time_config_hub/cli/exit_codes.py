# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""Exit codes used by the Time Config Hub CLI."""

from enum import IntEnum


class TchExitCode(IntEnum):
    """Enumerated exit codes for CLI commands.

    - SUCCESS: apply success
    - UNEXPECTED_ERROR: unexpected error handled by tch
    - INVALID_COMMAND_OR_PERMISSION: invalid command or permission issue (not a tch error)
    - USER_INPUT_ERROR: user input error (not a tch error)
    """

    SUCCESS = 0
    UNEXPECTED_ERROR = 1
    INVALID_COMMAND_OR_PERMISSION = 2
    USER_INPUT_ERROR = 3
