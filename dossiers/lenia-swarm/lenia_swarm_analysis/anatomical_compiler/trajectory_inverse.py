"""Prepare blinded, trajectory-aware inverse searches for the native Lenia runtime.

The inverse experiment keeps the implementation family and initial state fixed while
hiding selected rule parameters. It emits paired ES configurations: one sees only the
last observed state, while the other sees the same state plus earlier trajectory
moments. Comparing them isolates the information supplied by time.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

DEFAULT_INITIAL_PARAMS = {"r": 1.0, "m": 0.12, "s": 0.024, "R": 10.0}
DEFAULT_PARAM_RANGES = {
    "r": [1.0, 1.0],
    "b": [1.0, 1.0],
    "w": [0.0, 0.0],
    "a": [0.0, 0.0],
    "m": [0.10, 0.20],
    "s": [0.010, 0.030],
    "h": [1.0, 1.0],
    "R": [9.0, 17.0],
}


def image_state_patch(path: Path, center: tuple[int, int]) -> dict[str, Any]:
    """Encode a grayscale simulation frame as a one-channel f32 state patch."""
    with Image.open(path) as image:
        field = np.asarray(image.convert("L"), dtype=np.float32) / 255.0
    height, width = field.shape
    return {
        "center": list(center),
        "width": width,
        "height": height,
        "channels": 1,
        "encoding": "f32le",
        "data": base64.b64encode(field.astype("<f4").tobytes(order="C")).decode("ascii"),
    }


def blind_runtime_config(
    source: dict[str, Any], initial_params: dict[str, float] | None = None
) -> dict[str, Any]:
    """Return a runtime config with the target rule replaced by a declared wrong start."""
    config = copy.deepcopy(source)
    mode = config.get("implementation", {}).get("mode")
    if mode != "qd24_additive_v1":
        raise ValueError(f"trajectory inverse currently requires qd24_additive_v1, got {mode!r}")

    declared = DEFAULT_INITIAL_PARAMS | (initial_params or {})
    params = config["params"]
    params["r"] = [declared["r"]]
    params["m"] = [declared["m"]]
    params["s"] = [declared["s"]]
    params["R"] = declared["R"]
    params["mode"] = "explicit"
    params["ranges"] = None

    # Runtime provenance can contain native parameters. It is irrelevant to simulation
    # and must not travel into a blinded inverse-search input.
    config["provenance"] = {
        "experiment": "blinded_trajectory_inverse",
        "known_family": mode,
        "hidden_parameters": ["m", "s", "R"],
    }
    return config


def es_config(
    *,
    output_dir: Path,
    steps: list[int],
    patches: list[dict[str, Any]],
    generations: int,
    population: int,
    seed: int,
    temporal: bool,
    sigma: float,
    learning_rate: float,
) -> dict[str, Any]:
    """Build an ES search config for either final-state or trajectory evidence."""
    if not steps or len(steps) != len(patches):
        raise ValueError("steps and patches must be non-empty and have equal length")
    fitness: dict[str, Any] = {
        "objective": "template_sequence",
        "target_step": max(steps),
        "angle_threshold": 0.01,
        "morphology_threshold": 0.03,
        "template_sequence_reward": 1.0,
        "template_sequence_mass_penalty": 0.25,
        "template_sequence_support_penalty": 0.25,
        "template_sequence_steps": steps,
        "template_sequence_state_patches": patches,
    }
    if temporal:
        if len(steps) < 2:
            raise ValueError("temporal search requires at least two observed states")
        fitness |= {
            "template_sequence_change_penalty": 0.35,
            "template_sequence_delta_reward": 0.25,
            "template_sequence_signed_delta_reward": 0.25,
        }
    return {
        "output_dir": str(output_dir),
        "generations": generations,
        "population": population,
        "sigma": sigma,
        "learning_rate": learning_rate,
        "seed": seed,
        "steps": max(steps),
        "fitness": fitness,
        "fitness_shaping": "centered_rank",
        "include_parent": True,
        "init_patch": None,
        "initial_kernel_params": None,
        "param_ranges": DEFAULT_PARAM_RANGES,
    }


def prepare_experiment(
    *,
    source_config: Path,
    frames_dir: Path,
    output_dir: Path,
    observed_steps: list[int],
    generations: int = 30,
    population: int = 24,
    seed: int = 41,
    sigma: float = 1.4,
    learning_rate: float = 0.10,
) -> dict[str, Path]:
    """Write paired inverse-search inputs and a manifest to ``output_dir``."""
    source = json.loads(source_config.read_text())
    grid = source["grid"]
    center = (int(grid["sx"]) // 2, int(grid["sy"]) // 2)
    frame_paths = [frames_dir / f"frame_{step:06d}.png" for step in observed_steps]
    missing = [path for path in frame_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing observed frames: {', '.join(map(str, missing))}")

    patches = [image_state_patch(path, center) for path in frame_paths]
    blinded = blind_runtime_config(source)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "base": output_dir / "blinded-base.json",
        "still": output_dir / "still-es.json",
        "trajectory": output_dir / "trajectory-es.json",
        "manifest": output_dir / "experiment.json",
    }
    still_step = [observed_steps[-1]]
    still_patch = [patches[-1]]
    paths["base"].write_text(json.dumps(blinded, indent=2) + "\n")
    paths["still"].write_text(
        json.dumps(
            es_config(
                output_dir=output_dir / "still-run",
                steps=still_step,
                patches=still_patch,
                generations=generations,
                population=population,
                seed=seed,
                temporal=False,
                sigma=sigma,
                learning_rate=learning_rate,
            ),
            indent=2,
        )
        + "\n"
    )
    paths["trajectory"].write_text(
        json.dumps(
            es_config(
                output_dir=output_dir / "trajectory-run",
                steps=observed_steps,
                patches=patches,
                generations=generations,
                population=population,
                seed=seed,
                temporal=True,
                sigma=sigma,
                learning_rate=learning_rate,
            ),
            indent=2,
        )
        + "\n"
    )
    manifest = {
        "question": "How much does temporal evidence improve rule recovery?",
        "known": ["implementation family", "kernel profile", "growth profile", "initial state"],
        "hidden": ["m", "s", "R"],
        "initial_parameters": DEFAULT_INITIAL_PARAMS,
        "parameter_ranges": DEFAULT_PARAM_RANGES,
        "optimizer": {"sigma": sigma, "learning_rate": learning_rate},
        "observed_steps": observed_steps,
        "source_frames": [str(path.resolve()) for path in frame_paths],
        "searches": {
            "still": {"observed_steps": still_step, "config": paths["still"].name},
            "trajectory": {
                "observed_steps": observed_steps,
                "config": paths["trajectory"].name,
            },
        },
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2) + "\n")
    return paths


def prepare_refinement_experiment(
    *,
    source_config: Path,
    coarse_best: Path,
    coarse_es: Path,
    output_dir: Path,
    generations: int = 12,
    population: int | None = None,
    seed: int = 43,
    sigma: float = 0.15,
    learning_rate: float = 0.05,
) -> dict[str, Path]:
    """Prepare a narrow ES stage centered on the winner of a broad search."""
    source = json.loads(source_config.read_text())
    winner = json.loads(coarse_best.read_text())
    coarse = json.loads(coarse_es.read_text())
    winner_params = winner["params"]
    initial_params = {
        "r": float(winner_params["r"][0]),
        "m": float(winner_params["m"][0]),
        "s": float(winner_params["s"][0]),
        "R": float(winner_params["R"]),
    }
    refined_base = blind_runtime_config(source, initial_params)
    refined_es = copy.deepcopy(coarse)
    refined_es |= {
        "output_dir": str(output_dir / "refine-run"),
        "generations": generations,
        "population": population or int(coarse["population"]),
        "seed": seed,
        "sigma": sigma,
        "learning_rate": learning_rate,
        "include_parent": True,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "base": output_dir / "refined-base.json",
        "es": output_dir / "refine-es.json",
        "manifest": output_dir / "refinement.json",
    }
    paths["base"].write_text(json.dumps(refined_base, indent=2) + "\n")
    paths["es"].write_text(json.dumps(refined_es, indent=2) + "\n")
    manifest = {
        "question": "Can a narrow second stage improve the broad-search winner?",
        "coarse_best": str(coarse_best.resolve()),
        "coarse_fitness": float(winner["fitness"]),
        "initial_parameters": initial_params,
        "optimizer": {
            "generations": generations,
            "population": refined_es["population"],
            "seed": seed,
            "sigma": sigma,
            "learning_rate": learning_rate,
        },
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2) + "\n")
    return paths


def parse_steps(value: str) -> list[int]:
    steps = sorted({int(part.strip()) for part in value.split(",") if part.strip()})
    if not steps or steps[0] <= 0:
        raise argparse.ArgumentTypeError("steps must be a comma-separated list of positive integers")
    return steps


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-config", required=True, type=Path)
    parser.add_argument("--frames-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--steps", type=parse_steps, default=parse_steps("100,200,300"))
    parser.add_argument("--generations", type=int, default=30)
    parser.add_argument("--population", type=int, default=24)
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--sigma", type=float, default=1.4)
    parser.add_argument("--learning-rate", type=float, default=0.10)
    args = parser.parse_args()
    paths = prepare_experiment(
        source_config=args.source_config,
        frames_dir=args.frames_dir,
        output_dir=args.output,
        observed_steps=args.steps,
        generations=args.generations,
        population=args.population,
        seed=args.seed,
        sigma=args.sigma,
        learning_rate=args.learning_rate,
    )
    print(json.dumps({key: str(value) for key, value in paths.items()}, indent=2))


def refinement_main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a narrow inverse-search stage from a broad-search winner."
    )
    parser.add_argument("--source-config", required=True, type=Path)
    parser.add_argument("--coarse-best", required=True, type=Path)
    parser.add_argument("--coarse-es", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--generations", type=int, default=12)
    parser.add_argument("--population", type=int)
    parser.add_argument("--seed", type=int, default=43)
    parser.add_argument("--sigma", type=float, default=0.15)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    args = parser.parse_args()
    paths = prepare_refinement_experiment(
        source_config=args.source_config,
        coarse_best=args.coarse_best,
        coarse_es=args.coarse_es,
        output_dir=args.output,
        generations=args.generations,
        population=args.population,
        seed=args.seed,
        sigma=args.sigma,
        learning_rate=args.learning_rate,
    )
    print(json.dumps({key: str(value) for key, value in paths.items()}, indent=2))


if __name__ == "__main__":
    main()
