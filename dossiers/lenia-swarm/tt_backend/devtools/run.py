"""Run Flow Lenia on the TT runtime path.

Usage:
    python devtools/run.py \
      --config configs/base/paper_base_3k_1c_128.json \
      --backend tt \
      --execution-mode fleet \
      --steps 1000 \
      --device-list 0,1,2,3 \
      --output ./out

    python devtools/run.py \
      --config configs/base/paper_base_3k_1c_128.json \
      --reference reference/ \
      --backend tt \
      --execution-mode mesh \
      --device-list 0,1,2,3 \
      --mesh-shape 1,8 \
      --steps 100 \
      --output ./out
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tt_lenia.backends import make_runtime_engine
from tt_lenia.config import compile_kernels, load_config, resolve_connectivity, resolve_params
from tt_lenia.device import (
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
    split_visible_devices,
)
from tt_lenia.frame_export import FrameSequenceWriter
from tt_lenia.reference import (
    load_initial_mass_from_reference,
    load_kernels_from_reference,
    load_reference_arrays,
    load_reference_manifest,
)


@dataclass(frozen=True)
class RunOutcome:
    mass: np.ndarray
    elapsed_s: float


def parse_seed_list(value: str | None) -> list[int] | None:
    if value is None:
        return None
    seeds = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not seeds:
        raise ValueError("--seed-list must contain at least one integer seed.")
    return seeds


def default_initial_seeds(config_raw: dict, batch_size: int) -> list[int]:
    init_seed = int(config_raw["init"]["seed"])
    return [init_seed + i for i in range(batch_size)]


def resolved_parameter_seed(config_raw: dict, seed_override: int | None) -> int | None:
    if seed_override is not None:
        return int(seed_override)
    seed = config_raw.get("params", {}).get("seed")
    return None if seed is None else int(seed)


def make_initial_state(
    config_raw: dict,
    sx: int,
    sy: int,
    channels: int,
    batch_size: int,
    *,
    seed_list: list[int] | None = None,
    init_seed_offset: int = 0,
) -> np.ndarray:
    init_cfg = config_raw["init"]
    seeds = seed_list if seed_list is not None else [init_cfg["seed"] + i for i in range(batch_size)]
    if len(seeds) != batch_size:
        raise ValueError(f"seed_list length {len(seeds)} does not match batch_size {batch_size}.")
    mass = np.zeros((batch_size, sx, sy, channels), dtype=np.float32)

    state_patch = init_cfg.get("state_patch")
    if state_patch is not None:
        raise ValueError("config init.state_patch requires a Swift reference bundle for TT execution.")

    lo = init_cfg["a_uniform"]["low"]
    hi = init_cfg["a_uniform"]["high"]
    rngs = [np.random.default_rng(seed + init_seed_offset) for seed in seeds]
    for patch in init_cfg["patches"]:
        cx, cy = patch["center"]
        half = patch["size"] // 2
        x0 = max(0, cx - half)
        x1 = min(sx, cx + half)
        y0 = max(0, cy - half)
        y1 = min(sy, cy + half)
        for batch_index, rng in enumerate(rngs):
            mass[batch_index, x0:x1, y0:y1, :] = rng.uniform(
                lo, hi, (x1 - x0, y1 - y0, channels)
            ).astype(np.float32)
    return mass


def _close_engine(engine) -> None:
    close = getattr(engine, "close", None)
    if callable(close):
        close()


def _sampling_steps(*, steps: int, save_every: int, frame_every: int) -> set[int]:
    sample_steps: set[int] = set()
    for interval in (save_every, frame_every):
        if interval <= 0:
            continue
        sample_steps.add(0)
        sample_steps.update(range(interval, steps + 1, interval))
    if frame_every > 0:
        sample_steps.add(max(0, steps))
    return sample_steps


def _save_sample(
    *,
    step: int,
    state: np.ndarray,
    steps: int,
    save_every: int,
    frame_every: int,
    out_dir: Path,
    frame_writer: FrameSequenceWriter | None,
    started_at: float,
) -> None:
    if save_every > 0 and (step == 0 or step % save_every == 0):
        np.save(out_dir / f"step_{step:04d}.npy", state)
    if frame_writer is not None and frame_every > 0 and (step == 0 or step % frame_every == 0):
        frame_writer.write_frame(step, state)
    if step > 0:
        elapsed = time.perf_counter() - started_at
        print(f"  step {step}/{steps} ({step / elapsed:.1f} steps/s, mass={state.sum():.2f})")


def _run_single_engine(
    engine,
    mass: np.ndarray,
    *,
    steps: int,
    save_every: int,
    frame_every: int,
    out_dir: Path,
    frame_writer: FrameSequenceWriter | None,
) -> RunOutcome:
    state = mass
    t0 = time.perf_counter()
    sample_steps = _sampling_steps(steps=steps, save_every=save_every, frame_every=frame_every)
    run_sampled = getattr(engine, "run_sampled", None)
    if not sample_steps:
        state = engine.run(state, steps)
    elif callable(run_sampled):
        state = run_sampled(
            state,
            steps,
            sample_steps,
            lambda step, sample: _save_sample(
                step=step,
                state=sample,
                steps=steps,
                save_every=save_every,
                frame_every=frame_every,
                out_dir=out_dir,
                frame_writer=frame_writer,
                started_at=t0,
            ),
        )
    else:
        _save_sample(
            step=0,
            state=state,
            steps=steps,
            save_every=save_every,
            frame_every=frame_every,
            out_dir=out_dir,
            frame_writer=frame_writer,
            started_at=t0,
        )
        for step in range(1, steps + 1):
            state = engine.step(state).mass
            if step in sample_steps:
                _save_sample(
                    step=step,
                    state=state,
                    steps=steps,
                    save_every=save_every,
                    frame_every=frame_every,
                    out_dir=out_dir,
                    frame_writer=frame_writer,
                    started_at=t0,
                )
    elapsed = time.perf_counter() - t0
    print(f"Done in {elapsed:.2f}s ({steps / elapsed:.1f} steps/s)")
    return RunOutcome(mass=state, elapsed_s=elapsed)


def _run_parallel(
    *,
    backend: str,
    config,
    kernels,
    mass: np.ndarray,
    steps: int,
    save_every: int,
    frame_every: int,
    out_dir: Path,
    frame_writer: FrameSequenceWriter | None,
    visible_devices: list[str],
    persistent_workers: bool,
) -> RunOutcome:
    state = mass
    sample_steps = _sampling_steps(steps=steps, save_every=save_every, frame_every=frame_every)

    t0 = time.perf_counter()
    if persistent_workers or sample_steps:
        with PersistentBatchRunner(
            backend=backend,
            config=config,
            kernels=kernels,
            visible_devices=visible_devices,
        ) as runner:
            if not sample_steps:
                state = runner.run(state, steps=steps).mass
            else:
                state = runner.run_sampled(
                    state,
                    steps=steps,
                    sample_steps=sample_steps,
                    on_sample=lambda step, sample: _save_sample(
                        step=step,
                        state=sample,
                        steps=steps,
                        save_every=save_every,
                        frame_every=frame_every,
                        out_dir=out_dir,
                        frame_writer=frame_writer,
                        started_at=t0,
                    ),
                ).mass
    else:
        state = run_batch_parallel(
            backend=backend,
            config=config,
            kernels=kernels,
            mass=state,
            visible_devices=visible_devices,
            warmup=0,
            steps=steps,
        ).mass
    elapsed = time.perf_counter() - t0
    print(f"Done in {elapsed:.2f}s ({steps / elapsed:.1f} steps/s)")
    return RunOutcome(mass=state, elapsed_s=elapsed)


def _sample_summaries(final_mass: np.ndarray, seed_list: list[int], init_seed_offset: int) -> list[dict]:
    summaries: list[dict] = []
    for batch_index, seed in enumerate(seed_list):
        sample = final_mass[batch_index].astype(np.float32, copy=False)
        summaries.append(
            {
                "batch_index": batch_index,
                "seed": seed,
                "init_seed": seed + init_seed_offset,
                "mass_sum": float(sample.sum()),
                "mass_mean": float(sample.mean()),
                "mass_min": float(sample.min()),
                "mass_max": float(sample.max()),
            }
        )
    return summaries


def write_run_manifest(
    *,
    out_dir: Path,
    config_path: str,
    reference_path: Path | None,
    backend: str,
    execution_mode: str,
    execution_strategy: str,
    mesh_shape: tuple[int, int] | None,
    visible_devices: str | None,
    mesh_dft: bool,
    steps: int,
    seed: int | None,
    seed_list: list[int],
    init_seed_offset: int,
    final_mass: np.ndarray,
    elapsed_s: float,
) -> Path:
    manifest = {
        "manifest_version": 1,
        "kind": "lenia_tt_run",
        "backend": backend,
        "execution_mode": execution_mode,
        "execution_strategy": execution_strategy,
        "mesh_shape": list(mesh_shape) if mesh_shape is not None else None,
        "visible_devices": visible_devices,
        "mesh_dft": bool(mesh_dft),
        "config_path": config_path,
        "reference_path": str(reference_path) if reference_path is not None else None,
        "steps": int(steps),
        "batch_size": int(final_mass.shape[0]),
        "parameter_seed": None if seed is None else int(seed),
        "seed_list": [int(item) for item in seed_list],
        "init_seed_offset": int(init_seed_offset),
        "elapsed_seconds": elapsed_s,
        "steps_per_second": float(steps / elapsed_s) if elapsed_s > 0 else None,
        "mass_final_path": "mass_final.npy",
        "samples": _sample_summaries(final_mass, seed_list, init_seed_offset),
    }
    path = out_dir / "tt_run.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def validate_execution_batch(execution_mode: str, batch_size: int) -> None:
    if batch_size != 1 and execution_mode != "fleet":
        raise ValueError(
            "TT batch_size > 1 currently requires --execution-mode fleet "
            "because the packed TT-Lang flow kernels are batch=1."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Flow Lenia on the TT runtime backend")
    parser.add_argument("--config", required=True, help="Path to JSON config file")
    parser.add_argument(
        "--backend",
        choices=["tt"],
        default="tt",
        help="tt=TTNN spectral front half plus TT-Lang growth/reintegration.",
    )
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Parameter seed override; defaults to params.seed from the config.",
    )
    parser.add_argument(
        "--seed-list",
        default=None,
        help="Comma-separated initial-state seeds for the batch; defaults to seed..seed+batch_size-1.",
    )
    parser.add_argument(
        "--init-seed-offset",
        type=int,
        default=0,
        help="Offset added to each seed when constructing initial states.",
    )
    parser.add_argument("--save-every", type=int, default=0, help="Save state every N steps (0=final only)")
    parser.add_argument(
        "--frame-every",
        type=int,
        default=0,
        help="Export Studio-playable raw r8 frame every N steps (0=disabled)",
    )
    parser.add_argument(
        "--frame-projection",
        default="matter",
        help="Frame projection: 'matter' sums channels, or 'channel:N' selects one channel.",
    )
    parser.add_argument("--frame-batch-index", type=int, default=0)
    parser.add_argument("--device-id", type=int, default=0)
    parser.add_argument(
        "--reference",
        type=Path,
        default=None,
        help="Reference bundle exported by lenia-swarm export-reference; uses Swift-resolved mass and kernels",
    )
    parser.add_argument(
        "--device-list",
        default=None,
        help="Comma-separated physical device ids for TT execution, or 'auto'.",
    )
    parser.add_argument("--tt-visible-devices", default=None)
    parser.add_argument("--mesh-shape", default=None, help="Explicit TT mesh shape as rows,cols.")
    parser.add_argument(
        "--mesh-dft",
        action="store_true",
        help="Enable the experimental mesh-partitioned DFT front half for --execution-mode mesh.",
    )
    parser.add_argument(
        "--execution-mode",
        choices=["single", "fleet", "mesh"],
        default="single",
        help=(
            "single=one sim on one TT device, fleet=independent batch sims across devices, "
            "mesh=one TTNN/TT-Lang mesh engine. Current batch-1 mesh is replicated SPMD; "
            "fleet is the path for independent sims."
        ),
    )
    parser.add_argument("--persistent-workers", action="store_true")
    args = parser.parse_args()

    if args.device_list is not None and args.tt_visible_devices is not None:
        parser.error("--device-list and --tt-visible-devices cannot be used together.")

    config, raw = load_config(args.config)
    reference_manifest = load_reference_manifest(args.reference) if args.reference is not None else None
    parameter_seed = resolved_parameter_seed(raw, args.seed)
    init_seed_offset = args.init_seed_offset
    try:
        seed_list = parse_seed_list(args.seed_list)
    except ValueError as exc:
        parser.error(str(exc))
    if reference_manifest is not None:
        if seed_list is None and "initial_seeds" in reference_manifest:
            seed_list = [int(seed) for seed in reference_manifest["initial_seeds"]]
        if "parameter_seed" in reference_manifest:
            parameter_seed = int(reference_manifest["parameter_seed"])
        if "init_seed_offset" in reference_manifest:
            init_seed_offset = int(reference_manifest["init_seed_offset"])

    if args.reference is not None:
        params = None
        ref = load_reference_arrays(args.reference)
        kernels = load_kernels_from_reference(ref)
        mass = load_initial_mass_from_reference(ref)
        if args.batch_size != 1 and args.batch_size != mass.shape[0]:
            parser.error(f"--batch-size={args.batch_size} does not match reference batch={mass.shape[0]}.")
        if seed_list is None:
            seed_list = default_initial_seeds(raw, mass.shape[0])
        if len(seed_list) != mass.shape[0]:
            parser.error(f"--seed-list contains {len(seed_list)} seeds but reference batch={mass.shape[0]}.")
    else:
        if seed_list is None:
            seed_list = default_initial_seeds(raw, args.batch_size)
        if len(seed_list) != args.batch_size:
            parser.error(f"--seed-list contains {len(seed_list)} seeds but --batch-size={args.batch_size}.")
        c0, c1 = resolve_connectivity(raw)
        params = resolve_params(raw, config.nb_k, seed=args.seed)
        kernels = compile_kernels(params, config, c0, c1)
        try:
            mass = make_initial_state(
                raw,
                config.sx,
                config.sy,
                config.channels,
                args.batch_size,
                seed_list=seed_list,
                init_seed_offset=init_seed_offset,
            )
        except ValueError as exc:
            parser.error(str(exc))

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    frame_writer = None
    if args.frame_every > 0:
        radius = getattr(params, "R", 0.0) if params is not None else raw.get("params", {}).get("R", 0.0)
        if not isinstance(radius, (int, float)):
            radius = 0.0
        frame_writer = FrameSequenceWriter(
            output_dir=out_dir,
            backend=args.backend,
            config_path=str(Path(args.config)),
            steps=args.steps,
            frame_every=args.frame_every,
            projection=args.frame_projection,
            batch_index=args.frame_batch_index,
            metadata={
                "dt": config.dt,
                "dd": config.dd,
                "sigma": config.sigma,
                "n": config.n,
                "theta_a": config.theta_a,
                "border": config.border,
                "kernel_profile": config.implementation.kernel_profile,
                "kernel_count": config.nb_k,
                "radius": radius,
            },
        )

    device_list = parse_device_list(args.device_list)
    mesh_shape = parse_mesh_shape(args.mesh_shape)
    resolved_backend = args.backend
    resolved_devices = device_list
    try:
        execution_mode = resolve_execution_mode(
            execution_mode=args.execution_mode,
            device_list=resolved_devices,
            visible_devices=args.tt_visible_devices,
            mesh_shape=mesh_shape,
        )
    except ValueError as exc:
        parser.error(str(exc))
    resolved_visible_devices, resolved_mesh_shape = resolve_runtime_device_selection(
        backend=resolved_backend,
        execution_mode=execution_mode,
        device_list=resolved_devices,
        visible_devices=args.tt_visible_devices,
        mesh_shape=mesh_shape,
    )
    try:
        validate_execution_batch(execution_mode, mass.shape[0])
    except ValueError as exc:
        parser.error(str(exc))
    if args.mesh_dft and execution_mode != "mesh":
        parser.error("--mesh-dft requires --execution-mode mesh.")
    use_persistent_workers = args.persistent_workers
    execution_strategy = resolve_execution_strategy(
        execution_mode=execution_mode,
    )

    print(
        f"Running {args.steps} steps, batch={mass.shape[0]}, grid={config.sx}x{config.sy}, "
        f"channels={config.channels}, backend={resolved_backend}, execution={execution_mode}"
    )
    if execution_mode == "mesh":
        print(f"Mesh strategy: {execution_strategy}")

    if execution_mode == "fleet":
        visible_devices = resolved_devices or list(split_visible_devices(resolved_visible_devices))
        outcome = _run_parallel(
            backend=resolved_backend,
            config=config,
            kernels=kernels,
            mass=mass,
            steps=args.steps,
            save_every=args.save_every,
            frame_every=args.frame_every,
            out_dir=out_dir,
            frame_writer=frame_writer,
            visible_devices=visible_devices,
            persistent_workers=use_persistent_workers,
        )
    else:
        device = None
        engine = None
        previous_env = apply_tt_runtime_env(
            visible_device=resolved_visible_devices,
            mesh_dft=True if args.mesh_dft else None,
        )
        try:
            device = open_ttnn_device(
                device_id=args.device_id,
                mesh_shape=resolved_mesh_shape,
            )
            engine = make_runtime_engine(resolved_backend, config, kernels, device=device)
            outcome = _run_single_engine(
                engine,
                mass,
                steps=args.steps,
                save_every=args.save_every,
                frame_every=args.frame_every,
                out_dir=out_dir,
                frame_writer=frame_writer,
            )
        finally:
            if engine is not None:
                _close_engine(engine)
            if device is not None:
                close_ttnn_device(device)
            restore_tt_runtime_env(previous_env)

    final_mass = outcome.mass
    np.save(out_dir / "mass_final.npy", final_mass)
    if frame_writer is not None:
        frame_writer.write_manifest(final_mass_path="mass_final.npy")
    write_run_manifest(
        out_dir=out_dir,
        config_path=str(Path(args.config)),
        reference_path=args.reference,
        backend=resolved_backend,
        execution_mode=execution_mode,
        execution_strategy=execution_strategy,
        mesh_shape=resolved_mesh_shape,
        visible_devices=resolved_visible_devices,
        mesh_dft=args.mesh_dft,
        steps=args.steps,
        seed=parameter_seed,
        seed_list=seed_list,
        init_seed_offset=init_seed_offset,
        final_mass=final_mass,
        elapsed_s=outcome.elapsed_s,
    )
    print(f"Saved to {out_dir}")


if __name__ == "__main__":
    main()
