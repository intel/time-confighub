# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
time_config_hub.services.ai_workload.runner — reusable AI workload benchmark runner.

Multiple :class:`AIWorkloadRunner` instances may run simultaneously on different
transports.  A single instance is reusable: after a run finishes or is stopped,
call :meth:`~AIWorkloadRunner.start` again to begin a new run.

Public API
----------
AIWorkloadRunner            : Reusable benchmark runner class.
AIWorkloadMaxRetriesError   : Raised when the benchmark loop exceeds the consecutive
                              failure limit.
BENCHMARK_SAMPLE_INTERVAL_S : Metrics sampling interval (seconds).
"""

from __future__ import annotations

import json
import logging
import threading
import time

from time_config_hub.infra.execution_transport import ExecutionTransport
from time_config_hub.services.common.result import ServiceResult
from time_config_hub.utils.common.status_codes import TchStatusCode

from .config import AIWorkloadConfig
from .run import _resolve_model, _run_benchmark, _stop_benchmark
from .state import BenchmarkProgress, _RunState

_log = logging.getLogger("ai_workload.runner")

#: Interval between metrics snapshots written by the worker thread.
BENCHMARK_SAMPLE_INTERVAL_S: int = 5

# Runner-specific retry behaviour — not user-configurable via AIWorkloadConfig.
_BENCH_RETRY_DELAY_S: int = 5
_MAX_CONSECUTIVE_FAILURES: int = 3


class AIWorkloadMaxRetriesError(RuntimeError):
    """Raised when the benchmark loop exceeds consecutive failure limit.

    Propagates out of the worker thread so callers can react via
    :func:`threading.excepthook` or by inspecting
    :attr:`~.state.BenchmarkProgressDict.run_error` from
    :meth:`AIWorkloadRunner.get_progress`.
    """


class AIWorkloadRunner:
    """Reusable AI workload benchmark runner for one transport target.

    Multiple instances may co-exist and run simultaneously.  After a run ends
    (naturally or via :meth:`stop`), the same instance may be reused by calling
    :meth:`start` again.

    Thread safety
    -------------
    All public methods are safe to call from any thread concurrently.

    Example usage::

        runner = AIWorkloadRunner(transport)
        result = runner.start(duration_s=60)   # returns immediately

        # poll from any thread
        progress = runner.get_progress()       # ServiceResult; data = BenchmarkProgressDict

        # stop early
        runner.stop()

        # reuse
        result = runner.start(duration_s=120)

    :param ExecutionTransport transport: Execution transport for the target.
    :param AIWorkloadConfig config: Configuration; uses defaults if omitted.
    """

    def __init__(
        self,
        transport: ExecutionTransport,
        config: AIWorkloadConfig | None = None,
    ) -> None:
        self._transport = transport
        self._config = config or AIWorkloadConfig()
        self._state = _RunState(target_label=transport.target_label)
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, duration_s: int | None = None) -> ServiceResult:
        """Start the benchmark worker thread and return immediately.

        If the previous run has finished, state is reset automatically so the
        same instance can be reused.

        :param int duration_s: Benchmark duration in seconds.
        :return: :class:`~.state.ServiceResult` with:

            * :attr:`~time_config_hub.utils.common.status_codes.TchStatusCode.SUCCESS`
              — worker started; ``data`` is the initial
              :class:`~.state.BenchmarkProgressDict`.
            * :attr:`~time_config_hub.utils.common.status_codes.TchStatusCode.ALREADY_RUNNING`
              — a benchmark is already in progress on this instance.
        :rtype: ServiceResult
        """
        if duration_s is None:
            duration_s = self._config.bench_duration_s
        with self._lock:
            if self._state.is_running:
                return ServiceResult(
                    status_code=TchStatusCode.ALREADY_RUNNING,
                    error=(
                        f"Benchmark already running for "
                        f"{self._transport.target_label}"
                    ),
                    data=self._build_progress_locked(),
                )
            # Reset state for reuse
            self._state.stop_event.clear()
            self._state.is_running = True
            self._state.duration_s = duration_s
            self._state.start_time = time.monotonic()
            self._state.metrics = {}
            self._state.metrics_history = []
            self._state.run_error = ""

        t = threading.Thread(
            target=self._run_worker,
            args=(duration_s,),
            daemon=True,
            name=f"ai_runner_{self._transport.target_label}",
        )
        with self._lock:
            self._state.thread = t
        t.start()

        _log.info(
            "[runner] started benchmark for %s duration=%ds",
            self._transport.target_label,
            duration_s,
        )
        return ServiceResult(
            status_code=TchStatusCode.SUCCESS,
            output=(
                f"Benchmark started for {self._transport.target_label} "
                f"(duration={duration_s}s)"
            ),
            data=self._build_progress(),
        )

    def stop(self) -> ServiceResult:
        """Stop the running benchmark and return immediately.

        Sets the internal stop event and sends a ``pkill`` signal to
        ``benchmark_app``.  Does not wait for the worker thread to finish.

        :return: :class:`~.state.ServiceResult` with:

            * :attr:`~time_config_hub.utils.common.status_codes.TchStatusCode.SUCCESS`
              — stop signal sent; ``data`` is the current
              :class:`~.state.BenchmarkProgressDict`.
            * :attr:`~time_config_hub.utils.common.status_codes.TchStatusCode.NOT_RUNNING`
              — no benchmark was running.
        :rtype: ServiceResult
        """
        with self._lock:
            if not self._state.is_running:
                return ServiceResult(
                    status_code=TchStatusCode.NOT_RUNNING,
                    error=f"No benchmark running for {self._transport.target_label}",
                    data=self._build_progress_locked(),
                )
            self._state.stop_event.set()

        _stop_benchmark(self._transport)

        _log.info("[runner] stop requested for %s", self._transport.target_label)
        return ServiceResult(
            status_code=TchStatusCode.SUCCESS,
            output=f"Stop signal sent to {self._transport.target_label}",
            data=self._build_progress(),
        )

    def get_progress(self) -> ServiceResult:
        """Return the current benchmark progress without blocking.

        ``elapsed_s`` and ``remaining_s`` are computed fresh from
        :func:`time.monotonic` at call time so the values are always current
        regardless of the sample interval.

        Safe to call from any thread at any time, including before :meth:`start`
        is called.

        :return: :class:`~.state.ServiceResult` with
            :attr:`~time_config_hub.utils.common.status_codes.TchStatusCode.SUCCESS`
            and ``data`` set to the current :class:`~.state.BenchmarkProgressDict`.
        :rtype: ServiceResult
        """
        return ServiceResult(
            status_code=TchStatusCode.SUCCESS,
            data=self._build_progress(),
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_progress_locked(self) -> BenchmarkProgress:
        """Build a progress snapshot.

        **Must be called while** ``_lock`` **is held.**

        :return: Current :class:`~.state.BenchmarkProgressDict`.
        :rtype: BenchmarkProgressDict
        """
        elapsed = (
            max(0.0, time.monotonic() - self._state.start_time)
            if self._state.start_time > 0
            else 0.0
        )
        duration_s = self._state.duration_s
        remaining = max(0.0, duration_s - elapsed)
        pct = min(100, int(elapsed / duration_s * 100)) if duration_s > 0 else 0
        return BenchmarkProgress(
            node_id=self._transport.target_label,
            is_running=self._state.is_running,
            run_index=self._state.run_index,
            duration_s=duration_s,
            elapsed_s=elapsed,
            remaining_s=remaining,
            percent_complete=pct,
            metrics=dict(self._state.metrics),
            metrics_history=list(self._state.metrics_history),
            run_error=self._state.run_error,
        )

    def _build_progress(self) -> BenchmarkProgress:
        """Build a progress snapshot, acquiring ``_lock`` internally.

        Must **not** be called while ``_lock`` is already held by the calling
        thread.

        :return: Current :class:`~.state.BenchmarkProgressDict`.
        :rtype: BenchmarkProgressDict
        """
        with self._lock:
            return self._build_progress_locked()

    # ── Worker thread ─────────────────────────────────────────────────────────

    def _run_worker(self, duration_s: int) -> None:
        """Worker thread target: run benchmark in a continuous loop until stopped.

        Each iteration:

        1. Resolves the best available model.
        2. Starts a metrics-sampling sub-thread.
        3. Calls ``_run_benchmark`` (blocks until completion or cancellation).
        4. On success: updates live metrics and increments ``run_index``.
        5. On failure (without a stop request): waits ``_BENCH_RETRY_DELAY_S``
           seconds then retries.
        6. Exits the loop when ``stop_event`` is set.

        :param int duration_s: Per-run benchmark duration in seconds.
        """
        consecutive_failures = 0
        try:
            while not self._state.stop_event.is_set():
                model_xml = _resolve_model(self._transport, self._config)
                if model_xml is None:
                    _log.error(
                        "[runner] no model found for %s — aborting loop",
                        self._transport.target_label,
                    )
                    break

                sampler_stop = threading.Event()
                sampler = threading.Thread(
                    target=self._metrics_sampler,
                    args=(sampler_stop,),
                    daemon=True,
                    name=f"ai_sampler_{self._transport.target_label}",
                )
                sampler.start()

                success = False
                try:
                    success, _lines = _run_benchmark(
                        model_xml,
                        duration_s,
                        self._transport,
                        self._config,
                        self._state.stop_event,
                    )
                except Exception:  # noqa: BLE001
                    _log.exception(
                        "[runner] _run_benchmark raised for %s",
                        self._transport.target_label,
                    )
                finally:
                    sampler_stop.set()
                    sampler.join(timeout=BENCHMARK_SAMPLE_INTERVAL_S + 2)

                if self._state.stop_event.is_set():
                    break

                if success:
                    consecutive_failures = 0
                    final_metrics = _try_read_ai_metrics(self._transport, self._config.report_json)
                    elapsed = (
                        max(0.0, time.monotonic() - self._state.start_time)
                        if self._state.start_time > 0
                        else 0.0
                    )
                    with self._lock:
                        run_idx = self._state.run_index
                        if final_metrics:
                            self._state.metrics = final_metrics
                            if final_metrics.get("throughput_fps", 0) > 0:
                                self._state.metrics_history.append(
                                    {**final_metrics, "elapsed_s": elapsed}
                                )
                        self._state.run_index += 1
                    _log.info(
                        "[runner] run %d completed for %s",
                        run_idx,
                        self._transport.target_label,
                    )
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        msg = (
                            f"Benchmark on {self._transport.target_label} failed "
                            f"{_MAX_CONSECUTIVE_FAILURES} consecutive times — aborting"
                        )
                        raise AIWorkloadMaxRetriesError(msg)
                    _log.warning(
                        "[runner] run %d failed for %s (%d/%d) — retrying in %ds",
                        self._state.run_index,
                        self._transport.target_label,
                        consecutive_failures,
                        _MAX_CONSECUTIVE_FAILURES,
                        _BENCH_RETRY_DELAY_S,
                    )
                    self._state.stop_event.wait(_BENCH_RETRY_DELAY_S)
        except AIWorkloadMaxRetriesError as exc:
            _log.error(
                "[runner] max retries exceeded for %s: %s",
                self._transport.target_label,
                exc,
            )
            with self._lock:
                self._state.run_error = str(exc)
            raise
        finally:
            with self._lock:
                self._state.is_running = False
                self._state.run_index = 0
            _log.info(
                "[runner] worker loop finished for %s", self._transport.target_label
            )

    def _metrics_sampler(self, stop_event: threading.Event) -> None:
        """Sub-thread: sample metrics from the benchmark report every interval.

        Polls :attr:`AIWorkloadConfig.report_json` and appends a snapshot (with
        ``elapsed_s``) to :attr:`_state.metrics_history` whenever new data is
        available.  Exits when *stop_event* is set.

        :param threading.Event stop_event: Set by :meth:`_run_worker` to terminate.
        """
        while not stop_event.is_set():
            stop_event.wait(timeout=BENCHMARK_SAMPLE_INTERVAL_S)
            if stop_event.is_set():
                break
            metrics = _try_read_ai_metrics(self._transport, self._config.report_json)
            if metrics:
                elapsed = (
                    max(0.0, time.monotonic() - self._state.start_time)
                    if self._state.start_time > 0
                    else 0.0
                )
                with self._lock:
                    self._state.metrics = metrics
                    self._state.metrics_history.append(
                        {**metrics, "elapsed_s": elapsed}
                    )


# ── Module-level helpers ──────────────────────────────────────────────────────


def _try_read_ai_metrics(transport: ExecutionTransport, report_json: object) -> dict:
    """Attempt to parse AI workload metrics from the benchmark report JSON.

    Reads the report file from the transport target (local or remote).
    Handles multiple OpenVINO benchmark_app JSON output formats.
    Returns an empty dict if the report is absent or malformed.

    :param ExecutionTransport transport: Transport to read the report from.
    :param report_json: Path to the benchmark report JSON on the target
        (from :attr:`~.config.AIWorkloadConfig.report_json`).
    :return: Dict with ``latency_min_us``, ``latency_avg_us``,
        ``latency_max_us``, and ``throughput_fps`` keys, or ``{}`` on failure.
    :rtype: dict
    """
    try:
        result = transport.run(["cat", str(report_json)])
        if not result.success or not result.stdout:
            _log.debug(
                "[runner] _try_read_ai_metrics: cat failed on %s "
                "(success=%s stdout_len=%d)",
                transport.target_label,
                result.success,
                len(result.stdout or ""),
            )
            return {}
        data = json.loads(result.stdout)

        # Locate the latency/throughput container.
        # OpenVINO benchmark_app JSON has evolved across versions; try in order:
        #   1. execution_results is a list  → take first element
        #   2. execution_results is a dict  → use it directly
        #   3. latency / throughput at the top level  → use data directly
        exec_res = data.get("execution_results")
        if isinstance(exec_res, list) and exec_res:
            summary = exec_res[0]
        elif isinstance(exec_res, dict):
            summary = exec_res
        else:
            summary = data  # top-level fallback

        # Latency key may be "latency" or "latency_ms" depending on version.
        latency = summary.get("latency") or summary.get("latency_ms") or {}
        throughput = float(
            summary.get("throughput") or summary.get("item_per_second") or 0
        )

        if not latency and not throughput:
            _log.warning(
                "[runner] _try_read_ai_metrics: no usable data on %s "
                "— top-level keys: %s",
                transport.target_label,
                list(data.keys()),
            )
            return {}

        metrics = {
            "latency_min_us": float(latency.get("min", 0)) * 1000,
            "latency_avg_us": float(latency.get("avg", latency.get("mean", 0))) * 1000,
            "latency_max_us": float(latency.get("max", 0)) * 1000,
            "throughput_fps": throughput,
        }
        _log.info(
            "[runner] _try_read_ai_metrics: %s throughput=%.1f fps avg_latency=%.2f ms",
            transport.target_label,
            throughput,
            metrics["latency_avg_us"] / 1000,
        )
        return metrics
    except Exception:  # noqa: BLE001
        _log.warning(
            "[runner] _try_read_ai_metrics: exception on %s",
            transport.target_label,
            exc_info=True,
        )
        return {}
