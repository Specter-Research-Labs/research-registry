"""Forward-simulation harness for the anatomical compiler.

Takes a genotype (the decoded KernelParams shape stored in the compendium,
{R, r, b, w, a, m, s, h}), injects it into a regime's base config as explicit
params, runs one deterministic Lenia simulation through the LeniaCLI binary, and
returns the phenotype metrics. This is the forward map genotype -> phenotype that
Stage 2 validates its generated genotypes against: a generated genotype is only
trusted once it re-simulates to the requested descriptor and lands in the viable
shell.

The base config plus search config fix the physics regime; init_seed fixes the
initial condition so the map is a deterministic function of the genotype. The run
is invoked with --no-promotion and an isolated SPECTER_ARTIFACT_ROOT so it never
writes to the shared compendium.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from lenia_swarm_analysis.morphospace.common_morphology import (
    point_cloud_shape_features,
)

GENOTYPE_KEYS: tuple[str, ...] = ("r", "b", "w", "a", "m", "s", "h", "R")

METRIC_KEYS: tuple[str, ...] = (
    "mass_mean",
    "mass_std",
    "mass_min",
    "mass_max",
    "occupancy_mean",
    "variance_mean",
    "energy_mean",
    "speed_mean",
    "path_length",
    "displacement",
    "gyration",
    "center_velocity",
    "complexity_mean",
    "is_stable",
)

DEFAULT_BINARY = ".build/arm64-apple-macosx/release/LeniaCLI"


def state_patch_config(
    base_config: dict[str, Any], field: np.ndarray, *, center: tuple[int, int], seed: int
) -> dict[str, Any]:
    """Return a copy of base_config whose init seeds an explicit density field through
    init.state_patch, the Swift engine's explicit-state path (see
    SearchInitializationBuilder.buildExplicitInitialState).

    The builder writes a width*height*channels block, iterated x-outer/y/channel-inner,
    centered at `center` onto a zero background, so the values are the C-order ravel of the
    [sx, sy, C] field and width/height are the field's sx/sy. state_patch requires
    init.a_uniform == [0, 0] and (parameter_embedding disabled) no init.patches, so both are
    forced here; the data is f32le bytes, base64-encoded because Swift decodes Codable Data
    from a base64 JSON string."""
    if field.ndim == 2:
        field = field[:, :, None]
    sx, sy, channels = field.shape
    values = np.ascontiguousarray(field, dtype="<f4").ravel(order="C")
    config = deepcopy(base_config)
    config["init"] = {
        "seed": seed,
        "patches": [],
        "a_uniform": {"low": 0.0, "high": 0.0},
        "p_uniform": None,
        "state_patch": {
            "center": [int(center[0]), int(center[1])],
            "width": int(sx),
            "height": int(sy),
            "channels": int(channels),
            "encoding": "f32le",
            "data": base64.b64encode(values.tobytes()).decode("ascii"),
        },
    }
    return config


class ForwardSimulator:
    def __init__(
        self,
        base_config_path: Path,
        search_config_path: Path,
        *,
        dossier_root: Path,
        binary: Path | None = None,
        init_seed: int = 0,
        steps: int | None = None,
        backend: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> None:
        self.dossier_root = dossier_root
        self.backend = backend
        self.binary = binary or (dossier_root / DEFAULT_BINARY)
        if not self.binary.is_file():
            raise FileNotFoundError(f"LeniaCLI binary not found: {self.binary}")
        self.base_config = json.loads(base_config_path.read_text(encoding="utf-8"))
        self.search_config = json.loads(search_config_path.read_text(encoding="utf-8"))
        self.init_seed = init_seed
        self.steps = steps
        self.timeout_seconds = timeout_seconds

    def _explicit_config(self, genotype: dict[str, Any], init_seed: int) -> dict[str, Any]:
        config = deepcopy(self.base_config)
        params = deepcopy(config["params"])
        params["mode"] = "explicit"
        params["seed"] = init_seed
        for key in GENOTYPE_KEYS:
            if key not in genotype:
                raise KeyError(f"genotype missing required key {key!r}")
            params[key] = genotype[key]
        config["params"] = params
        config["init"] = {**config["init"], "seed": init_seed}
        return config

    def _search_config(self) -> dict[str, Any]:
        config = deepcopy(self.search_config)
        if self.steps is not None:
            config["steps"] = self.steps
        return config

    def generate_dataset(self, count: int, *, seed_start: int) -> list[dict[str, Any]]:
        """Sample the forward map: run `count` random genotypes through this regime
        and return their genotype and phenotype together.

        This is the clean training source for Stage 2, a contamination-free set of
        (genotype, phenotype) pairs drawn from one fully-specified physics regime,
        rather than the search-clustered, clone-ridden, unreconstructable historical
        compendium.
        """
        with tempfile.TemporaryDirectory() as raw_workdir:
            workdir = Path(raw_workdir)
            base_path = workdir / "base.json"
            base_path.write_text(json.dumps(self.base_config), encoding="utf-8")
            search_path = workdir / "search.json"
            search_path.write_text(json.dumps(self._search_config()), encoding="utf-8")
            output_dir = workdir / "out"
            self._run(base_path, search_path, output_dir, count=count, seed=seed_start)
            results = list(output_dir.rglob("results.jsonl"))
            if not results:
                raise RuntimeError("No results.jsonl produced for dataset generation")
            rows: list[dict[str, Any]] = []
            for line in results[0].read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                rows.append(
                    {"params": record["params"], "phenotype": self._phenotype(record)}
                )
            return rows

    def _run(
        self,
        base_path: Path,
        search_path: Path,
        output_dir: Path,
        *,
        count: int,
        seed: int,
        extra_args: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = {"SPECTER_ARTIFACT_ROOT": str(output_dir.parent / "artifacts")}
        command = [
            str(self.binary), "discover", "local",
            "--config", str(base_path),
            "--search", str(search_path),
            "--output", str(output_dir),
            "--count", str(count),
            "--seed", str(seed),
            "--no-promotion",
        ]
        if extra_args is not None:
            command += extra_args
        if self.backend is not None:
            command += ["--backend", self.backend]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            env=_merged_env(environment),
            cwd=str(self.dossier_root),
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"LeniaCLI failed (code {completed.returncode}):\n{completed.stderr[-2000:]}"
            )
        return completed

    def _phenotype(self, record: dict[str, Any]) -> dict[str, Any]:
        metrics = record["metrics"]
        output: dict[str, Any] = {key: metrics.get(key) for key in METRIC_KEYS}
        displacement = output.get("displacement")
        path_length = output.get("path_length")
        output["path_tortuosity"] = (
            path_length / displacement if displacement and displacement > 1e-9 else None
        )
        output["movement_efficiency"] = (
            displacement / path_length if path_length and path_length > 1e-9 else None
        )
        output["filters_passed"] = record.get("filters_passed")
        return output

    def evaluate(self, genotype: dict[str, Any], *, init_seed: int | None = None) -> dict[str, Any]:
        seed = self.init_seed if init_seed is None else init_seed
        config = self._explicit_config(genotype, seed)
        with tempfile.TemporaryDirectory() as raw_workdir:
            workdir = Path(raw_workdir)
            base_path = workdir / "base.json"
            base_path.write_text(json.dumps(config), encoding="utf-8")
            search_path = workdir / "search.json"
            search_path.write_text(json.dumps(self._search_config()), encoding="utf-8")
            output_dir = workdir / "out"
            self._run(base_path, search_path, output_dir, count=1, seed=seed)
            results = list(output_dir.rglob("results.jsonl"))
            if not results:
                raise RuntimeError("No results.jsonl produced for evaluation")
            record = json.loads(results[0].read_text(encoding="utf-8").splitlines()[0])
        return self._phenotype(record)

    def developmental_trajectory(
        self, genotype: dict[str, Any], *, init_seed: int | None = None, stride: int = 50
    ) -> dict[str, Any]:
        """Run one genotype and return its path through morphospace, the sequence of
        12 common-morphology shape axes at every `stride` steps, plus the terminal
        phenotype. This is the per-step developmental trajectory that the warehouse
        does not store; it makes the basins-and-fibers duality measurable, the
        forward flow toward an attractor that the inverse fiber lands in.
        """
        seed = self.init_seed if init_seed is None else init_seed
        config = self._explicit_config(genotype, seed)
        with tempfile.TemporaryDirectory() as raw_workdir:
            workdir = Path(raw_workdir)
            base_path = workdir / "base.json"
            base_path.write_text(json.dumps(config), encoding="utf-8")
            search_path = workdir / "search.json"
            search_path.write_text(json.dumps(self._search_config()), encoding="utf-8")
            output_dir = workdir / "out"
            self._run(
                base_path, search_path, output_dir, count=1, seed=seed,
                extra_args=["--frames", "--frame-stride", str(stride)],
            )
            results = list(output_dir.rglob("results.jsonl"))
            if not results:
                raise RuntimeError("No results.jsonl produced for trajectory")
            record = json.loads(results[0].read_text(encoding="utf-8").splitlines()[0])
            path: list[dict[str, Any]] = []
            for frame_path in sorted(output_dir.rglob("frame_*.png")):
                step = int(frame_path.stem.split("_")[1])
                axes = field_to_axes(np.asarray(Image.open(frame_path), dtype=np.float64))
                if axes is not None:
                    path.append({"step": step, "axes": axes})
        return {"terminal": self._phenotype(record), "path": path}


def field_to_axes(field: np.ndarray) -> dict[str, float] | None:
    """Map one density field (a frame) to the 12 common-morphology shape axes, the
    same basis the morphospace warehouse uses, by treating occupied cells as a
    weighted point cloud.
    """
    ys, xs = np.nonzero(field > 0.0)
    if xs.size < 2:
        return None
    points = np.column_stack([xs.astype(np.float64), ys.astype(np.float64)])
    weights = field[ys, xs].astype(np.float64)
    return point_cloud_shape_features(points, weights=weights)


def _merged_env(extra: dict[str, str]) -> dict[str, str]:
    import os

    environment = dict(os.environ)
    environment.update(extra)
    return environment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a fresh (genotype, phenotype) dataset by sampling the "
        "forward map of one fully-specified regime."
    )
    parser.add_argument("--base", default="configs/base/paper_base_3k_1c_128.json")
    parser.add_argument("--search", default="configs/search/search_crossmap_motion.json")
    parser.add_argument("--count", type=int, default=5000)
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument(
        "--output",
        default="outputs/anatomical-compiler/forward_dataset_3k_1c_128.jsonl",
    )
    args = parser.parse_args(argv)

    root = Path.cwd()
    simulator = ForwardSimulator(
        root / args.base,
        root / args.search,
        dossier_root=root,
        steps=args.steps,
        timeout_seconds=3600.0,
    )
    rows = simulator.generate_dataset(args.count, seed_start=args.seed_start)
    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    stable = sum(1 for row in rows if row["phenotype"]["is_stable"])
    print(f"Wrote {len(rows)} rows ({stable} stable) to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
