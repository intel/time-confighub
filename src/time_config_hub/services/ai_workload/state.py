# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
time_config_hub.services.ai_workload.state — shared state and progress types.

Defines:
- :class:`StepStatus`            : step-level status enum (``pending`` → ``running`` → ``done``/``failed``/``cancelled``).
- :class:`WorkloadState`         : workload state enum (``not_started`` → ``running`` → ``done``/``error``/``cancelled``).
- :class:`StepProgress`          : per-step progress entry (install phase).
- :class:`InstallProgress`       : install progress snapshot from :meth:`AIWorkload.get_install_progress`.
- :class:`BenchmarkProgress`     : run progress snapshot from :meth:`AIWorkload.get_run_progress`.
- :class:`_InstallState`         : mutable install state owned by :class:`~.service.AIWorkload`.
- :class:`_RunState`             : mutable run state owned by :class:`~.runner.AIWorkloadRunner`.

Internal API — not exported from ``ai_workload.__init__``.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import List, Optional


# ── Status enums ──────────────────────────────────────────────────────────────


class StepStatus(str, Enum):
    """Per-step status values for :attr:`StepProgress.status`.

    Using ``str`` as a mixin means enum members compare equal to their string
    values and serialise transparently (e.g. via ``json.dumps``).
    """

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkloadState(str, Enum):
    """Overall workload state values for :attr:`_InstallState.state` and
    :attr:`_InstallState.state` and :attr:`_RunState.state`.

    Using ``str`` as a mixin means enum members compare equal to their string
    values and serialise transparently.

    State transitions:
    - Install phase: ``not_started`` → ``running`` → ``done`` / ``error`` / ``cancelled``
    - Benchmark phase: ``not_started`` → ``running`` → ``done`` / ``error`` / ``cancelled``
    """

    NOT_STARTED = "not_started"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


# ── Public dataclasses (used as ServiceResult.data payloads) ─────────────────


@dataclass
class StepProgress:
    """Step progress entry returned inside :class:`InstallProgress`.

    :param str label: Human-readable step name.
    :param StepStatus status: One of :attr:`StepStatus.PENDING`, :attr:`StepStatus.RUNNING`,
        :attr:`StepStatus.DONE`, :attr:`StepStatus.FAILED`, :attr:`StepStatus.CANCELLED`.
    :param str detail: Short result or error message; empty until the step runs.
    """

    label: str
    status: StepStatus = StepStatus.PENDING
    detail: str = ""

    def to_dict(self) -> dict:
        """Return a plain :class:`dict` representation of this step.

        :return: Dict with ``label``, ``status``, and ``detail`` keys.
        :rtype: dict
        """
        return asdict(self)


@dataclass
class InstallProgress:
    """Installation progress snapshot returned by :meth:`~.service.AIWorkload.get_install_progress`.

    :param str node_id: Target label (``transport.target_label``).
    :param str component: Component name (``"ai_workload"``).
    :param WorkloadState state: Overall workload state.
    :param int overall_percent: 0–100.
    :param list steps: Per-step progress as :class:`StepProgress` instances.
    :param float elapsed_s: Wall-clock seconds since installation started.
    """

    node_id: str
    component: str
    state: WorkloadState
    overall_percent: int
    steps: List[StepProgress]
    elapsed_s: float

    def to_dict(self) -> dict:
        """Return a plain :class:`dict` representation including nested steps.

        :return: Fully serialisable dict.
        :rtype: dict
        """
        return {
            "node_id": self.node_id,
            "component": self.component,
            "state": self.state,
            "overall_percent": self.overall_percent,
            "steps": [s.to_dict() for s in self.steps],
            "elapsed_s": self.elapsed_s,
        }


@dataclass
class BenchmarkProgress:
    """Benchmark progress snapshot returned by :meth:`~.service.AIWorkload.get_run_progress`.

    :param str node_id: Target label (``transport.target_label``).
    :param bool is_running: Whether the benchmark worker thread is active.
    :param int run_index: Number of single-unit runs completed in the current session.
    :param int total_runs: Total number of single-unit runs requested.
    :param int duration_s: Total requested benchmark duration in seconds
        (``total_runs * config.bench_duration_s``).
    :param float elapsed_s: Wall-clock seconds elapsed since start; computed fresh at call time.
    :param float remaining_s: Estimated wall-clock seconds remaining; computed fresh at call time.
    :param int percent_complete: 0–100, derived from ``run_index / total_runs``.
    :param dict metrics: Latest metrics snapshot (keys: ``latency_min_us``,
        ``latency_avg_us``, ``latency_max_us``, ``throughput_fps``).
    :param list metrics_history: All in-session snapshots with an added ``elapsed_s`` field.
    :param str run_error: Non-empty if the loop terminated due to max consecutive failures.
    :param WorkloadState state: Overall workload state.
    """

    node_id: str
    is_running: bool
    run_index: int
    total_runs: int
    duration_s: int
    elapsed_s: float
    remaining_s: float
    percent_complete: int
    metrics: dict = field(default_factory=dict)
    metrics_history: List[dict] = field(default_factory=list)
    run_error: str = ""
    state: WorkloadState = WorkloadState.NOT_STARTED

    def to_dict(self) -> dict:
        """Return a plain :class:`dict` representation.

        :return: Fully serialisable dict.
        :rtype: dict
        """
        return asdict(self)


# ── Internal state dataclasses ────────────────────────────────────────────────


@dataclass
class _InstallState:
    """Mutable installation state owned by :class:`~.service.AIWorkload`.

    :param str target_label: Human-readable transport label (``transport.target_label``).
    :param str component: Component name.
    :param WorkloadState state: Overall workload state.
    :param int overall_percent: 0–100 completion percentage.
    :param list steps: Per-step progress dicts (mutated in-place by the worker).
    :param float start_time: ``time.monotonic()`` value at installation start (0 if not started).
    :param float end_time: ``time.monotonic()`` value at installation end (0 if not finished).
    :param threading.Event stop_event: Set by :meth:`~.installer.AIWorkloadInstaller.cancel`.
    :param thread: Worker thread reference (set after :meth:`~.installer.AIWorkloadInstaller.start`).
    :param bool started: ``True`` once :meth:`~.installer.AIWorkloadInstaller.start` has been
        called (enforces single-use).
    """
    
    target_label: str = ""
    component: str = ""
    state: WorkloadState = WorkloadState.NOT_STARTED
    overall_percent: int = 0
    steps: List[dict] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: Optional[threading.Thread] = None
    started: bool = False


@dataclass
class _RunState:
    """Mutable benchmark run state owned by :class:`~.runner.AIWorkloadRunner`.

    :param str target_label: Human-readable transport label (``transport.target_label``).
    :param bool is_running: Whether the benchmark worker thread is active.
    :param int run_index: Number of runs completed in the current session.
    :param float start_time: ``time.monotonic()`` value at run start (0 if never started).
    :param threading.Event stop_event: Set by :meth:`~.runner.AIWorkloadRunner.stop`.
    :param dict metrics: Most recent metrics snapshot.
    :param list metrics_history: All collected in-session snapshots, each with an
        ``elapsed_s`` field.
    :param thread: Worker thread reference (set after :meth:`~.runner.AIWorkloadRunner.start`).
    :param str run_error: Non-empty if the loop terminated due to max consecutive failures.
    :param WorkloadState state: Overall workload state.
    """

    target_label: str = ""
    is_running: bool = False
    run_index: int = 0
    total_runs: int = 0
    duration_s: int = 0
    start_time: float = 0.0
    stop_event: threading.Event = field(default_factory=threading.Event)
    metrics: dict = field(default_factory=dict)
    metrics_history: List[dict] = field(default_factory=list)
    thread: Optional[threading.Thread] = None
    run_error: str = ""
    state: WorkloadState = WorkloadState.NOT_STARTED
