# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
time_config_hub.services.ai_workload — AI workload setup and runtime.

This package covers two distinct phases, both exposed through the single
:class:`AIWorkload` class.  One instance is created per DUT target by the
orchestrator.

Setup phase (async)
-------------------
:meth:`AIWorkload.install`              : Spawn install thread (venv, pip, model export).
:meth:`AIWorkload.get_install_progress` : Step-level progress snapshot; poll anytime.
:meth:`AIWorkload.cancel_install`       : Signal install thread to stop.

Runtime phase (async benchmark, sync log collection)
-----------------------------------------------------
:meth:`AIWorkload.start`                : Verify env then start benchmark asynchronously.
:meth:`AIWorkload.get_run_progress`     : Live benchmark metrics snapshot.
:meth:`AIWorkload.stop`                 : Stop the running benchmark.
:meth:`AIWorkload.collect_logs`         : Retrieve benchmark report JSON.

Supporting public API
---------------------
AIWorkloadMaxRetriesError : Raised by the benchmark loop; catch via get_run_progress().
SETUP_TASK_NAMES          : Ordered list of setup step label strings.
BENCHMARK_SAMPLE_INTERVAL_S : Metrics sampling interval (informational).
"""

from .runner import (
    BENCHMARK_SAMPLE_INTERVAL_S,
    AIWorkloadMaxRetriesError,
)
from .service import AIWorkload
from .setup import SETUP_TASK_NAMES

__all__ = [
    "AIWorkload",
    "AIWorkloadMaxRetriesError",
    "SETUP_TASK_NAMES",
    "BENCHMARK_SAMPLE_INTERVAL_S",
]
