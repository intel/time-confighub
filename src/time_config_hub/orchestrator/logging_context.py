# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Orchestrator Worker Utilities

Provides role-aware log filtering and timestamping utilities shared
across orchestrator threads.

The utility functions :func:`now_ms` and :func:`timestamp` are imported
by ``orchestrator.py`` for consistent timestamping.  :func:`set_role_log_context`
and the :class:`_RoleFilter` tag concurrent step threads with their target
role so log records from any service logger are identifiable per-thread.
"""

import logging
import threading
import time
from datetime import datetime, timezone

from .models import Target

__all__ = ["now_ms", "timestamp", "set_role_log_context"]

logger = logging.getLogger("orchestrator.logging_context")


# ======================================================================
# Role-aware logging — thread-local context + filter
# ======================================================================
#
# Problem: in multi-DUT runs, talker and listener threads emit log records
# concurrently.  Service-layer loggers (time_config_hub.services.*) have no
# knowledge of topology, so their records carry no role or target context.
#
# Solution: a single _RoleFilter is installed on both orchestrator and
# time_config_hub logger namespaces at module import time.  Each worker /
# step thread calls set_role_log_context(target) at its entry point, which
# stores a role prefix in threading.local().  The filter prepends that
# prefix to every log record emitted on that thread, regardless of which
# logger or service file produced it.
#
# Example output:
#   [talker/dut-1] STAGE START  start_ptp[dut-1/talker]
#   [listener/dut-2] STAGE START  start_ptp[dut-2/listener]
#   [listener/dut-2] [ptp] ptp4l slave started on 'dut-2'
#   [talker/dut-1] [ptp] ptp4l GM started on 'dut-1'
#   [listener/dut-2] STAGE DONE   start_ptp[dut-2/listener]  elapsed=0.501s
#   [talker/dut-1] STAGE DONE   start_ptp[dut-1/talker]  elapsed=0.612s

_role_ctx: threading.local = threading.local()


class _RoleFilter(logging.Filter):
    """Prepend the thread-local role prefix to every log record on this thread.

    Prepending directly to ``record.msg`` (the format string) works correctly
    with %-style format args: ``record.msg = "[role/id] " + record.msg`` still
    formats with the original ``record.args`` on the handler side.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        prefix = getattr(_role_ctx, "prefix", "")
        if prefix:
            record.msg = f"{prefix} {record.msg}"
        return True


def _install_role_filter() -> None:
    """Install the role filter on orchestrator and service loggers (idempotent)."""
    _f = _RoleFilter()
    for name in ("orchestrator", "time_config_hub"):
        lg = logging.getLogger(name)
        # Guard against duplicate installation if module is re-imported
        if not any(isinstance(f, _RoleFilter) for f in lg.filters):
            lg.addFilter(_f)


# ------------------------------------------------------------------
# Helpers for log context and timestamping
# -----------------------------------------------------------------

def set_role_log_context(target: Target) -> None:
    """Set the thread-local role prefix for the calling thread.

    Must be called at the entry point of every worker thread and step
    thread before any logging is performed.  Subsequent log records
    emitted on the same thread will be prefixed with ``[role/target_id]``.

    :param target: The DUT target assigned to this thread.
    """
    role = target.role or "local"
    _role_ctx.prefix = f"[{role}/{target.id}]"


def now_ms() -> int:
    return int(time.monotonic() * 1000)


def timestamp() -> str:
    """Return a UTC timestamp string in HH:MM:SS.mmm format."""
    now = datetime.now(timezone.utc)
    return now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"


# ------------------------------------------------------------------
# Install at import time so the filter is active before any orchestrator
# thread starts emitting log records.  set_role_log_context() is a no-op
# until called per-thread, but the filter must be registered first.
# -----------------------------------------------------------------

_install_role_filter()
