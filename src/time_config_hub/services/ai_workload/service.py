# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
AI Workload — setup and runtime for a single DUT target.

:class:`AIWorkload` is the self-contained library entry point for AI workload
operations on one target.  It covers two distinct phases:

Setup phase (async)
-------------------
- :meth:`AIWorkload.install` — spawns a worker thread that runs all setup
  steps (venv, pip install, model export, quantization).  Returns immediately.
- :meth:`AIWorkload.get_install_progress` — step-level progress snapshot;
  safe to poll from any thread at any time.
- :meth:`AIWorkload.cancel_install` — signal the install thread to stop.

Runtime phase (async benchmark, sync log collection)
-----------------------------------------------------
- :meth:`AIWorkload.start` — verifies the installed environment, then starts
  the benchmark asynchronously via :class:`~.runner.AIWorkloadRunner`.
  ``duration_s`` is the *total* requested duration; the runner divides it into
  ``round(duration_s / config.bench_duration_s)`` unit-runs, each lasting
  ``config.bench_duration_s`` seconds.  After every unit-run ``benchmark_app``
  writes ``benchmark_report.json`` and metrics become available.
- :meth:`AIWorkload.get_run_progress` — live benchmark metrics snapshot.
- :meth:`AIWorkload.stop` — stop the running benchmark.
- :meth:`AIWorkload.collect_logs` — retrieve the benchmark report JSON.

The orchestrator creates one :class:`AIWorkload` instance per DUT target and
manages the collection externally.  This class has no knowledge of other
targets or concurrent installations.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from time_config_hub.infra.execution_transport import ExecutionTransport

from .config import AIWorkloadConfig
from .helper import _run_cmds
from .installer import AIWorkloadInstaller
from .runner import AIWorkloadRunner
from .setup import build_verify_steps
from .state import (
    BenchmarkProgress,
    InstallProgress,
)

logger = logging.getLogger(__name__)

_COMPONENT = "ai_workload"
_DEFAULT_LOG_LOCAL_DIR = "results/"


class AIWorkload:
    """AI workload setup and runtime for a single DUT target.

    Bind one instance to one transport at construction time.  The orchestrator
    creates one :class:`AIWorkload` per DUT and calls the setup and runtime
    methods as needed.

    Thread safety
    -------------
    All public methods are safe to call from any thread concurrently.

    Configuration
    -------------
    The verify steps are built once at construction from *config* (via
    :func:`~.setup.build_verify_steps`), so a custom
    :class:`~.config.AIWorkloadConfig` drives the commands run on the target.
    Installation is delegated to :class:`~.installer.AIWorkloadInstaller`,
    which also owns disk-persisted progress for the setup phase.

    :param ExecutionTransport transport: Execution transport for the target.
    :param AIWorkloadConfig config: Configuration; uses defaults if omitted.
    :param str log_local_dir: Local directory for collected benchmark reports.
    """

    def __init__(
        self,
        transport: ExecutionTransport,
        config: AIWorkloadConfig | None = None,
        log_local_dir: str = _DEFAULT_LOG_LOCAL_DIR,
    ) -> None:
        self._transport = transport
        self._config = config or AIWorkloadConfig()
        self._log_local_dir = log_local_dir
        self._verify_steps = build_verify_steps(self._config)
        self._installer = AIWorkloadInstaller(transport, self._config)
        self._runner = AIWorkloadRunner(transport, self._config)

    # ------------------------------------------------------------------
    # Setup phase
    # ------------------------------------------------------------------

    def install(self) -> None:
        """Spawn the installation worker thread and return immediately.

        Delegates to :class:`~.installer.AIWorkloadInstaller`.  The installer
        persists step-level progress to disk so it survives process restarts.

        :raises RuntimeError: If ``install()`` has already been called on
            this instance.  Create a new :class:`AIWorkload` to retry.
        """
        result = self._installer.start()
        if not result.success:
            raise RuntimeError(
                f"install() failed for '{self._transport.target_label}': {result.error}"
            )
        logger.info("[ai_workload] install started for '%s'", self._transport.target_label)

    def get_install_progress(self) -> InstallProgress:
        """Return the current installation progress snapshot.

        Safe to call before :meth:`install` is called (returns safe defaults),
        during installation, and after completion.

        :return: Step-level progress snapshot.
        :rtype: InstallProgress
        """
        return self._installer.get_progress().data

    def cancel_install(self) -> None:
        """Signal the installation worker to stop before the next step.

        Returns immediately; the worker thread checks the signal between steps
        and terminates cleanly.  Has no effect if no installation is running.
        """
        self._installer.cancel()
        logger.info(
            "[ai_workload] install cancel requested for '%s'",
            self._transport.target_label,
        )

    # ------------------------------------------------------------------
    # Runtime phase
    # ------------------------------------------------------------------

    def start(
        self,
        duration_s: int | None = None,
        dry_run: bool = False,
    ) -> None:
        """Verify the AI environment, then start the benchmark asynchronously.

        The configured verify steps (built from this instance's
        :class:`~.config.AIWorkloadConfig`) run synchronously before spawning
        the benchmark thread; the method returns once the thread is started.

        :param int duration_s: Benchmark duration in seconds.
        :param bool dry_run: If True, log intent without executing.
        :raises RuntimeError: If environment verification fails or the benchmark
            is already running on this instance.
        """
        if duration_s is None:
            duration_s = self._config.bench_duration_s
        if dry_run:
            logger.info(
                "[ai_workload][DRY RUN] Would start benchmark on '%s' (duration=%ds)",
                self._transport.target_label,
                duration_s,
            )
            return

        for step in self._verify_steps:
            success, detail = _run_cmds(step["cmds"], transport=self._transport)
            if not success:
                raise RuntimeError(
                    f"AI environment check failed on '{self._transport.target_label}' "
                    f"at step '{step['name']}': {detail}"
                )

        result = self._runner.start(duration_s=duration_s)
        if not result.success:
            raise RuntimeError(
                f"Failed to start AI benchmark on '{self._transport.target_label}': "
                f"{result.error}"
            )
        logger.info(
            "[ai_workload] benchmark started for '%s'", self._transport.target_label
        )

    def get_run_progress(self) -> BenchmarkProgress:
        """Return the current benchmark progress snapshot.

        Safe to call before :meth:`start`, during a run, and after stopping.

        :return: Live benchmark metrics snapshot.
        :rtype: BenchmarkProgress
        """
        return self._runner.get_progress().data

    def stop(self, dry_run: bool = False) -> None:
        """Stop the running benchmark.

        Sends a stop signal and a ``pkill`` to ``benchmark_app``.  Returns
        immediately without waiting for the worker thread to finish.

        :param bool dry_run: If True, log intent without executing.
        """
        if dry_run:
            logger.info(
                "[ai_workload][DRY RUN] Would stop benchmark on '%s'",
                self._transport.target_label,
            )
            return
        self._runner.stop()
        logger.info(
            "[ai_workload] benchmark stopped for '%s'", self._transport.target_label
        )

    def collect_logs(self, dry_run: bool = False) -> list[str]:
        """Retrieve the benchmark report JSON from the target.

        :param bool dry_run: If True, log intent without executing.
        :return: Output log lines.
        :rtype: list[str]
        """
        output = [f"[ai_workload] collect_logs from '{self._transport.target_label}'"]
        local_name = (
            self._transport.target_label.replace("@", "_") + "_ai_benchmark.json"
        )
        local_path = os.path.join(self._log_local_dir, local_name)

        if dry_run:
            output.append(
                f"[DRY RUN] Would retrieve '{self._config.report_json}' "
                f"from '{self._transport.target_label}' \u2192 '{local_path}'"
            )
            return output

        Path(self._log_local_dir).mkdir(parents=True, exist_ok=True)
        self._transport.get_file(str(self._config.report_json), local_path)

        logger.info(
            "[ai_workload] logs collected from '%s'", self._transport.target_label
        )
        output.append(f"[ai_workload] report saved to '{local_path}'")
        return output


