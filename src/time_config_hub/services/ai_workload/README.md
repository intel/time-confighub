# `ai_workload` — AI Workload Service

Manages AI workload **setup** and **benchmark runtime** on a single DUT target.
One `AIWorkload` instance is created per DUT by the orchestrator.

---

## Package layout

```
ai_workload/
├── __init__.py      Public API surface
├── service.py       AIWorkload — main entry point (setup + runtime)
├── installer.py     AIWorkloadInstaller — threaded setup worker
├── runner.py        AIWorkloadRunner — threaded benchmark loop
├── setup.py         build_setup_steps / build_verify_steps / SETUP_TASK_NAMES
├── config.py        AIWorkloadConfig — all tunable parameters with defaults
├── state.py         Shared types: ServiceResult, StepStatus, WorkloadState,
│                    InstallProgress, BenchmarkProgress, _InstallState, _RunState
├── helper.py        _run_cmds — executes command dicts via ExecutionTransport
└── run.py           Low-level benchmark primitives (_start_benchmark, _stop_benchmark)
```

---

## Two-phase lifecycle

```mermaid
stateDiagram-v2
    direction LR
    [*] --> Idle

    state "Setup phase" as Setup {
        Idle --> Installing : install()
        Installing --> Done : all steps OK
        Installing --> Error : step failed
        Installing --> Cancelled : cancel_install()
    }

    state "Runtime phase" as Runtime {
        Done --> Verifying : start(duration_s)
        Verifying --> Benchmarking : env checks pass
        Verifying --> Error2 : env check failed
        Benchmarking --> Done2 : all unit-runs complete
        Benchmarking --> Cancelled2 : stop() called early
    }

    Error --> [*]
    Error2 --> [*]
    Cancelled --> [*]
    Done2 --> [*]
    Cancelled2 --> [*]
```

---

## Setup phase — step sequence

`install()` spawns a daemon thread that runs these steps in order.
Steps tagged **verify** are also reused by `start()` before the benchmark.

```mermaid
flowchart TD
    A([install called]) --> S1
    S1["① Check system\n(Ubuntu + Python ≥ 3.10)"]:::verify --> S2
    S2["② Install apt dependencies"] --> S3
    S3["③ Create Python virtual environment"] --> S4
    S4["④ Upgrade pip"] --> S5
    S5["⑤ Install AI dependencies\n(openvino, onnx, torchvision, nncf…)"] --> S6
    S6["⑥ Verify installed packages"]:::verify --> S7
    S7["⑦ Export ResNet-50 to ONNX"] --> S8
    S8["⑧ Convert ONNX → FP32 IR (ovc)"] --> S9
    S9["⑨ Quantize FP32 → INT8 (NNCF)"] --> S10
    S10["⑩ Install Intel GPU driver\n(intel-opencl-icd)"] --> S11
    S11["⑪ Install OpenCL ICD loader\n(ocl-icd-libopencl1)"] --> S12
    S12["⑫ Verify OpenCL installation"]:::verify --> S13
    S13["⑬ Verify INT8 model on disk"]:::verify --> S14
    S14["⑭ Run 10-second validation benchmark"] --> Z([Done])

    classDef verify fill:#d4edda,stroke:#28a745,color:#155724
```

> **Green** steps are verification-only steps reused by `start()` via `build_verify_steps()`.

---

## Class relationships

`AIWorkload` is the per-DUT **facade**. It owns one `AIWorkloadInstaller` and
one `AIWorkloadRunner` — both created at construction time and bound to the
same `AIWorkloadConfig` instance. Both are **internal collaborators** (not for
direct use); `AIWorkload` delegates the full setup phase to `AIWorkloadInstaller`
and the benchmark runtime to `AIWorkloadRunner`.

```mermaid
classDiagram
    class AIWorkload {
        <<facade · per DUT>>
        +install() None
        +get_install_progress() InstallProgress
        +cancel_install() None
        +start(duration_s) None
        +get_run_progress() BenchmarkProgress
        +stop() None
        +collect_logs() list[str]
    }

    class AIWorkloadRunner {
        <<internal · benchmark runtime>>
        +start(duration_s) ServiceResult
        +stop() ServiceResult
        +get_progress() ServiceResult
    }

    class AIWorkloadInstaller {
        <<internal · setup phase>>
        +start() ServiceResult
        +cancel() ServiceResult
        +get_progress() ServiceResult
    }

    class AIWorkloadConfig {
        <<config · required · single source of truth>>
        +venv_base_dir str
        +openvino_version str
        +bench_duration_s int
        +bench_device str
    }

    class _InstallState {
        <<internal · setup progress>>
    }

    class _RunState {
        <<internal · benchmark progress>>
    }

    %% ── AIWorkload facade (config required at construction) ────────────────
    AIWorkload *-- AIWorkloadInstaller : owns (setup phase)
    AIWorkload *-- AIWorkloadRunner : owns (benchmark runtime)
    AIWorkloadConfig --> AIWorkload : required
    AIWorkloadConfig --> AIWorkloadRunner : required
    AIWorkloadConfig --> AIWorkloadInstaller : required

    %% ── Internal state ──────────────────────────────────────────────────────
    AIWorkloadInstaller *-- _InstallState : setup progress
    AIWorkloadRunner *-- _RunState : benchmark progress
```

---

## Usage pattern

```python
from time_config_hub.services.ai_workload import AIWorkload
from time_config_hub.infra.execution_transport import ExecutionTransport

transport = ExecutionTransport(...)          # one per DUT
workload  = AIWorkload(transport)

# ── Setup phase ──────────────────────────────────────────────
workload.install()                          # non-blocking; spawns thread

while True:
    progress = workload.get_install_progress()
    print(progress.overall_percent, progress.state)
    if progress.state in ("done", "error", "cancelled"):
        break
    time.sleep(2)

# ── Runtime phase ────────────────────────────────────────────
workload.start(duration_s=30)              # verify env, then run benchmark

metrics = workload.get_run_progress()      # BenchmarkProgress
print(metrics.latency_avg_us, metrics.throughput_fps)

workload.stop()
logs = workload.collect_logs()             # retrieves report JSON from DUT
```

---

## State and progress types

| Type | Returned by | Purpose |
|---|---|---|
| `ServiceResult` | `installer.*`, `runner.*` | Wrapper: `status_code`, `output`, `error`, `data` |
| `InstallProgress` | `get_install_progress()` | Install snapshot: `state`, `overall_percent`, `steps[]` |
| `BenchmarkProgress` | `get_run_progress()` | Metrics snapshot: `run_index`, `total_runs`, `percent_complete`, latency, throughput |
| `StepStatus` | `StepDict.status` | `PENDING → RUNNING → DONE / FAILED / CANCELLED` |
| `WorkloadState` | `_InstallState.state`, `_RunState.state` | `NOT_STARTED → RUNNING → DONE / ERROR / CANCELLED` |

---

## Configuration

All parameters have sensible defaults — `AIWorkloadConfig()` is fully
default-constructible.  Override only what you need:

```python
from time_config_hub.services.ai_workload import AIWorkload
from time_config_hub.services.ai_workload.config import AIWorkloadConfig

config = AIWorkloadConfig(
    venv_base_dir="/opt/custom",
    bench_duration_s=60,
    bench_device="GPU",
)
workload = AIWorkload(transport, config=config)
```

Key defaults:

| Parameter | Default | Description |
|---|---|---|
| `venv_base_dir` | `/opt/tch` | Root install directory on target |
| `openvino_version` | `2026.1.0` | OpenVINO pip version |
| `bench_duration_s` | `5` | Per-run benchmark duration (seconds) |
| `bench_device` | `CPU` | OpenVINO inference device |
| `bench_cpu_cores` | `"4,5"` | CPU core affinity for `taskset` |
