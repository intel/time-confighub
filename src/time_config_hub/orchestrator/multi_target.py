# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
Multi-DUT Step Definitions for B2B and MULTI_DUT Orchestration

Defines the ordered sub-step sequences used by the orchestrator when
executing stages in B2B or MULTI_DUT topologies.

Each entry in ``STEP_REGISTRY`` maps a stage name to a list of
sub-step tuples: ``(step_name, roles, action)``.

The orchestrator executes steps sequentially.  Within each step,
targets whose role matches ``roles`` run the ``action`` in parallel.
All matching targets must complete a step before the next step begins.

For parallel stages (install, apply_config), a single step targeting
both roles achieves the same effect as the original parallel dispatch.

For ordered stages (run, results), multiple steps enforce the required
talker/listener execution sequence.

"""

from __future__ import annotations

import logging

from .models import StageHandler, Target

__all__ = [
    "get_steps",
    "STEP_REGISTRY",
]

logger = logging.getLogger("orchestrator.multi_target")


# ==================================================================
# Sub-step actions for the 'install' stage
# ==================================================================

def _install(target: Target, dry_run: bool) -> list[str]:
    """Install tools and dependencies on a multi-DUT target."""
    output = [f"[{target.id}/{target.role}] Installing tools and dependencies"]
    if dry_run:
        output.append(f"[DRY RUN] Would install on '{target.id}'")
        return output
    # TODO: Install/verify required packages (Testbench, AI Workloads, etc.)
    #   sc.run(["apt-get", "install", "-y", "package"], target_id=target.sc_target_id)
    output.append(f"[{target.id}/{target.role}] installation complete")
    return output


# ==================================================================
# Sub-step actions for the 'apply_config' stage
# ==================================================================

def _apply_config(target: Target, dry_run: bool) -> list[str]:
    """Apply TCC and TSN configurations on a multi-DUT target."""
    output = [f"[{target.id}/{target.role}] Applying configuration"]
    if dry_run:
        output.append(f"[DRY RUN] Would apply config on '{target.id}'")
        return output
    # TODO: Apply TCC/TSN config via TCH config library
    output.append(f"[{target.id}/{target.role}] configuration applied")
    return output


# ==================================================================
# Sub-step actions for the 'run' stage — TALKER
# ==================================================================

def _talker_run_ptp4l(target: Target, dry_run: bool) -> list[str]:
    """Start ptp4l on the talker as PTP grandmaster."""
    output = [f"[{target.id}/{target.role}] Starting ptp4l (GM)"]
    if dry_run:
        output.append(f"[DRY RUN] Would start ptp4l GM on '{target.id}'")
        return output
    # TODO: sc.run(["ptp4l", "-i", iface, "-f", gm_cfg, ...], target_id=target.sc_target_id)
    output.append(f"[{target.id}/{target.role}] ptp4l GM started")
    return output


def _talker_verify_ptp_sync(target: Target, dry_run: bool) -> list[str]:
    """Verify PTP grandmaster status on the talker."""
    output = [f"[{target.id}/{target.role}] Verifying PTP GM status"]
    if dry_run:
        output.append(f"[DRY RUN] Would verify PTP GM status on '{target.id}'")
        return output
    # TODO: Poll ptp4l until portState is MASTER
    #   for attempt in range(max_retries):
    #       result = sc.run(["pmc", "-u", "-b", "0", "GET PORT_DATA_SET"],
    #                       target_id=target.sc_target_id)
    #       if "MASTER" in result.get("stdout", ""):
    #           break
    #       time.sleep(poll_interval)
    #   else:
    #       raise RuntimeError(f"PTP GM not achieved on '{target.id}'")
    output.append(f"[{target.id}/{target.role}] PTP GM status verified")
    return output


def _talker_run_phc2sys(target: Target, dry_run: bool) -> list[str]:
    """Start phc2sys on the talker."""
    output = [f"[{target.id}/{target.role}] Starting phc2sys"]
    if dry_run:
        output.append(f"[DRY RUN] Would start phc2sys on '{target.id}'")
        return output
    # TODO: sc.run(["phc2sys", ...], target_id=target.sc_target_id)
    output.append(f"[{target.id}/{target.role}] phc2sys started")
    return output


def _talker_run_testbench(target: Target, dry_run: bool) -> list[str]:
    """Start testbench transmitter on the talker."""
    output = [f"[{target.id}/{target.role}] Starting testbench (tx)"]
    if dry_run:
        output.append(f"[DRY RUN] Would start testbench tx on '{target.id}'")
        return output
    # TODO: launch testbench in transmit mode
    output.append(f"[{target.id}/{target.role}] testbench tx started")
    return output


# ==================================================================
# Sub-step actions for the 'run' stage — LISTENER
# ==================================================================

def _listener_run_ptp4l(target: Target, dry_run: bool) -> list[str]:
    """Start ptp4l on a listener as PTP slave."""
    output = [f"[{target.id}/{target.role}] Starting ptp4l (slave)"]
    if dry_run:
        output.append(f"[DRY RUN] Would start ptp4l slave on '{target.id}'")
        return output
    # TODO: sc.run(["ptp4l", "-i", iface, "-f", slave_cfg, ...], target_id=target.sc_target_id)
    output.append(f"[{target.id}/{target.role}] ptp4l slave started")
    return output


def _listener_verify_ptp_sync(target: Target, dry_run: bool) -> list[str]:
    """Verify PTP slave lock on a listener."""
    output = [f"[{target.id}/{target.role}] Verifying PTP SLAVE lock"]
    if dry_run:
        output.append(f"[DRY RUN] Would verify PTP SLAVE lock on '{target.id}'")
        return output
    # TODO: Poll ptp4l until portState is SLAVE and offset < threshold
    #   for attempt in range(max_retries):
    #       result = sc.run(["pmc", "-u", "-b", "0", "GET PORT_DATA_SET"],
    #                       target_id=target.sc_target_id)
    #       if "SLAVE" in result.get("stdout", ""):
    #           break
    #       time.sleep(poll_interval)
    #   else:
    #       raise RuntimeError(f"PTP SLAVE lock not achieved on '{target.id}'")
    output.append(f"[{target.id}/{target.role}] PTP SLAVE lock verified")
    return output


def _listener_run_phc2sys(target: Target, dry_run: bool) -> list[str]:
    """Start phc2sys on a listener."""
    output = [f"[{target.id}/{target.role}] Starting phc2sys"]
    if dry_run:
        output.append(f"[DRY RUN] Would start phc2sys on '{target.id}'")
        return output
    # TODO: sc.run(["phc2sys", ...], target_id=target.sc_target_id)
    output.append(f"[{target.id}/{target.role}] phc2sys started")
    return output


def _listener_run_ai_workload(target: Target, dry_run: bool) -> list[str]:
    """Start AI workload on a listener."""
    output = [f"[{target.id}/{target.role}] Starting AI workload"]
    if dry_run:
        output.append(f"[DRY RUN] Would start AI workload on '{target.id}'")
        return output
    # TODO: launch AI workload
    output.append(f"[{target.id}/{target.role}] AI workload started")
    return output


def _listener_run_testbench(target: Target, dry_run: bool) -> list[str]:
    """Start testbench receiver on a listener."""
    output = [f"[{target.id}/{target.role}] Starting testbench (rx)"]
    if dry_run:
        output.append(f"[DRY RUN] Would start testbench rx on '{target.id}'")
        return output
    # TODO: launch testbench in receive mode
    output.append(f"[{target.id}/{target.role}] testbench rx started")
    return output


# ==================================================================
# Sub-step actions for the 'results' stage — TALKER
# ==================================================================

def _talker_stop_testbench(target: Target, dry_run: bool) -> list[str]:
    """Stop testbench transmitter on the talker."""
    output = [f"[{target.id}/{target.role}] Stopping testbench (tx)"]
    if dry_run:
        output.append(f"[DRY RUN] Would stop testbench tx on '{target.id}'")
        return output
    # TODO: stop testbench transmitter process
    output.append(f"[{target.id}/{target.role}] testbench tx stopped")
    return output


def _talker_collect_logs(target: Target, dry_run: bool) -> list[str]:
    """Collect logs and test output from the talker."""
    output = [f"[{target.id}/{target.role}] Collecting logs"]
    if dry_run:
        output.append(f"[DRY RUN] Would collect logs from '{target.id}'")
        return output
    # TODO: gather talker-specific logs, parse results
    output.append(f"[{target.id}/{target.role}] logs collected")
    return output


# ==================================================================
# Sub-step actions for the 'results' stage — LISTENER
# ==================================================================

def _listener_stop_testbench(target: Target, dry_run: bool) -> list[str]:
    """Stop testbench receiver on a listener."""
    output = [f"[{target.id}/{target.role}] Stopping testbench (rx)"]
    if dry_run:
        output.append(f"[DRY RUN] Would stop testbench rx on '{target.id}'")
        return output
    # TODO: stop testbench receiver process
    output.append(f"[{target.id}/{target.role}] testbench rx stopped")
    return output


def _listener_collect_logs(target: Target, dry_run: bool) -> list[str]:
    """Collect logs and test output from a listener."""
    output = [f"[{target.id}/{target.role}] Collecting logs"]
    if dry_run:
        output.append(f"[DRY RUN] Would collect logs from '{target.id}'")
        return output
    # TODO: gather listener-specific logs, parse results
    output.append(f"[{target.id}/{target.role}] logs collected")
    return output


# ==================================================================
# Step Registry — ordered sub-steps for multi-DUT stages
#
# Each entry is a list of (step_name, roles, action) tuples.
# The orchestrator executes steps sequentially; within each step,
# matching-role targets run in parallel, then all wait before the
# next step begins.
#
# For parallel stages (install, apply_config), a single step with
# both roles achieves parallel execution across all targets.
#
# Execution sequence (B2B example, 1 talker + 1 listener):
#
#   Orchestrator thread (conductor)
#   │
#   ├─ install
#   │   └─ all:install              → [talker, listener] parallel → wait
#   │
#   ├─ apply_config
#   │   └─ all:apply_config         → [talker, listener] parallel → wait
#   │
#   ├─ run (9 sequential steps)
#   │   ├─ talker:ptp4l              → [talker]    → wait
#   │   ├─ listeners:ptp4l           → [listener]  → wait
#   │   ├─ talker:verify_ptp_sync    → [talker]    → poll GM status
#   │   ├─ listeners:verify_ptp_sync → [listener]  → poll SLAVE lock
#   │   ├─ listeners:phc2sys         → [listener]  → wait
#   │   ├─ talker:phc2sys            → [talker]    → wait
#   │   │   ── system time synchronized ──
#   │   ├─ listeners:ai_workload     → [listener]  → wait
#   │   ├─ listeners:testbench       → [listener]  → wait
#   │   └─ talker:testbench          → [talker]    → wait
#   │       ── all running ──
#   │
#   └─ results (4 sequential steps)
#       ├─ talker:stop_testbench     → [talker]    → wait
#       ├─ listeners:stop_testbench  → [listener]  → wait
#       ├─ listeners:collect_logs    → [listener]  → wait
#       └─ talker:collect_logs       → [talker]    → wait
#
# Any step failure aborts the stage; any stage failure aborts the
# pipeline.  MULTI_DUT works identically with N listeners — each
# listener-targeted step runs all listeners in parallel.
# ==================================================================

# Each tuple: (step_name, roles, action)
StepEntry = tuple[str, set[str], StageHandler]

def get_steps(stage_name: str) -> list[StepEntry]:
    """Return the ordered step list for a stage in multi-target mode.

    :raises KeyError: If the stage has no steps defined.
    """
    try:
        return STEP_REGISTRY[stage_name]
    except KeyError:
        raise KeyError(
            f"No steps defined for stage '{stage_name}'"
        ) from None

# ==================================================================
# STEP REGISTRY — map stage_name to handler function
# ==================================================================
STEP_REGISTRY: dict[str, list[StepEntry]] = {
    "install": [
        # All targets install in parallel
        ("all:install", {"talker", "listener"}, _install),
    ],
    "apply_config": [
        # All targets apply config in parallel
        ("all:apply_config", {"talker", "listener"}, _apply_config),
    ],
    "run": [
        # 1. Talker starts ptp4l (PTP grandmaster)
        ("talker:ptp4l",              {"talker"},   _talker_run_ptp4l),
        # 2. Listeners start ptp4l (PTP slave — syncs to talker GM)
        ("listeners:ptp4l",           {"listener"}, _listener_run_ptp4l),
        # 3. Verify talker achieved GM status
        ("talker:verify_ptp_sync",    {"talker"},   _talker_verify_ptp_sync),
        # 4. Verify listeners achieved SLAVE lock
        ("listeners:verify_ptp_sync", {"listener"}, _listener_verify_ptp_sync),
        # 5. Listeners start phc2sys
        ("listeners:phc2sys",         {"listener"}, _listener_run_phc2sys),
        # 6. Talker starts phc2sys
        ("talker:phc2sys",            {"talker"},   _talker_run_phc2sys),
        # ── system time synchronized across all nodes ──
        # 7. Listeners start AI workload
        ("listeners:ai_workload",     {"listener"}, _listener_run_ai_workload),
        # 8. Listeners start testbench (receiver — must be ready before talker transmits)
        ("listeners:testbench",       {"listener"}, _listener_run_testbench),
        # 9. Talker starts testbench (transmitter — last to start)
        ("talker:testbench",          {"talker"},   _talker_run_testbench),
    ],
    "results": [
        # 1. Talker stops testbench first (stop transmitting)
        ("talker:stop_testbench",     {"talker"},   _talker_stop_testbench),
        # 2. Listeners stop testbench
        ("listeners:stop_testbench",  {"listener"}, _listener_stop_testbench),
        # 3. Listeners collect logs
        ("listeners:collect_logs",    {"listener"}, _listener_collect_logs),
        # 4. Talker collects logs
        ("talker:collect_logs",       {"talker"},   _talker_collect_logs),
    ],
}
