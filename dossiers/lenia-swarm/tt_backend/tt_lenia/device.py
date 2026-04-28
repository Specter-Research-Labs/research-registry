"""Tenstorrent device management for multi-card batch parallelism."""

from __future__ import annotations

import multiprocessing as mp
import os
import re
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from .config import BatchedConfig, CompiledKernels
from .topology import get_available_pcie_device_ids


ExecutionMode = Literal["single", "fleet", "mesh"]
ExecutionStrategy = Literal[
    "single-device",
    "fleet-independent",
    "mesh-replicated-spmd",
]

_TT_RUNTIME_ENV_KEYS = (
    "TT_VISIBLE_DEVICES",
    "TT_METAL_CACHE",
    "TT_METAL_INSPECTOR",
    "TT_METAL_INSPECTOR_RPC",
    "TT_METAL_SLOW_DISPATCH_MODE",
    "LENIA_TT_MESH_DFT",
)


def _uses_ttnn_runtime(backend: str) -> bool:
    return backend == "tt"


def split_visible_devices(spec: str | None) -> tuple[str, ...]:
    if spec is None:
        return ()
    return tuple(token.strip() for token in spec.split(",") if token.strip())


def infer_mesh_shape_from_visible_devices(
    visible_devices: str | list[str] | tuple[str, ...] | None,
    mesh_shape: tuple[int, int] | None = None,
) -> tuple[int, int] | None:
    if mesh_shape is not None:
        return mesh_shape
    if isinstance(visible_devices, str):
        devices = split_visible_devices(visible_devices)
    elif visible_devices is None:
        devices = ()
    else:
        devices = tuple(str(token).strip() for token in visible_devices if str(token).strip())
    if devices:
        # QuietBox exposes one PCIe device node per N300 card; each card contributes
        # two Wormhole chips to the TTNN mesh.
        return (1, 2 * len(devices))
    return None


def resolve_execution_mode(
    *,
    execution_mode: str,
    device_list: list[str],
    visible_devices: str | None,
    mesh_shape: tuple[int, int] | None,
) -> ExecutionMode:
    if execution_mode not in {"single", "fleet", "mesh"}:
        raise ValueError(f"Unknown TT execution mode {execution_mode!r}.")
    mode = execution_mode
    n_visible = len(split_visible_devices(visible_devices)) if visible_devices is not None else len(device_list)
    if mode == "single" and (mesh_shape is not None or n_visible > 1):
        raise ValueError("single execution mode accepts at most one TT device and no mesh shape.")
    if mode == "fleet" and mesh_shape is not None:
        raise ValueError("fleet execution mode runs independent sims and does not accept --mesh-shape.")
    if mode == "fleet" and n_visible < 1:
        raise ValueError("fleet execution mode requires --device-list or --tt-visible-devices.")
    if mode == "mesh" and n_visible < 1 and mesh_shape is None:
        raise ValueError("mesh execution mode requires --device-list, --tt-visible-devices, or --mesh-shape.")
    return mode  # type: ignore[return-value]


def resolve_runtime_device_selection(
    *,
    backend: str,
    execution_mode: ExecutionMode = "single",
    device_list: list[str],
    visible_devices: str | None,
    mesh_shape: tuple[int, int] | None,
) -> tuple[str | None, tuple[int, int] | None]:
    resolved_visible_devices = visible_devices
    if resolved_visible_devices is None and device_list:
        resolved_visible_devices = ",".join(device_list)
    resolved_mesh_shape = mesh_shape
    if _uses_ttnn_runtime(backend) and execution_mode == "mesh":
        resolved_mesh_shape = infer_mesh_shape_from_visible_devices(
            resolved_visible_devices,
            mesh_shape=mesh_shape,
        )
    return resolved_visible_devices, resolved_mesh_shape


def resolve_execution_strategy(
    *,
    execution_mode: ExecutionMode | str,
) -> ExecutionStrategy:
    """Describe how Lenia work is partitioned across TT devices.

    This is intentionally runtime-facing metadata, not a scheduler. It keeps
    CLI output honest while we evolve mesh from replicated SPMD to true
    spatially resident execution.
    """
    if execution_mode == "single":
        return "single-device"
    if execution_mode == "fleet":
        return "fleet-independent"
    if execution_mode != "mesh":
        raise ValueError(f"Unknown TT execution mode {execution_mode!r}.")

    return "mesh-replicated-spmd"


@dataclass(frozen=True)
class DevicePartition:
    visible_device: str
    batch_start: int
    batch_end: int


@dataclass(frozen=True)
class PartitionTiming:
    visible_device: str
    batch_start: int
    batch_end: int
    elapsed_s: float


@dataclass(frozen=True)
class ParallelRunResult:
    mass: np.ndarray
    elapsed_s: float
    partitions: tuple[PartitionTiming, ...]


def parallel_elapsed_s(timings: list[PartitionTiming] | tuple[PartitionTiming, ...]) -> float:
    """Return compute throughput time for a parallel batch run.

    Worker timings intentionally exclude per-worker warmup/compile work, matching
    the single-engine benchmark semantics.
    """
    if not timings:
        return 0.0
    return max(timing.elapsed_s for timing in timings)


class PersistentBatchRunner:
    """Keep one engine open per visible device for many independent runs."""

    def __init__(
        self,
        *,
        backend: str,
        config: BatchedConfig,
        kernels: CompiledKernels,
        visible_devices: list[str],
    ):
        if not visible_devices:
            raise ValueError("PersistentBatchRunner requires at least one visible device.")
        if backend != "tt":
            raise ValueError(f"PersistentBatchRunner only supports TT runtime backends, got {backend}.")
        self.backend = backend
        self.config = config
        self.kernels = kernels
        self.visible_devices = tuple(visible_devices)
        self._ctx = mp.get_context("spawn")
        self._workers: list[tuple[str, mp.connection.Connection, mp.Process]] = []

        for visible_device in self.visible_devices:
            self._workers.append(
                _launch_worker_process(
                    backend=backend,
                    config=config,
                    kernels=kernels,
                    visible_device=visible_device,
                    context=self._ctx,
                )
            )

    def close(self) -> None:
        if not hasattr(self, "_workers"):
            return
        for _, conn, process in self._workers:
            _close_worker_process(conn, process)
        self._workers.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def __del__(self) -> None:
        self.close()

    def run(self, mass: np.ndarray, *, warmup: int = 0, steps: int) -> ParallelRunResult:
        if mass.ndim != 4:
            raise ValueError(f"Expected mass with shape [batch, sx, sy, channels], got {mass.shape}")
        if mass.shape[0] == 0:
            raise ValueError("Batch must be non-empty for multi-device execution.")
        if steps < 0 or warmup < 0:
            raise ValueError(f"warmup and steps must be >= 0, got warmup={warmup}, steps={steps}")

        partitions = plan_partitions(mass.shape[0], list(self.visible_devices))
        worker_map = {visible_device: conn for visible_device, conn, _ in self._workers}

        for partition in partitions:
            worker_map[partition.visible_device].send(
                {
                    "op": "run",
                    "warmup": warmup,
                    "steps": steps,
                    "partition": partition,
                    "mass": mass[partition.batch_start : partition.batch_end].copy(),
                }
            )

        results = []
        for partition in partitions:
            message = worker_map[partition.visible_device].recv()
            if message.get("status") != "ok":
                raise RuntimeError(message.get("traceback", message.get("error", "Persistent worker failed.")))
            results.append((message["timing"], message["mass"]))

        final_mass = np.empty_like(mass)
        timings = []
        for timing, partition_mass in sorted(results, key=lambda item: item[0].batch_start):
            final_mass[timing.batch_start : timing.batch_end] = partition_mass
            timings.append(timing)
        return ParallelRunResult(mass=final_mass, elapsed_s=parallel_elapsed_s(timings), partitions=tuple(timings))

    def run_sampled(
        self,
        mass: np.ndarray,
        *,
        warmup: int = 0,
        steps: int,
        sample_steps: set[int],
        on_sample,
    ) -> ParallelRunResult:
        if not sample_steps:
            return self.run(mass, warmup=warmup, steps=steps)
        if mass.ndim != 4:
            raise ValueError(f"Expected mass with shape [batch, sx, sy, channels], got {mass.shape}")
        if mass.shape[0] == 0:
            raise ValueError("Batch must be non-empty for multi-device execution.")
        if steps < 0 or warmup < 0:
            raise ValueError(f"warmup and steps must be >= 0, got warmup={warmup}, steps={steps}")

        partitions = plan_partitions(mass.shape[0], list(self.visible_devices))
        worker_map = {visible_device: conn for visible_device, conn, _ in self._workers}

        samples = {int(step) for step in sample_steps if 0 <= int(step) <= steps}
        for partition in partitions:
            worker_map[partition.visible_device].send(
                {
                    "op": "run_sampled",
                    "warmup": warmup,
                    "steps": steps,
                    "sample_steps": samples,
                    "partition": partition,
                    "mass": mass[partition.batch_start : partition.batch_end].copy(),
                }
            )

        results = []
        sampled_partitions: dict[int, np.ndarray] = {}
        for partition in partitions:
            message = worker_map[partition.visible_device].recv()
            if message.get("status") != "ok":
                raise RuntimeError(message.get("traceback", message.get("error", "Persistent worker failed.")))
            timing = message["timing"]
            results.append((timing, message["mass"]))
            for step, partition_sample in message.get("samples", ()):
                sample = sampled_partitions.get(step)
                if sample is None:
                    sample = np.empty_like(mass)
                    sampled_partitions[step] = sample
                sample[timing.batch_start : timing.batch_end] = partition_sample

        for step in sorted(sampled_partitions):
            on_sample(step, sampled_partitions[step])

        final_mass = np.empty_like(mass)
        timings = []
        for timing, partition_mass in sorted(results, key=lambda item: item[0].batch_start):
            final_mass[timing.batch_start : timing.batch_end] = partition_mass
            timings.append(timing)
        return ParallelRunResult(mass=final_mass, elapsed_s=parallel_elapsed_s(timings), partitions=tuple(timings))


def _make_engine(*args, **kwargs):
    from .backends import make_runtime_engine

    return make_runtime_engine(*args, **kwargs)


def _close_engine(engine) -> None:
    close = getattr(engine, "close", None)
    if callable(close):
        close()


def get_available_devices() -> list[int]:
    """Return PCIe-visible Tenstorrent device ids for TT_VISIBLE_DEVICES."""
    try:
        return get_available_pcie_device_ids()
    except ImportError:
        return []


def is_mesh_device(device) -> bool:
    try:
        import ttnn
    except ImportError:
        return False
    multi_device = getattr(getattr(ttnn, "_ttnn", None), "multi_device", None)
    mesh_type = getattr(multi_device, "MeshDevice", None)
    return mesh_type is not None and isinstance(device, mesh_type)


def parse_mesh_shape(spec: str | None) -> tuple[int, int] | None:
    if spec is None:
        return None
    value = spec.strip()
    if not value:
        raise ValueError("Mesh shape cannot be empty.")
    rows_text, cols_text = (part.strip() for part in value.split(",", maxsplit=1))
    rows = int(rows_text)
    cols = int(cols_text)
    if rows <= 0 or cols <= 0:
        raise ValueError(f"Mesh shape entries must be > 0, got {spec}.")
    return rows, cols


def open_ttnn_device(
    *,
    device_id: int = 0,
    mesh_shape: tuple[int, int] | None = None,
):
    import ttnn

    if hasattr(ttnn, "CONFIG"):
        ttnn.CONFIG.throw_exception_on_fallback = True
    if mesh_shape is not None:
        fabric = ttnn.FabricConfig.FABRIC_1D if mesh_shape[0] == 1 else ttnn.FabricConfig.FABRIC_2D
        ttnn.set_fabric_config(fabric)
        return ttnn.open_mesh_device(ttnn.MeshShape(*mesh_shape))
    return ttnn.open_device(device_id=device_id)


def close_ttnn_device(device) -> None:
    import ttnn

    try:
        if is_mesh_device(device):
            try:
                for mesh_device in device.get_devices():
                    ttnn.synchronize_device(mesh_device)
            except Exception:
                pass
        else:
            try:
                ttnn.synchronize_device(device)
            except Exception:
                pass
    except Exception:
        pass

    if is_mesh_device(device):
        ttnn.close_mesh_device(device)
        return
    ttnn.close_device(device)


def get_mesh_size(device) -> int:
    if not is_mesh_device(device):
        return 1
    return int(device.get_num_devices())


def _worker_cache_path(visible_device: str) -> str:
    root = Path(os.environ.get("TT_METAL_CACHE_ROOT", Path.home() / ".cache" / "tt_metal_lenia"))
    cache_key = re.sub(r"[^0-9A-Za-z]+", "_", visible_device).strip("_")
    cache_path = root / f"pcie_{cache_key}"
    cache_path.mkdir(parents=True, exist_ok=True)
    return str(cache_path)


def apply_tt_runtime_env(
    *,
    visible_device: str | None = None,
    mesh_dft: bool | None = None,
) -> dict[str, str | None]:
    previous = {key: os.environ.get(key) for key in _TT_RUNTIME_ENV_KEYS}
    os.environ["TT_METAL_INSPECTOR"] = "0"
    os.environ["TT_METAL_INSPECTOR_RPC"] = "0"
    if os.environ.get("LENIA_TT_ALLOW_SLOW_DISPATCH") != "1":
        os.environ.pop("TT_METAL_SLOW_DISPATCH_MODE", None)
    if mesh_dft is not None:
        if mesh_dft:
            os.environ["LENIA_TT_MESH_DFT"] = "1"
        else:
            os.environ.pop("LENIA_TT_MESH_DFT", None)
    if visible_device is not None:
        os.environ["TT_VISIBLE_DEVICES"] = visible_device
        os.environ["TT_METAL_CACHE"] = _worker_cache_path(visible_device)
    return previous


def restore_tt_runtime_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _launch_worker_process(
    *,
    backend: str,
    config: BatchedConfig,
    kernels: CompiledKernels,
    visible_device: str,
    context,
) -> tuple[str, mp.connection.Connection, mp.Process]:
    parent_conn, child_conn = context.Pipe()
    process = context.Process(
        name=f"lenia-tt-{backend}-{visible_device}",
        target=_persistent_worker_loop,
        kwargs=dict(
            backend=backend,
            config=config,
            kernels=kernels,
            visible_device=visible_device,
            control=child_conn,
        ),
    )
    process.start()
    child_conn.close()
    ready = parent_conn.recv()
    if ready.get("status") != "ready":
        _close_worker_process(parent_conn, process)
        raise RuntimeError(ready.get("traceback", ready.get("error", "Persistent worker failed to start.")))
    return visible_device, parent_conn, process


def _close_worker_process(conn, process) -> None:
    try:
        conn.send({"op": "close"})
    except (BrokenPipeError, EOFError, OSError):
        pass
    try:
        conn.close()
    except OSError:
        pass
    process.join(timeout=5.0)
    if process.is_alive():
        process.kill()
        process.join(timeout=1.0)


def parse_device_list(spec: str | None) -> list[str]:
    """Parse a comma-separated device list or discover the local fleet."""
    if spec is None:
        return []
    value = spec.strip()
    if not value:
        raise ValueError("Device list cannot be empty.")
    if value == "auto":
        devices = [str(device) for device in get_available_devices()]
        if not devices:
            raise ValueError("Could not auto-discover any Tenstorrent devices.")
        return devices
    devices = [token.strip() for token in value.split(",") if token.strip()]
    if not devices:
        raise ValueError("Device list must contain at least one device id.")
    if len(set(devices)) != len(devices):
        raise ValueError(f"Device list contains duplicates: {spec}")
    return devices


def assign_batches(total_batch: int, n_devices: int) -> list[range]:
    """Split batch dimension evenly across devices."""
    if total_batch <= 0:
        raise ValueError(f"total_batch must be > 0, got {total_batch}")
    if n_devices <= 0:
        raise ValueError(f"n_devices must be > 0, got {n_devices}")
    per_device = total_batch // n_devices
    remainder = total_batch % n_devices
    ranges = []
    start = 0
    for i in range(n_devices):
        size = per_device + (1 if i < remainder else 0)
        ranges.append(range(start, start + size))
        start += size
    return ranges


def plan_partitions(total_batch: int, visible_devices: list[str]) -> list[DevicePartition]:
    """Assign non-empty batch slices to specific visible devices."""
    partitions = []
    for visible_device, batch_range in zip(visible_devices, assign_batches(total_batch, len(visible_devices))):
        if len(batch_range) == 0:
            continue
        partitions.append(
            DevicePartition(
                visible_device=visible_device,
                batch_start=batch_range.start,
                batch_end=batch_range.stop,
            )
        )
    return partitions


def _persistent_worker_loop(
    *,
    backend: str,
    config: BatchedConfig,
    kernels: CompiledKernels,
    visible_device: str,
    control,
):
    previous_env = apply_tt_runtime_env(visible_device=visible_device) if backend == "tt" else {}

    device = None
    engine = None
    try:
        if _uses_ttnn_runtime(backend):
            import ttnn

            device = ttnn.open_device(device_id=0)
            engine = _make_engine(backend, config, kernels, device=device)
        else:
            raise ValueError(f"Unsupported TT runtime backend for persistent worker path: {backend}")

        control.send({"status": "ready"})
        while True:
            message = control.recv()
            if message["op"] == "close":
                break
            if message["op"] not in {"run", "run_sampled"}:
                raise ValueError(f"Unknown worker op: {message['op']}")
            partition = message["partition"]
            state = message["mass"]
            if message["warmup"] > 0:
                state = engine.run(state, message["warmup"])
            t0 = time.perf_counter()
            samples = []
            if message["op"] == "run_sampled":
                run_sampled = getattr(engine, "run_sampled", None)
                if callable(run_sampled):
                    state = run_sampled(
                        state,
                        message["steps"],
                        message["sample_steps"],
                        lambda step, sample: samples.append((int(step), sample.copy())),
                    )
                else:
                    sample_steps = set(message["sample_steps"])
                    if 0 in sample_steps:
                        samples.append((0, state.copy()))
                    for step in range(1, message["steps"] + 1):
                        state = engine.step(state).mass
                        if step in sample_steps:
                            samples.append((step, state.copy()))
            else:
                state = engine.run(state, message["steps"])
            elapsed_s = time.perf_counter() - t0
            control.send(
                {
                    "status": "ok",
                    "timing": PartitionTiming(
                        visible_device=partition.visible_device,
                        batch_start=partition.batch_start,
                        batch_end=partition.batch_end,
                        elapsed_s=elapsed_s,
                    ),
                    "mass": state,
                    "samples": samples,
                }
            )
    except Exception as exc:
        control.send({"status": "error", "error": repr(exc), "traceback": traceback.format_exc()})
    finally:
        try:
            control.close()
        except OSError:
            pass
        if engine is not None:
            _close_engine(engine)
        if device is not None:
            close_ttnn_device(device)
        restore_tt_runtime_env(previous_env)


def run_batch_parallel(
    *,
    backend: str,
    config: BatchedConfig,
    kernels: CompiledKernels,
    mass: np.ndarray,
    visible_devices: list[str],
    warmup: int = 0,
    steps: int,
) -> ParallelRunResult:
    """Run an independent batch slice on each selected device in parallel."""
    if mass.ndim != 4:
        raise ValueError(f"Expected mass with shape [batch, sx, sy, channels], got {mass.shape}")
    if mass.shape[0] == 0:
        raise ValueError("Batch must be non-empty for multi-device execution.")
    if steps < 0 or warmup < 0:
        raise ValueError(f"warmup and steps must be >= 0, got warmup={warmup}, steps={steps}")
    partitions = plan_partitions(mass.shape[0], visible_devices)
    if not partitions:
        raise ValueError("No non-empty device partitions were created.")

    context = mp.get_context("spawn")
    workers: list[tuple[DevicePartition, mp.connection.Connection, mp.Process]] = []
    try:
        for partition in partitions:
            _, conn, process = _launch_worker_process(
                backend=backend,
                config=config,
                kernels=kernels,
                visible_device=partition.visible_device,
                context=context,
            )
            workers.append((partition, conn, process))

        for partition, conn, _ in workers:
            conn.send(
                {
                    "op": "run",
                    "warmup": warmup,
                    "steps": steps,
                    "partition": partition,
                    "mass": mass[partition.batch_start : partition.batch_end].copy(),
                }
            )

        results = []
        for _, conn, _ in workers:
            message = conn.recv()
            if message.get("status") != "ok":
                raise RuntimeError(message.get("traceback", message.get("error", "Worker failed.")))
            results.append((message["timing"], message["mass"]))
    finally:
        for _, conn, process in workers:
            _close_worker_process(conn, process)

    final_mass = np.empty_like(mass)
    timings = []
    for timing, partition_mass in sorted(results, key=lambda item: item[0].batch_start):
        final_mass[timing.batch_start : timing.batch_end] = partition_mass
        timings.append(timing)
    return ParallelRunResult(mass=final_mass, elapsed_s=parallel_elapsed_s(timings), partitions=tuple(timings))
