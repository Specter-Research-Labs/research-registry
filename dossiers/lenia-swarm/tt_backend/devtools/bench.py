"""Benchmark Flow Lenia throughput for a chosen backend.

Usage:
    python devtools/bench.py --grid-sizes 128 --steps 20 --backend reference
    python devtools/bench.py --grid-sizes 128 --steps 20 --backend tt --device-list 0,1,2,3
    python devtools/bench.py --grid-sizes 128 --steps 20 --backend tt --execution-mode fleet --device-list 0,1,2,3 --batch-sizes 4
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tt_lenia.backends import make_reference_engine, make_runtime_engine, uses_ttnn_runtime
from tt_lenia.config import (
    compile_kernels,
    load_config,
    resolve_connectivity,
    resolve_params,
)
from tt_lenia.device import (
    ExecutionMode,
    PersistentBatchRunner,
    apply_tt_runtime_env,
    close_ttnn_device,
    open_ttnn_device,
    parse_device_list,
    parse_mesh_shape,
    resolve_execution_mode,
    resolve_execution_strategy,
    resolve_runtime_device_selection,
    restore_tt_runtime_env,
    run_batch_parallel,
)
TRACY_REEXEC_ENV = "LENIA_TT_BENCH_TRACY_ACTIVE"
BENCH_LOCK_ENV = "LENIA_TT_BENCH_LOCK_HELD"
BENCH_LOCK_PATH = Path(os.environ.get("LENIA_TT_BENCH_LOCK_PATH", "/tmp/lenia-tt-bench.lock"))
TT_HUGEPAGE_CLEANUP = "sudo rm -f /dev/hugepages-1G/*tenstorrent"
TT_CASE_TIMEOUT_S = 180


@dataclass(frozen=True)
class BenchResult:
    elapsed_s: float
    stage_profile: dict[str, object] | None = None


@dataclass(frozen=True)
class BenchRow:
    grid_size: int
    batch_size: int
    backend_label: str
    resolved_backend: str
    ms_per_step: float
    device_label: str
    execution_strategy: str
    stage_profile: dict[str, object] | None = None


def resolve_config_path(config_path: Path | None) -> Path:
    if config_path is None:
        return Path(__file__).parents[2] / "configs" / "base" / "paper_base_3k_1c_128.json"
    if config_path.exists():
        return config_path.resolve()
    if config_path.is_absolute():
        return config_path
    repo_relative = Path(__file__).parents[2] / config_path
    if repo_relative.exists():
        return repo_relative
    return config_path


def bench_config(sx: int, sy: int, config_path: Path | None = None) -> tuple:
    config_path = resolve_config_path(config_path)
    config, raw = load_config(config_path)

    config = replace(config, sx=sx, sy=sy)
    c0, c1 = resolve_connectivity(raw)
    params = resolve_params(raw, config.nb_k)
    kernels = compile_kernels(params, config, c0, c1)
    return config, kernels


def make_mass(bs: int, gs: int, channels: int) -> np.ndarray:
    rng = np.random.default_rng(0)
    mass = np.zeros((bs, gs, gs, channels), dtype=np.float32)
    q = gs // 4
    mass[:, q : 3 * q, q : 3 * q, :] = rng.uniform(0, 1, (bs, 2 * q, 2 * q, channels)).astype(np.float32)
    return mass


def resolve_bench_execution_mode(
    *,
    requested_mode: str | None,
    device_list: list[str],
    visible_devices: str | None,
    mesh_shape: tuple[int, int] | None,
) -> ExecutionMode:
    """Default benchmark device selection to mesh when TT devices are explicit."""
    execution_mode = requested_mode
    if execution_mode is None:
        execution_mode = "mesh" if device_list or visible_devices is not None or mesh_shape is not None else "single"
    return resolve_execution_mode(
        execution_mode=execution_mode,
        device_list=device_list,
        visible_devices=visible_devices,
        mesh_shape=mesh_shape,
    )


def bench_engine(
    engine,
    mass: np.ndarray,
    warmup: int,
    steps: int,
    *,
    profile_stages: bool = False,
) -> BenchResult:
    state = mass.copy()
    run = getattr(engine, "run", None)
    if callable(run):
        if warmup > 0:
            state = run(state, warmup)
        if profile_stages and hasattr(engine, "reset_stage_timings"):
            engine.reset_stage_timings()
        t0 = time.perf_counter()
        state = run(state, steps)
        stage_profile = None
        if profile_stages and hasattr(engine, "stage_timing_summary"):
            stage_profile = engine.stage_timing_summary()
            stage_profile["amortized_ms_per_step"] = _amortized_stage_ms(stage_profile, steps)
        return BenchResult(elapsed_s=time.perf_counter() - t0, stage_profile=stage_profile)
    for _ in range(warmup):
        state = engine.step(state).mass
    if profile_stages and hasattr(engine, "reset_stage_timings"):
        engine.reset_stage_timings()
    t0 = time.perf_counter()
    for _ in range(steps):
        state = engine.step(state).mass
    stage_profile = None
    if profile_stages and hasattr(engine, "stage_timing_summary"):
        stage_profile = engine.stage_timing_summary()
        stage_profile["amortized_ms_per_step"] = _amortized_stage_ms(stage_profile, steps)
    return BenchResult(elapsed_s=time.perf_counter() - t0, stage_profile=stage_profile)


def _amortized_stage_ms(stage_profile: dict[str, object], steps: int) -> dict[str, float]:
    if steps <= 0:
        return {}
    total_ms = stage_profile.get("total_ms", {})
    if not isinstance(total_ms, dict):
        return {}
    return {str(name): float(total) / float(steps) for name, total in total_ms.items()}


def _close_engine(engine) -> None:
    close = getattr(engine, "close", None)
    if callable(close):
        close()


def _strip_cli_args(
    argv: list[str],
    *,
    options_with_values: set[str],
    boolean_flags: set[str],
) -> list[str]:
    filtered: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in boolean_flags:
            index += 1
            continue
        matched_option = next((option for option in options_with_values if arg == option), None)
        if matched_option is not None:
            index += 2
            continue
        matched_prefix = next((option for option in options_with_values if arg.startswith(f"{option}=")), None)
        if matched_prefix is not None:
            index += 1
            continue
        filtered.append(arg)
        index += 1
    return filtered


def _grid_and_batch_cases(grid_sizes: list[int], batch_sizes: list[int]) -> list[tuple[int, int]]:
    return [(grid_size, batch_size) for grid_size in grid_sizes for batch_size in batch_sizes]


def _print_table_header() -> None:
    header = "{:>8} {:>6} {:>12} {:>10} {:>9}".format("Grid", "Batch", "Backend", "ms/step", "Devices")
    print(header)
    print("-" * len(header))


def _print_bench_row(row: BenchRow) -> None:
    print(
        "{:>8} {:>6} {:>12} {:>10.1f} {:>9}".format(
            row.grid_size,
            row.batch_size,
            row.backend_label,
            row.ms_per_step,
            row.device_label,
        )
    )
    if row.execution_strategy.startswith("mesh-"):
        print(f"{'':>8} {'':>6} {'strategy':>12} {row.execution_strategy}")
    if row.stage_profile is None:
        return
    mean_ms = row.stage_profile.get("amortized_ms_per_step", {})
    counts = row.stage_profile.get("counts", {})
    ordered = [
        "prepare",
        "front_half",
        "fft",
        "spectra",
        "ifft",
        "growth",
        "flow",
        "reintegration",
        "finalize",
    ]
    ordered_names = [name for name in ordered if name in mean_ms]
    extra_names = sorted(name for name in mean_ms if name not in ordered)
    stage_text = " ".join(f"{name}={mean_ms[name]:.2f}ms" for name in [*ordered_names, *extra_names])
    count_text = " ".join(f"{name}x{counts[name]}" for name in [*ordered_names, *extra_names] if name in counts)
    print(f"{'':>8} {'':>6} {'stage/step':>12} {stage_text}")
    print(f"{'':>8} {'':>6} {'stage-count':>12} {count_text}")


def _serialize_rows(rows: list[BenchRow]) -> list[dict[str, object]]:
    return [
        {
            "grid_size": row.grid_size,
            "batch_size": row.batch_size,
            "backend_label": row.backend_label,
            "resolved_backend": row.resolved_backend,
            "ms_per_step": row.ms_per_step,
            "device_label": row.device_label,
            "execution_strategy": row.execution_strategy,
            "stage_profile": row.stage_profile,
        }
        for row in rows
    ]


def build_tracy_command(
    *,
    script_path: Path,
    argv: list[str],
    output_dir: Path,
    perf_counters: str | None,
    sync_host_device: bool,
    tracy_tools_folder: Path | None,
) -> list[str]:
    command = [sys.executable, "-m", "tracy", "-v", "-r", "-p", "-o", str(output_dir)]
    if sync_host_device:
        command.append("--sync-host-device")
    if perf_counters is not None:
        command.extend(["--profiler-capture-perf-counters", perf_counters])
    if tracy_tools_folder is not None:
        command.extend(["--tracy-tools-folder", str(tracy_tools_folder)])
    command.append(str(script_path))
    command.extend(
        _strip_cli_args(
            argv,
            options_with_values={"--tracy-output-dir", "--tracy-perf-counters", "--tracy-tools-folder"},
            boolean_flags={"--tracy-sync-host-device"},
        )
    )
    return command


def maybe_reexec_under_tracy(
    *,
    script_path: Path,
    argv: list[str],
    output_dir: Path | None,
    perf_counters: str | None,
    sync_host_device: bool,
    tracy_tools_folder: Path | None,
) -> None:
    if output_dir is None or os.environ.get(TRACY_REEXEC_ENV) == "1":
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    command = build_tracy_command(
        script_path=script_path,
        argv=argv,
        output_dir=output_dir,
        perf_counters=perf_counters,
        sync_host_device=sync_host_device,
        tracy_tools_folder=tracy_tools_folder,
    )
    env = os.environ.copy()
    env[TRACY_REEXEC_ENV] = "1"
    raise SystemExit(subprocess.run(command, check=False, env=env).returncode)


def build_serialized_case_command(
    *,
    script_path: Path,
    argv: list[str],
    grid_size: int,
    batch_size: int,
    summary_path: Path,
) -> list[str]:
    filtered_args = _strip_cli_args(
        argv,
        options_with_values={
            "--grid-sizes",
            "--batch-sizes",
            "--summary-json",
        },
        boolean_flags=set(),
    )
    return [
        sys.executable,
        str(script_path),
        *filtered_args,
        "--grid-sizes",
        str(grid_size),
        "--batch-sizes",
        str(batch_size),
        "--summary-json",
        str(summary_path),
    ]


def _run_cleanup_command(command: str) -> None:
    subprocess.run(command, shell=True, check=True, executable="/bin/bash")


def _run_bench_case_subprocess(
    *,
    command: list[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=TT_CASE_TIMEOUT_S,
        env={**os.environ, BENCH_LOCK_ENV: "1"},
    )


def _acquire_bench_lock():
    if os.environ.get(BENCH_LOCK_ENV) == "1":
        return None
    BENCH_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = BENCH_LOCK_PATH.open("w", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError(
            f"Another TT bench run already holds {BENCH_LOCK_PATH}. "
            "Wait for it to finish or clean up the stale process first."
        ) from exc
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    return handle


def _release_bench_lock(handle) -> None:
    if handle is None:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def run_serialized_cases(
    *,
    script_path: Path,
    argv: list[str],
    grid_sizes: list[int],
    batch_sizes: list[int],
    summary_json: Path | None,
) -> list[BenchRow]:
    rows: list[BenchRow] = []
    with tempfile.TemporaryDirectory(prefix="lenia-tt-bench-") as temp_dir:
        temp_root = Path(temp_dir)
        for grid_size, batch_size in _grid_and_batch_cases(grid_sizes, batch_sizes):
            print(f"[case {grid_size}x{grid_size} b{batch_size}] cleanup: {TT_HUGEPAGE_CLEANUP}")
            _run_cleanup_command(TT_HUGEPAGE_CLEANUP)
            summary_path = temp_root / f"summary_{grid_size}_{batch_size}.json"
            command = build_serialized_case_command(
                script_path=script_path,
                argv=argv,
                grid_size=grid_size,
                batch_size=batch_size,
                summary_path=summary_path,
            )
            print(
                f"[case {grid_size}x{grid_size} b{batch_size}] exec: "
                + " ".join(shlex.quote(part) for part in command)
            )
            result = _run_bench_case_subprocess(command=command)
            if result.stdout:
                print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
            if result.returncode != 0:
                raise SystemExit(result.returncode)
            case_rows = [
                BenchRow(
                    grid_size=int(item["grid_size"]),
                    batch_size=int(item["batch_size"]),
                    backend_label=str(item["backend_label"]),
                    resolved_backend=str(item["resolved_backend"]),
                    ms_per_step=float(item["ms_per_step"]),
                    device_label=str(item["device_label"]),
                    execution_strategy=str(item.get("execution_strategy", "")),
                    stage_profile=item.get("stage_profile"),
                )
                for item in json.loads(summary_path.read_text())
            ]
            rows.extend(case_rows)
    if summary_json is not None:
        summary_json.parent.mkdir(parents=True, exist_ok=True)
        summary_json.write_text(json.dumps(_serialize_rows(rows), indent=2, sort_keys=True))
    return rows


def bench_single_device(
    *,
    backend: str,
    config,
    kernels,
    mass: np.ndarray,
    warmup: int,
    steps: int,
    device_id: int,
    mesh_shape: tuple[int, int] | None,
    visible_devices: str | None,
    mesh_dft: bool,
    profile_stages: bool,
) -> BenchResult:
    if backend == "reference":
        engine = make_reference_engine(config, kernels)
        try:
            return bench_engine(engine, mass, warmup, steps, profile_stages=profile_stages)
        finally:
            _close_engine(engine)

    device = None
    engine = None
    if uses_ttnn_runtime(backend):
        previous_env = apply_tt_runtime_env(
            visible_device=visible_devices,
            mesh_dft=True if mesh_dft else None,
        )
        device = open_ttnn_device(
            device_id=device_id,
            mesh_shape=mesh_shape,
        )
    else:
        previous_env = {}
    try:
        engine = make_runtime_engine(
            backend,
            config,
            kernels,
            device=device,
        )
        return bench_engine(engine, mass, warmup, steps, profile_stages=profile_stages)
    finally:
        if engine is not None:
            _close_engine(engine)
        if device is not None:
            close_ttnn_device(device)
        restore_tt_runtime_env(previous_env)


def main():
    parser = argparse.ArgumentParser(description="Benchmark Flow Lenia backends on the TT runtime surface")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parents[2] / "configs" / "base" / "paper_base_3k_1c_128.json",
        help="Flow Lenia config to benchmark. Grid sizes still override sx/sy in the loaded config.",
    )
    parser.add_argument("--grid-sizes", default="128", help="Comma-separated grid sizes")
    parser.add_argument("--batch-sizes", default="1", help="Comma-separated batch sizes")
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument(
        "--backend",
        choices=["reference", "tt"],
        default="tt",
        help="reference=NumPy oracle, tt=TTNN spectral front half plus TT-Lang growth/reintegration.",
    )
    parser.add_argument("--device-id", type=int, default=1)
    parser.add_argument(
        "--device-list",
        default=None,
        help="Comma-separated physical device ids for batch-parallel execution, or 'auto'.",
    )
    parser.add_argument("--mesh-shape", default=None, help="Explicit TTNN mesh shape as rows,cols.")
    parser.add_argument("--tt-visible-devices", default=None)
    parser.add_argument(
        "--mesh-dft",
        action="store_true",
        help="Enable the experimental mesh-partitioned DFT front half for mesh benchmarks.",
    )
    parser.add_argument(
        "--execution-mode",
        choices=["single", "fleet", "mesh"],
        default=None,
        help=(
            "single=one TT device, fleet=independent batch sims across TT devices, "
            "mesh=one sim on a TTNN/TT-Lang mesh. Defaults to mesh when TT devices "
            "are supplied, otherwise single."
        ),
    )
    parser.add_argument(
        "--stage-profile",
        action="store_true",
        help="Emit per-stage timing averages for the single-engine TT path.",
    )
    parser.add_argument("--tracy-output-dir", type=Path, default=None)
    parser.add_argument("--tracy-perf-counters", default=None)
    parser.add_argument("--tracy-tools-folder", type=Path, default=None)
    parser.add_argument("--tracy-sync-host-device", action="store_true")
    parser.add_argument("--summary-json", type=Path, default=None)
    parser.add_argument(
        "--persistent-workers",
        action="store_true",
        help="Reuse one engine per device for batch-parallel runs instead of respawning workers per benchmark.",
    )
    args = parser.parse_args()
    if args.device_list is not None and args.tt_visible_devices is not None:
        parser.error("--device-list and --tt-visible-devices cannot be used together.")
    if args.backend == "reference":
        if args.device_list is not None or args.tt_visible_devices is not None or args.mesh_shape is not None:
            parser.error("--backend reference does not support TT device selection flags.")
        if args.persistent_workers:
            parser.error("--backend reference does not support --persistent-workers.")
    maybe_reexec_under_tracy(
        script_path=Path(__file__).resolve(),
        argv=sys.argv[1:],
        output_dir=args.tracy_output_dir,
        perf_counters=args.tracy_perf_counters,
        sync_host_device=args.tracy_sync_host_device,
        tracy_tools_folder=args.tracy_tools_folder,
    )

    bench_lock = _acquire_bench_lock()
    try:
        grid_sizes = [int(x) for x in args.grid_sizes.split(",")]
        batch_sizes = [int(x) for x in args.batch_sizes.split(",")]
        isolate_cases = (
            args.backend != "reference"
            and not args.stage_profile
            and len(_grid_and_batch_cases(grid_sizes, batch_sizes)) > 1
        )
        if isolate_cases:
            run_serialized_cases(
                script_path=Path(__file__).resolve(),
                argv=sys.argv[1:],
                grid_sizes=grid_sizes,
                batch_sizes=batch_sizes,
                summary_json=args.summary_json,
            )
            return
        device_list = parse_device_list(args.device_list)
        mesh_shape = parse_mesh_shape(args.mesh_shape)
        try:
            execution_mode = resolve_bench_execution_mode(
                requested_mode=args.execution_mode,
                device_list=device_list,
                visible_devices=args.tt_visible_devices,
                mesh_shape=mesh_shape,
            )
        except ValueError as exc:
            parser.error(str(exc))
        if args.mesh_dft and execution_mode != "mesh":
            parser.error("--mesh-dft requires mesh execution mode.")

        rows: list[BenchRow] = []
        _print_table_header()

        for gs in grid_sizes:
            config, kernels = bench_config(gs, gs, config_path=args.config)
            persistent_runners: dict[tuple[object, ...], PersistentBatchRunner] = {}
            try:
                for bs in batch_sizes:
                    resolved_backend = args.backend
                    resolved_device_list = device_list
                    resolved_visible_devices, resolved_mesh_shape = resolve_runtime_device_selection(
                        backend=resolved_backend,
                        execution_mode=execution_mode,
                        device_list=resolved_device_list,
                        visible_devices=args.tt_visible_devices,
                        mesh_shape=mesh_shape,
                    )
                    use_persistent_workers = args.persistent_workers
                    if args.stage_profile and (
                        not uses_ttnn_runtime(resolved_backend)
                        or use_persistent_workers
                        or execution_mode == "fleet"
                    ):
                        parser.error(
                            "--stage-profile is only supported for the single-engine TT path or explicit TTNN mesh mode."
                        )
                    persistent_runner = None
                    if execution_mode == "fleet" and use_persistent_workers and resolved_device_list:
                        runner_key = (
                            resolved_backend,
                            tuple(resolved_device_list),
                        )
                        persistent_runner = persistent_runners.get(runner_key)
                        if persistent_runner is None:
                            persistent_runner = PersistentBatchRunner(
                                backend=resolved_backend,
                                config=config,
                                kernels=kernels,
                                visible_devices=resolved_device_list,
                            )
                            persistent_runners[runner_key] = persistent_runner
                    mass = make_mass(bs, gs, config.channels)
                    if execution_mode == "fleet":
                        if bs == 1:
                            raise ValueError(
                                "Fleet benchmarking needs --batch-sizes greater than 1; "
                                "use mesh mode for one sim across TT devices."
                            )
                        if persistent_runner is not None:
                            result = persistent_runner.run(mass, warmup=args.warmup, steps=args.steps)
                        else:
                            result = run_batch_parallel(
                                backend=resolved_backend,
                                config=config,
                                kernels=kernels,
                                mass=mass,
                                visible_devices=resolved_device_list,
                                warmup=args.warmup,
                                steps=args.steps,
                            )
                        bench_result = BenchResult(elapsed_s=result.elapsed_s)
                        device_label = (
                            f"p{len(result.partitions)}"
                            if persistent_runner is not None
                            else str(len(result.partitions))
                        )
                    else:
                        bench_result = bench_single_device(
                            backend=resolved_backend,
                            config=config,
                            kernels=kernels,
                            mass=mass,
                            warmup=args.warmup,
                            steps=args.steps,
                            device_id=args.device_id,
                            mesh_shape=resolved_mesh_shape,
                            visible_devices=resolved_visible_devices,
                            mesh_dft=args.mesh_dft,
                            profile_stages=args.stage_profile,
                        )
                        device_label = (
                            f"{resolved_mesh_shape[0]}x{resolved_mesh_shape[1]}"
                            if resolved_mesh_shape is not None
                            else "1"
                        )
                    execution_strategy = resolve_execution_strategy(
                        execution_mode=execution_mode,
                    )
                    ms_per_step = bench_result.elapsed_s / args.steps * 1000
                    row = BenchRow(
                        grid_size=gs,
                        batch_size=bs,
                        backend_label=resolved_backend,
                        resolved_backend=resolved_backend,
                        ms_per_step=ms_per_step,
                        device_label=device_label,
                        execution_strategy=execution_strategy,
                        stage_profile=bench_result.stage_profile,
                    )
                    rows.append(row)
                    _print_bench_row(row)
            finally:
                for runner in persistent_runners.values():
                    runner.close()
        if args.summary_json is not None:
            args.summary_json.parent.mkdir(parents=True, exist_ok=True)
            args.summary_json.write_text(json.dumps(_serialize_rows(rows), indent=2, sort_keys=True))
    finally:
        _release_bench_lock(bench_lock)


if __name__ == "__main__":
    main()
