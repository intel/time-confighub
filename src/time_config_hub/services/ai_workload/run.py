# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
time_config_hub.services.ai_workload.run — launch and stop the benchmark process.

Executes the OpenVINO ``benchmark_app`` for the configured ResNet-50 model
(INT8 preferred, FP32 fallback) on a local or remote target via
:class:`~time_config_hub.infra.execution_transport.ExecutionTransport`.

Internal API
------------
_resolve_model   : Select the best available model XML (INT8 preferred, FP32 fallback).
_run_benchmark   : Launch benchmark_app on a transport target.
_stop_benchmark  : Stop a running benchmark_app via pkill on a transport target.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

from time_config_hub.infra.execution_transport import ExecutionTransport

from .config import AIWorkloadConfig
from .helper import _run_cmds

_log = logging.getLogger("ai_workload.run")

_POLL_INTERVAL_S = 0.5


# ── Private helpers ────────────────────────────────────────────────────────────


def _resolve_model(transport: ExecutionTransport, config: AIWorkloadConfig) -> Optional[Path]:
    """Return the best available model XML path (INT8 preferred, FP32 fallback).

    Checks file existence on the transport target (works for local and remote).

    :param ExecutionTransport transport: Transport to check model existence on.
    :param AIWorkloadConfig config: Configuration providing model paths.
    :return: Path to the model XML, or ``None`` if neither exists on the target.
    :rtype: Optional[Path]
    """
    for xml in (config.int8_xml, config.fp32_xml):
        result = transport.run(["test", "-f", str(xml)])
        if result.success:
            return xml
    return None


def _run_benchmark(
    model_xml: Path,
    duration_s: int,
    transport: ExecutionTransport,
    config: AIWorkloadConfig,
    stop_event: Optional[threading.Event] = None,
) -> tuple[bool, list[str]]:
    """Run benchmark_app on the transport target.

    :param Path model_xml: Model XML path.
    :param int duration_s: Benchmark duration in seconds.
    :param ExecutionTransport transport: Transport to run the benchmark on.
    :param AIWorkloadConfig config: Configuration providing binary paths and
        benchmark parameters.
    :param Optional[threading.Event] stop_event: Cancellation signal (local or
        remote); when set, sends ``pkill benchmark_app`` through the transport.
    :return: ``(success, output_lines)``.
    :rtype: tuple[bool, list[str]]
    """
    output: list[str] = []
    target_label = transport.target_label

    cmd_str = (
        f"mkdir -p {config.report_dir} && "
        f"taskset -c {config.bench_cpu_cores} {config.bench_app} "
        f"-m {model_xml} "
        f"-d {config.bench_device} "
        f"-b {config.bench_batch} "
        f"-hint tput "
        f"-t {duration_s} "
        f"-report_type no_counters "
        f"-json_stats "
        f"-report_folder {config.report_dir}"
    )
    output.append(f"  [run_benchmark] cmd: {cmd_str}")
    _log.info(
        "[run_workload] launching benchmark_app on %s (duration=%ds)",
        target_label,
        duration_s,
    )

    cmds = [{"info": "run benchmark_app", "cmd": cmd_str, "timeout": duration_s + 60}]

    if stop_event is not None:
        # Early-exit: already cancelled before we even start.
        if stop_event.is_set():
            output.append("  [run_benchmark] Cancelled by stop signal")
            _log.warning("[run_workload] benchmark_app was cancelled")
            return False, output

        # Run the blocking _run_cmds call in a daemon thread so the main thread
        # can monitor stop_event and cancel via pkill if needed.
        _result: list[tuple[bool, str]] = []

        def _worker() -> None:
            _result.append(_run_cmds(cmds, transport=transport))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        while t.is_alive():
            if stop_event.is_set():
                _log.info(
                    "[run_workload] stop_event set — killing benchmark_app on %s",
                    target_label,
                )
                transport.run(["pkill", "-f", "benchmark_app"])
                t.join(timeout=15)
                output.append("  [run_benchmark] Cancelled by stop signal")
                _log.warning("[run_workload] benchmark_app was cancelled")
                return False, output
            time.sleep(_POLL_INTERVAL_S)
        t.join()
        success, detail = _result[0]
    else:
        success, detail = _run_cmds(cmds, transport=transport)

    if success:
        output.append(f"  [run_benchmark] OK — report written to {config.report_dir}")
        _log.info("[run_workload] benchmark completed on %s", target_label)
    else:
        output.append(f"  [run_benchmark] FAILED — {detail}")
        _log.error("[run_workload] benchmark failed on %s: %s", target_label, detail)

    return success, output


def _stop_benchmark(transport: ExecutionTransport) -> bool:
    """Stop a running benchmark_app via pkill on the transport target.

    :param ExecutionTransport transport: Transport to send the pkill signal through.
    :return: ``True`` if pkill found and signalled the process, ``False``
        otherwise.
    :rtype: bool
    """
    result = transport.run(["pkill", "-f", "benchmark_app"])
    ok = result.success
    if ok:
        _log.info(
            "[stop_workload] pkill benchmark_app succeeded on %s",
            transport.target_label,
        )
    else:
        _log.warning(
            "[stop_workload] pkill found no benchmark_app on %s",
            transport.target_label,
        )
    return ok
