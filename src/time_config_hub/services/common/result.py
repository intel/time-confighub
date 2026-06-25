# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
time_config_hub.services.common.result — unified return type for all TCH services.

Enforces consistent return types and keys across all services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from time_config_hub.utils.common.status_codes import TchStatusCode


@dataclass
class ServiceResult:
    """Unified return type for all TCH service public methods.

    :param TchStatusCode status_code: The status code of the operation.
    :param str output: Human-readable output or captured stdout.
    :param str error: Human-readable failure message; empty on success.
    :param Any data: Optional payload returned by the operation.
    """

    status_code: TchStatusCode
    output: str = ""
    error: str = ""
    data: Any = field(default=None)

    @property
    def success(self) -> bool:
        """Return ``True`` if the operation completed successfully.

        :return: True when ``status_code`` is :attr:`TchStatusCode.SUCCESS`.
        :rtype: bool
        """
        return self.status_code == TchStatusCode.SUCCESS
