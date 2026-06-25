# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
AI Workload setup step definitions.

Provides :func:`build_setup_steps` and :func:`build_verify_steps` which
construct ordered step lists for the AI workload installer.  All paths and
version pins are derived from the supplied :class:`~.config.AIWorkloadConfig`
so there are no module-level globals.

Each step dict has the following shape::

    {
        "name": str,           # human-readable step label
        "cmds": [              # ordered list of command dicts
            {
                "info": str,           # label for the command
                "cmd": list | str,     # command as list[str] or shell string
                "timeout": int,        # seconds; default 60
                "expect_stdout": str,  # (optional) stdout must contain this
                "skip_if_stdout": str, # (optional) skip step if probe matches
            },
            ...
        ],
    }

Steps are executed on the target via
:class:`~time_config_hub.infra.execution_transport.ExecutionTransport`
(local or remote), so they work for both local and remote DUT targets.

Public API
----------
build_setup_steps   : Build the full ordered step list from a config.
build_verify_steps  : Build the read-only verification subset from a config.
SETUP_TASK_NAMES    : Ordered list of step name strings (derived from build_setup_steps).
"""

from __future__ import annotations

import logging

from .config import AIWorkloadConfig

_log = logging.getLogger("ai_workload_lib.setup")


# ── Step builders ─────────────────────────────────────────────────────────────


def build_setup_steps(config: AIWorkloadConfig) -> list[dict]:
    """Build the ordered setup step list from *config*.

    All paths, version pins, and benchmark parameters are resolved from
    *config* at call time.  The returned list is safe to pass directly to
    :class:`~.installer.AIWorkloadInstaller`.

    :param AIWorkloadConfig config: Configuration to resolve paths and
        package versions from.
    :return: Ordered list of step dicts.
    :rtype: list[dict]
    """
    py = str(config.python)
    pip = str(config.pip)
    ovc = str(config.ovc)
    bench = str(config.bench_app)
    onnx = str(config.onnx_model)
    fp32_xml = str(config.fp32_xml)
    fp32_dir = str(config.fp32_dir)
    int8_xml = str(config.int8_xml)
    int8_bin = str(config.int8_xml).replace(".xml", ".bin")
    int8_dir = str(config.int8_dir)
    report_dir = str(config.report_dir)
    venv_dir = str(config.venv_dir)
    min_py = f"({config.min_python[0]}, {config.min_python[1]})"

    export_onnx_script = (
        "import torch, torchvision.models as models, warnings; "
        "warnings.filterwarnings('ignore'); "
        "model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1); "
        "model.eval(); "
        "dummy = torch.randn(1, 3, 224, 224); "
        f"torch.onnx.export(model, dummy, '{onnx}', "
        "input_names=['data'], output_names=['prob'], "
        f"dynamic_axes={{'data': {{0: 'batch'}}, 'prob': {{0: 'batch'}}}}, "
        "opset_version=13, do_constant_folding=True); "
        "print('Exported resnet-v1-50.onnx')"
    )

    quantize_int8_script = (
        f"import nncf, openvino as ov, numpy as np, os; "
        f"np.random.seed(42); "
        f"cal = [{{'data': np.random.randn(1, 3, 224, 224).astype(np.float32)}} for _ in range(300)]; "
        f"core = ov.Core(); "
        f"model = core.read_model('{fp32_xml}'); "
        f"q = nncf.quantize(model, nncf.Dataset(cal)); "
        f"os.makedirs('{int8_dir}', exist_ok=True); "
        f"ov.save_model(q, '{int8_xml}'); "
        f"print('INT8 saved')"
    )

    return [
        {
            "name": "Check system (Ubuntu + Python >= 3.10)",
            "verify": True,
            "cmds": [
                {
                    "info": "Verify Ubuntu OS",
                    "cmd": "grep -qi ubuntu /etc/os-release && echo ubuntu_ok",
                    "timeout": 60,
                    "expect_stdout": "ubuntu_ok",
                },
                {
                    "info": f"Verify Python >= {config.min_python[0]}.{config.min_python[1]}",
                    "cmd": (
                        f'python3 -c "import sys; '
                        f"print('py_ok' if sys.version_info >= {min_py} else 'py_old')\""
                    ),
                    "timeout": 60,
                    "expect_stdout": "py_ok",
                },
            ],
        },
        {
            "name": "Install apt dependencies",
            "cmds": [
                {
                    "info": "Install python3-venv (provides ensurepip, required by venv)",
                    "cmd": "apt-get install -y python3-venv",
                    "timeout": 300,
                },
                {
                    "info": "Install python3-pip (ensures pip is available for venv bootstrap)",
                    "cmd": "apt-get install -y python3-pip",
                    "timeout": 300,
                },
            ],
        },
        {
            "name": "Create Python virtual environment",
            "cmds": [
                {
                    "info": "Skip if venv exists and matches system python3 version",
                    "cmd": (
                        f"test -f {py} && "
                        f"[ \"$({py} -c 'import sys; print(sys.version_info[:2])')\" = "
                        f"\"$(python3 -c 'import sys; print(sys.version_info[:2])')\" ] "
                        f"&& echo venv_ok"
                    ),
                    "timeout": 60,
                    "skip_if_stdout": "venv_ok",
                },
                {
                    "info": "Remove stale or mismatched venv if present",
                    "cmd": f"rm -rf {venv_dir}",
                    "timeout": 60,
                },
                {
                    "info": f"Create venv at {venv_dir}",
                    "cmd": f"python3 -m venv --upgrade-deps {venv_dir}",
                    "timeout": 300,
                },
            ],
        },
        {
            "name": "Upgrade pip",
            "cmds": [
                {
                    "info": "Upgrade pip, setuptools, wheel",
                    "cmd": [pip, "install", "--upgrade", "pip", "setuptools", "wheel"],
                    "timeout": 300,
                },
            ],
        },
        {
            "name": "Install AI dependencies (openvino, onnx, torchvision, nncf...)",
            "cmds": [
                {
                    "info": "Install numpy (build dependency)",
                    "cmd": [pip, "install", "-q", "--no-build-isolation", "numpy<2.5.0"],
                    "timeout": 600,
                },
                {
                    "info": "Install openvino",
                    "cmd": [pip, "install", "-q", "--no-build-isolation", config.pkg_openvino],
                    "timeout": 600,
                },
                {
                    "info": "Install onnx + onnxscript",
                    "cmd": [pip, "install", "-q", "--no-build-isolation", config.pkg_onnx, config.pkg_onnxscript],
                    "timeout": 600,
                },
                {
                    "info": "Install torchvision",
                    "cmd": [pip, "install", "-q", "--no-build-isolation", config.pkg_torchvision],
                    "timeout": 600,
                },
                {
                    "info": "Install nncf",
                    "cmd": [pip, "install", "-q", "--no-build-isolation", config.pkg_nncf],
                    "timeout": 600,
                },
            ],
        },
        {
            "name": "Verify installed packages",
            "verify": True,
            "cmds": [
                {
                    "info": "Import-check all AI packages",
                    "cmd": [
                        py,
                        "-c",
                        "import onnx, torchvision, onnxscript, nncf; print('All packages imported OK')",
                    ],
                    "timeout": 300,
                    "expect_stdout": "All packages imported OK",
                },
            ],
        },
        {
            "name": "Export ResNet-50 to ONNX",
            "cmds": [
                {
                    "info": "Skip if ONNX already exists",
                    "cmd": f"test -f {onnx} && echo exists",
                    "timeout": 60,
                    "skip_if_stdout": "exists",
                },
                {
                    "info": "Create ONNX output directory",
                    "cmd": f"mkdir -p $(dirname {onnx})",
                    "timeout": 60,
                },
                {
                    "info": "Export ResNet-50 to ONNX",
                    "cmd": [py, "-c", export_onnx_script],
                    "timeout": 600,
                    "expect_stdout": "Exported resnet-v1-50.onnx",
                },
            ],
        },
        {
            "name": "Convert ONNX -> FP32 IR (ovc)",
            "cmds": [
                {
                    "info": "Skip if FP32 IR already exists",
                    "cmd": f"test -f {fp32_xml} && echo exists",
                    "timeout": 60,
                    "skip_if_stdout": "exists",
                },
                {
                    "info": "Verify ONNX model is present",
                    "cmd": f"test -f {onnx} && echo onnx_ok",
                    "timeout": 60,
                    "expect_stdout": "onnx_ok",
                },
                {
                    "info": "Create FP32 output directory",
                    "cmd": f"mkdir -p {fp32_dir}",
                    "timeout": 60,
                },
                {
                    "info": "Convert ONNX -> FP32 IR (ovc)",
                    "cmd": [ovc, onnx, "--output_model", f"{fp32_dir}/resnet-50"],
                    "timeout": 300,
                },
            ],
        },
        {
            "name": "Quantize FP32 -> INT8 (NNCF)",
            "cmds": [
                {
                    "info": "Skip if INT8 model already exists",
                    "cmd": f"test -f {int8_xml} && echo exists",
                    "timeout": 10,
                    "skip_if_stdout": "exists",
                },
                {
                    "info": "Quantize FP32 -> INT8 (NNCF)",
                    "cmd": [py, "-c", quantize_int8_script],
                    "timeout": 600,
                    "expect_stdout": "INT8 saved",
                },
            ],
        },
        {
            "name": "Install Intel GPU driver (intel-opencl-icd)",
            "cmds": [
                {
                    "info": "Install intel-opencl-icd",
                    "cmd": ["sudo", "-n", "apt-get", "install", "-y", "intel-opencl-icd"],
                    "timeout": 600,
                },
            ],
        },
        {
            "name": "Install OpenCL ICD loader (ocl-icd-libopencl1)",
            "cmds": [
                {
                    "info": "Install ocl-icd-libopencl1",
                    "cmd": ["sudo", "-n", "apt-get", "install", "-y", "ocl-icd-libopencl1"],
                    "timeout": 300,
                },
            ],
        },
        {
            "name": "Verify OpenCL installation",
            "verify": True,
            "cmds": [
                {
                    "info": "Verify intel-opencl-icd package is installed",
                    "cmd": "dpkg -s intel-opencl-icd | grep 'Status:'",
                    "timeout": 15,
                    "expect_stdout": "install ok installed",
                },
                {
                    "info": "Verify libOpenCL is registered (best-effort)",
                    "cmd": (
                        "ldconfig -p 2>/dev/null | grep -qi opencl && echo opencl_ok || echo opencl_ok"
                    ),
                    "timeout": 10,
                },
            ],
        },
        {
            "name": "Verify INT8 model on disk",
            "verify": True,
            "cmds": [
                {
                    "info": "Verify INT8 model XML and BIN exist",
                    "cmd": f"test -f {int8_xml} && test -f {int8_bin} && echo model_ok",
                    "timeout": 10,
                    "expect_stdout": "model_ok",
                },
            ],
        },
        {
            "name": "Run 10-second validation benchmark",
            "cmds": [
                {
                    "info": "Create benchmark report directory",
                    "cmd": f"mkdir -p {report_dir}",
                    "timeout": 10,
                },
                {
                    "info": "Run 10-second validation benchmark",
                    "cmd": [
                        "taskset",
                        "-c",
                        config.bench_cpu_cores,
                        bench,
                        "-m",
                        int8_xml,
                        "-d",
                        config.bench_device,
                        "-b",
                        str(config.quick_bench_batch),
                        "-hint",
                        "tput",
                        "-t",
                        str(config.quick_bench_duration_s),
                    ],
                    "timeout": 60,
                },
            ],
        },
    ]


# ── Derived constant (single source of truth) ─────────────────────────────────

SETUP_TASK_NAMES: list[str] = [s["name"] for s in build_setup_steps(AIWorkloadConfig())]


def build_verify_steps(config: AIWorkloadConfig) -> list[dict]:
    """Build the read-only verification step subset from *config*.

    Returns the steps tagged ``"verify": True`` in :func:`build_setup_steps`
    — steps that check the environment is ready for benchmarking without
    modifying the target.

    :param AIWorkloadConfig config: Configuration to resolve paths from.
    :return: List of read-only verification step dicts.
    :rtype: list[dict]
    """
    return [s for s in build_setup_steps(config) if s.get("verify")]


# ── Module-level step lists (default config, used by service.py) ──────────────
# service.py imports these directly; they are pre-built with default config so
# the caller doesn't need to pass a config object for the common case.

_defaults = AIWorkloadConfig()
SETUP_STEPS: list[dict] = build_setup_steps(_defaults)
VERIFY_STEPS: list[dict] = build_verify_steps(_defaults)
del _defaults
