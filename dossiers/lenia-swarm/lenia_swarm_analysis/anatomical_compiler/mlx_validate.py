"""Validate the MLX forward map against the Swift LeniaCLI oracle.

Two checks, because no single one is both exact and end-to-end:

1. Per-cell dynamics. Run LeniaCLI with frame capture, seed the MLX rollout from the
   captured initial field (frame 0, which is the uniform[0,1] init at 8-bit precision),
   roll forward, and compare cell-by-cell against the later Swift frames. Frames store
   clip(mass, 0, 1) * 255, so the comparison clips the MLX field to [0, 1] too; this
   isolates the step math from the frame's clamping and quantization. A short horizon is
   used because the rollout is weakly chaotic (positive Lyapunov exponent), so the ~0.4%
   quantization of the shared init grows over time and only the early steps are a clean
   per-cell test.

2. Mass conservation. Flow Lenia conserves total mass exactly; the MLX rollout should
   hold its initial mass across the full horizon.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import mlx.core as mx
import numpy as np
from PIL import Image

from lenia_swarm_analysis.anatomical_compiler.forward_sim import (
    DEFAULT_BINARY,
    GENOTYPE_KEYS,
    _merged_env,
)
from lenia_swarm_analysis.anatomical_compiler.mlx_lenia import (
    GenotypeBatch,
    LeniaConfig,
    compile_kernels,
    make_step,
    position_grid,
)


def _run_with_frames(
    binary: Path, base_config: dict[str, Any], search_config: dict[str, Any],
    genotype: dict[str, Any], output_dir: Path, *, init_seed: int, steps: int,
    stride: int, dossier_root: Path, timeout: float,
) -> None:
    config = json.loads(json.dumps(base_config))
    params = config["params"]
    params["mode"] = "explicit"
    params["seed"] = init_seed
    for key in GENOTYPE_KEYS:
        params[key] = genotype[key]
    config["init"] = {**config["init"], "seed": init_seed}
    search = json.loads(json.dumps(search_config))
    search["steps"] = steps
    # This run only reads frames, not post-warmup metric samples, so collapse the
    # warmup and recording schedule to satisfy the preflight at a short horizon.
    search["warmup_steps"] = 0
    search["record_interval"] = max(1, min(stride, steps))
    with tempfile.TemporaryDirectory() as raw:
        workdir = Path(raw)
        base_path = workdir / "base.json"
        base_path.write_text(json.dumps(config), encoding="utf-8")
        search_path = workdir / "search.json"
        search_path.write_text(json.dumps(search), encoding="utf-8")
        command = [
            str(binary), "discover", "local",
            "--config", str(base_path), "--search", str(search_path),
            "--output", str(output_dir), "--count", "1", "--seed", str(init_seed),
            "--no-promotion", "--frames", "--frame-stride", str(stride),
        ]
        env = {"SPECTER_ARTIFACT_ROOT": str(output_dir.parent / "artifacts")}
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            env=_merged_env(env), cwd=str(dossier_root),
        )
        if completed.returncode != 0:
            raise RuntimeError(f"LeniaCLI failed:\n{completed.stderr[-2000:]}")


def _load_frames(output_dir: Path) -> dict[int, np.ndarray]:
    frames: dict[int, np.ndarray] = {}
    for frame_path in output_dir.rglob("frame_*.png"):
        step = int(frame_path.stem.split("_")[1])
        frames[step] = np.asarray(Image.open(frame_path), dtype=np.float32) / 255.0
    if not frames:
        raise RuntimeError("No frames captured")
    return frames


def run(
    base_config_path: Path, search_config_path: Path, dataset_path: Path,
    *, dossier_root: Path, genotype_index: int, init_seed: int, steps: int,
    stride: int, timeout: float,
) -> dict[str, Any]:
    base_config = json.loads(base_config_path.read_text(encoding="utf-8"))
    search_config = json.loads(search_config_path.read_text(encoding="utf-8"))
    config = LeniaConfig.from_base_config(base_config)

    rows = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    row = rows[genotype_index]
    genotype = row["params"]
    binary = dossier_root / DEFAULT_BINARY

    with tempfile.TemporaryDirectory() as raw:
        output_dir = Path(raw) / "out"
        _run_with_frames(
            binary, base_config, search_config, genotype, output_dir,
            init_seed=init_seed, steps=steps, stride=stride,
            dossier_root=dossier_root, timeout=timeout,
        )
        frames = _load_frames(output_dir)

    frame_steps = sorted(frames)
    first = frame_steps[0]
    a0_field = frames[first]
    if a0_field.ndim == 2:
        a0_field = a0_field[:, :, None]
    a0 = mx.array(a0_field[None, :, :, :])

    geno = GenotypeBatch.from_param_dicts([genotype])
    grid = position_grid(config)
    kernels = compile_kernels(geno, config)
    step = make_step(config, compile_step=True)

    init_mass = float(a0.sum())
    a = a0
    cursor = first
    comparisons: list[dict[str, Any]] = []
    for target in frame_steps[1:]:
        while cursor < target:
            a = step(a, grid, kernels)
            cursor += 1
        mx.eval(a)
        mlx_clamped = np.asarray(mx.clip(a[0, :, :, 0], 0.0, 1.0))
        swift = frames[target]
        if swift.ndim == 3:
            swift = swift[:, :, 0]
        diff = mlx_clamped - swift
        denom = float(np.sqrt((swift**2).mean())) + 1e-9
        rms = float(np.sqrt((diff**2).mean()))
        comparisons.append({
            "step": target,
            "relRms": rms / denom,
            "maxAbs": float(np.abs(diff).max()),
            "corr": float(np.corrcoef(mlx_clamped.ravel(), swift.ravel())[0, 1]),
            "mlxMass": float(a.sum()),
        })

    return {
        "genotypeIndex": genotype_index,
        "initSeed": init_seed,
        "steps": steps,
        "stride": stride,
        "initMass": init_mass,
        "massConservation": comparisons[-1]["mlxMass"] / init_mass if comparisons else None,
        "comparisons": comparisons,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="configs/base/paper_base_3k_1c_128.json")
    parser.add_argument("--search", default="configs/search/search_crossmap_motion.json")
    parser.add_argument(
        "--dataset", default="outputs/anatomical-compiler/forward_dataset_3k_1c_128.jsonl"
    )
    parser.add_argument("--genotype-index", type=int, default=0)
    parser.add_argument("--init-seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=60)
    parser.add_argument("--stride", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument(
        "--output", default="outputs/anatomical-compiler/mlx_validation.json"
    )
    args = parser.parse_args(argv)

    root = Path.cwd()
    report = run(
        (root / args.base).resolve(), (root / args.search).resolve(),
        (root / args.dataset).resolve(), dossier_root=root,
        genotype_index=args.genotype_index, init_seed=args.init_seed,
        steps=args.steps, stride=args.stride, timeout=args.timeout,
    )
    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"init mass {report['initMass']:.2f}, mass conservation "
          f"{report['massConservation']:.5f}")
    for c in report["comparisons"]:
        print(f"  step {c['step']:4d}: relRMS {c['relRms']:.4f}  "
              f"maxAbs {c['maxAbs']:.4f}  corr {c['corr']:.5f}")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
