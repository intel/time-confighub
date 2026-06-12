# SPDX-FileCopyrightText: 2025 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
system_controller.target — remote-host connection parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Target:
    """SSH connection parameters for a remote DUT.

    A ``Target`` always represents a **remote** host.  Pass ``target=None``
    (the default throughout the system_controller API) to run on localhost.

    :param str host: Hostname or IP address of the remote host.
    :param str user: SSH username.
    :param int port: SSH port (default 22).
    :param str remote_dir: Working/base directory on the remote host.
    :param password: SSH password — used **only** during the one-time
        :func:`~system_controller.key_exchange.ensure_key_auth` exchange.
        Never stored on disk.
    :type password: str or None
    """

    host: str
    user: str
    port: int = 22
    remote_dir: str = "/opt/tch"
    password: Optional[str] = field(default=None, repr=False)

    @property
    def identity(self) -> str:
        """Unique string identifier for this target: ``user@host``.

        :return: SSH target identity string.
        :rtype: str
        """
        return f"{self.user}@{self.host}"
