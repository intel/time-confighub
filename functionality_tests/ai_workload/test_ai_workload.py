#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
"""
AI Workload service smoke test against a remote DUT.

Usage
-----
    # Pass credentials via environment variables (recommended):
    DUT_HOST=10.107.255.21 DUT_USER=root DUT_PASSWORD=<pw> python test_ai_workload.py

    # Or override defaults inline:
    python test_ai_workload.py --host 10.107.255.21 --user root

The script runs the full two-phase cycle:
  1. install()          — setup phase; polls until done or error
  2. start()            — verify env, then run benchmark asynchronously
  3. get_run_progress() — poll for live metrics
  4. stop()             — stop benchmark
  5. collect_logs()     — retrieve report JSON from DUT

Exit codes
----------
  0  all phases completed successfully
  1  setup (install) failed
  2  benchmark start or runtime failed
  3  transport / connection error
"""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
import time

# ── path setup ───────────────────────────────────────────────────────────────

_REPO_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
if _REPO_SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(_REPO_SRC))

# ── imports ───────────────────────────────────────────────────────────────────

import time_config_hub.utils.system_controller as sc
from time_config_hub.infra.execution_transport import make_transport
from time_config_hub.orchestrator.models.topology import Target
from time_config_hub.services.ai_workload import AIWorkload
from time_config_hub.services.ai_workload.state import WorkloadState

# ── logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("smoke_test")

# ── CLI args ──────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AI Workload service smoke test")
    p.add_argument("--host", default=os.environ.get("DUT_HOST", "10.107.255.21"))
    p.add_argument("--user", default=os.environ.get("DUT_USER", "root"))
    p.add_argument("--port", type=int, default=int(os.environ.get("DUT_PORT", "22")))
    p.add_argument(
        "--bench-duration", type=int, default=30,
        help="Benchmark duration in seconds (default: 30)",
    )
    p.add_argument(
        "--poll-interval", type=float, default=5.0,
        help="Progress poll interval in seconds (default: 5)",
    )
    p.add_argument(
        "--skip-install", action="store_true",
        help="Skip install phase (assume DUT already set up)",
    )
    return p.parse_args()


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_password(user: str, host: str) -> str:
    """Resolve SSH password from env var or interactive prompt."""
    pw = os.environ.get("DUT_PASSWORD")
    if pw:
        log.info("Using password from DUT_PASSWORD env var")
        return pw
    return getpass.getpass(f"SSH password for {user}@{host}: ")


def _print_install_progress(progress) -> None:
    print(
        f"  [{progress.state:>11}]  {progress.overall_percent:3d}%  "
        f"elapsed={progress.elapsed_s:.1f}s"
    )
    for step in progress.steps:
        mark = {"pending": "○", "running": "►", "done": "✓", "failed": "✗"}.get(
            str(step.status), "?"
        )
        detail = f"  — {step.detail[:60]}" if step.detail else ""
        print(f"             {mark} {step.label}{detail}")


def _print_benchmark_progress(progress) -> None:
    m = progress.metrics
    print(
        f"  [benchmark]  run={progress.run_index}  "
        f"{progress.percent_complete:3d}%  elapsed={progress.elapsed_s:.1f}s  "
        f"remaining={progress.remaining_s:.1f}s"
    )
    if m:
        print(
            f"               latency min/avg/max = "
            f"{m.get('latency_min_us', '?')}/{m.get('latency_avg_us', '?')}/"
            f"{m.get('latency_max_us', '?')} µs  |  "
            f"throughput = {m.get('throughput_fps', '?')} fps"
        )


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = _parse_args()
    identity = f"{args.user}@{args.host}"

    # ── 1. Register with system_controller ───────────────────────────────────
    password = _get_password(args.user, args.host)
    log.info("Registering %s with system_controller …", identity)
    try:
        sc.register(identity, password=password, port=args.port)
    except Exception as exc:
        log.error("Failed to register target: %s", exc)
        return 3

    # ── 2. Build transport + AIWorkload ───────────────────────────────────────
    target = Target(
        id=identity,
        ip_address=args.host,
        ssh_user=args.user,
        ssh_password=password,
        ssh_port=args.port,
    )
    transport = make_transport(target)
    workload = AIWorkload(transport)
    log.info("Transport: %s", transport.target_label)

    # ── 3. Install phase ──────────────────────────────────────────────────────
    if not args.skip_install:
        print("\n" + "=" * 60)
        print("PHASE 1 — INSTALL")
        print("=" * 60)
        log.info("Starting install …")
        workload.install()

        while True:
            progress = workload.get_install_progress()
            _print_install_progress(progress)

            if progress.state == WorkloadState.DONE:
                log.info("Install completed successfully (%.1fs)", progress.elapsed_s)
                break
            if progress.state == WorkloadState.ERROR:
                log.error("Install FAILED — check step details above")
                return 1

            time.sleep(args.poll_interval)
    else:
        log.info("Skipping install phase (--skip-install)")

    # ── 4. Benchmark phase ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"PHASE 2 — BENCHMARK  ({args.bench_duration}s)")
    print("=" * 60)
    log.info("Starting benchmark (duration=%ds) …", args.bench_duration)
    try:
        workload.start(duration_s=args.bench_duration)
    except RuntimeError as exc:
        log.error("Failed to start benchmark: %s", exc)
        return 2

    while True:
        progress = workload.get_run_progress()
        _print_benchmark_progress(progress)

        if progress.run_error:
            log.error("Benchmark loop error: %s", progress.run_error)
            return 2
        if not progress.is_running:
            log.info("Benchmark completed (run_index=%d)", progress.run_index)
            break

        time.sleep(args.poll_interval)

    # ── 5. Collect logs ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE 3 — COLLECT LOGS")
    print("=" * 60)
    lines = workload.collect_logs()
    for line in lines:
        print(line)

    print("\n✓ Smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
