# SPDX-FileCopyrightText: 2026 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause

"""
AI Workload configuration dataclass.

:class:`AIWorkloadConfig` is the single source of truth for all AI workload
parameters.  All file-system paths are derived from :attr:`~AIWorkloadConfig.venv_base_dir`
via read-only properties, ensuring consistent resolution when the base
directory is customised at construction time.

Callers instantiate :class:`AIWorkloadConfig` with their chosen parameters
and pass it to :class:`~.installer.AIWorkloadInstaller` and
:class:`~.runner.AIWorkloadRunner`.  No global constants are used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple


@dataclass
class AIWorkloadConfig:
    """Typed configuration for the AI workload library.

    All tunable parameters are declared as dataclass fields with sensible
    defaults.  File-system paths are exposed as read-only properties derived
    from :attr:`venv_base_dir`, so all paths move together when the root
    directory changes.

    :param str venv_base_dir: Root installation directory on the target.
        All paths are derived from this value.
    :param str openvino_version: OpenVINO package version to install.
    :param str onnx_version: ONNX package version to install.
    :param str torchvision_version: torchvision package version to install.
    :param str onnxscript_version: onnxscript package version to install.
    :param str nncf_version: NNCF package version to install.
    :param int bench_duration_s: Benchmark duration in seconds.
    :param str bench_device: OpenVINO inference device (e.g. ``"CPU"``).
    :param str bench_cpu_cores: CPU core affinity for ``taskset`` (e.g. ``"4,5"``).
    :param int bench_batch: Batch size for benchmark_app.
    :param int quick_bench_batch: Batch size for the quick validation benchmark.
    :param int quick_bench_duration_s: Duration for the quick validation benchmark.
    :param tuple min_python: Minimum required Python version as ``(major, minor)``.
    """

    # ── Installation root ─────────────────────────────────────────────────────
    venv_base_dir: str = "/opt/tch"

    # ── Package version pins ──────────────────────────────────────────────────
    openvino_version: str = "2026.1.0"
    onnx_version: str = "1.21.0"
    torchvision_version: str = "0.26.0"
    onnxscript_version: str = "0.6.2"
    nncf_version: str = "3.1.0"

    # ── Benchmark parameters ──────────────────────────────────────────────────
    bench_duration_s: int = 5
    bench_device: str = "CPU"
    bench_cpu_cores: str = "4,5"
    bench_batch: int = 16
    quick_bench_batch: int = 1
    quick_bench_duration_s: int = 10
    min_python: Tuple[int, int] = field(default_factory=lambda: (3, 10))

    # ── Derived path properties ───────────────────────────────────────────────

    @property
    def app_base_dir(self) -> Path:
        """Root installation directory as a :class:`~pathlib.Path`.

        :rtype: Path
        """
        return Path(self.venv_base_dir)

    @property
    def venv_dir(self) -> Path:
        """Python virtual environment directory.

        :rtype: Path
        """
        return self.app_base_dir / "ai_venv"

    @property
    def python(self) -> Path:
        """Python interpreter inside the virtual environment.

        :rtype: Path
        """
        return self.venv_dir / "bin" / "python"

    @property
    def pip(self) -> Path:
        """``pip`` binary inside the virtual environment.

        :rtype: Path
        """
        return self.venv_dir / "bin" / "pip"

    @property
    def ovc(self) -> Path:
        """``ovc`` (OpenVINO model converter) binary inside the virtual environment.

        :rtype: Path
        """
        return self.venv_dir / "bin" / "ovc"

    @property
    def bench_app(self) -> Path:
        """``benchmark_app`` binary inside the virtual environment.

        :rtype: Path
        """
        return self.venv_dir / "bin" / "benchmark_app"

    @property
    def onnx_model(self) -> Path:
        """Target path for the exported ResNet-50 ONNX model.

        :rtype: Path
        """
        return self.app_base_dir / "public" / "resnet-50-pytorch" / "resnet-v1-50.onnx"

    @property
    def fp32_dir(self) -> Path:
        """Directory for the FP32 OpenVINO IR model.

        :rtype: Path
        """
        return self.app_base_dir / "public" / "resnet-50-pytorch" / "FP32"

    @property
    def fp32_xml(self) -> Path:
        """FP32 OpenVINO IR model XML file path.

        :rtype: Path
        """
        return self.fp32_dir / "resnet-50.xml"

    @property
    def int8_dir(self) -> Path:
        """Directory for the INT8 OpenVINO IR model.

        :rtype: Path
        """
        return self.app_base_dir / "public" / "resnet-50-pytorch" / "INT8"

    @property
    def int8_xml(self) -> Path:
        """INT8 OpenVINO IR model XML file path.

        :rtype: Path
        """
        return self.int8_dir / "resnet-50.xml"

    @property
    def bench_dir(self) -> Path:
        """Benchmark working directory.

        :rtype: Path
        """
        return self.app_base_dir / "ai_benchmark"

    @property
    def report_dir(self) -> Path:
        """Directory where benchmark_app writes its results.

        :rtype: Path
        """
        return self.bench_dir / "results"

    @property
    def report_json(self) -> Path:
        """Full path to the benchmark JSON report file.

        :rtype: Path
        """
        return self.report_dir / "benchmark_report.json"

    # ── Package specifier helpers ─────────────────────────────────────────────

    @property
    def pkg_openvino(self) -> str:
        """Pinned ``openvino`` pip specifier.

        :rtype: str
        """
        return f"openvino=={self.openvino_version}"

    @property
    def pkg_onnx(self) -> str:
        """Pinned ``onnx`` pip specifier.

        :rtype: str
        """
        return f"onnx=={self.onnx_version}"

    @property
    def pkg_torchvision(self) -> str:
        """Pinned ``torchvision`` pip specifier.

        :rtype: str
        """
        return f"torchvision=={self.torchvision_version}"

    @property
    def pkg_onnxscript(self) -> str:
        """Pinned ``onnxscript`` pip specifier.

        :rtype: str
        """
        return f"onnxscript=={self.onnxscript_version}"

    @property
    def pkg_nncf(self) -> str:
        """Pinned ``nncf`` pip specifier.

        :rtype: str
        """
        return f"nncf=={self.nncf_version}"
