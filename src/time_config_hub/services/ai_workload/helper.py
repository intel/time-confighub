# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
time_config_hub.services.ai_workload.helper — command execution utilities.

Internal API — not exported from ``ai_workload.__init__``.
"""

from __future__ import annotations

from time_config_hub.infra.execution_transport import ExecutionTransport


def _run_cmds(cmds: list[dict], transport: ExecutionTransport) -> tuple[bool, str]:
    """Execute a list of command dicts on a transport; return ``(success, detail)``.

    :param list[dict] cmds: Ordered list of command dicts for one step.
    :param ExecutionTransport transport: Transport to execute commands on.
    :return: ``(True, detail)`` on success or skip, ``(False, error)`` on failure.
    :rtype: tuple[bool, str]
    """
    for spec in cmds:
        label = spec.get("info", "")
        cmd = spec["cmd"]
        timeout = spec.get("timeout", 60)
        skip_trigger = spec.get("skip_if_stdout")
        expect = spec.get("expect_stdout")

        # Shell strings (with &&, |, $(...) etc.) must be wrapped for subprocess
        if isinstance(cmd, str):
            cmd = ["bash", "-c", cmd]

        result = transport.run(cmd, timeout=timeout)
        stdout = result.stdout
        ok = result.success

        if skip_trigger is not None:
            if skip_trigger in stdout:
                return True, f"skipped — {label}: already done"
            continue  # probe miss; keep going

        if not ok:
            err = (result.stderr or stdout)[:200]
            return False, f"[{label}] {err}"

        if expect and expect not in stdout:
            return False, f"[{label}] expected '{expect}' in stdout: {stdout[:200]}"

    return True, "done"
