"""Torch-free genotype/phenotype data utilities shared across the compiler modules.

Kept separate from cinn_inverse so the numpy-only analyses (refine, jacobian_fiber,
the Lyapunov diagnostic) do not require the optional torch extra to import.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

# Only the init-robust shape descriptors. Motion metrics (speed, displacement,
# center_velocity, path_length and their ratios) have ~60% coefficient of variation
# across initial conditions for a fixed genotype, because a stable blob's drift
# direction is set by the initial condition, not the genotype; conditioning on them
# would be conditioning on initial-condition noise. The compiler targets morphology.
PHENOTYPE_FIELDS: tuple[str, ...] = (
    "mass_mean",
    "mass_std",
    "occupancy_mean",
    "variance_mean",
    "energy_mean",
    "gyration",
    "complexity_mean",
)


@dataclass
class GenotypeCodec:
    """Bijection between a genotype params dict and a flat vector, in the same
    layout as the fiber analysis (R, then per kernel m, s, h, r, a, b, w)."""

    kernel_count: int
    bump_lengths: tuple[int, int, int]

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> GenotypeCodec:
        return cls(
            kernel_count=len(params["m"]),
            bump_lengths=(len(params["a"][0]), len(params["b"][0]), len(params["w"][0])),
        )

    def flatten(self, params: dict[str, Any]) -> list[float]:
        out: list[float] = [float(params["R"])]
        for index in range(self.kernel_count):
            out.extend(
                (
                    float(params["m"][index]),
                    float(params["s"][index]),
                    float(params["h"][index]),
                    float(params["r"][index]),
                )
            )
            out.extend(float(v) for v in params["a"][index])
            out.extend(float(v) for v in params["b"][index])
            out.extend(float(v) for v in params["w"][index])
        return out

    def unflatten(self, vector: np.ndarray) -> dict[str, Any]:
        la, lb, lw = self.bump_lengths
        cursor = 1
        params: dict[str, Any] = {
            "R": float(vector[0]),
            "m": [],
            "s": [],
            "h": [],
            "r": [],
            "a": [],
            "b": [],
            "w": [],
        }
        for _ in range(self.kernel_count):
            params["m"].append(float(vector[cursor]))
            params["s"].append(float(vector[cursor + 1]))
            params["h"].append(float(vector[cursor + 2]))
            params["r"].append(float(vector[cursor + 3]))
            cursor += 4
            params["a"].append([float(v) for v in vector[cursor : cursor + la]])
            cursor += la
            params["b"].append([float(v) for v in vector[cursor : cursor + lb]])
            cursor += lb
            params["w"].append([float(v) for v in vector[cursor : cursor + lw]])
            cursor += lw
        return params

    @property
    def dim(self) -> int:
        return 1 + self.kernel_count * (4 + sum(self.bump_lengths))


@dataclass
class Standardizer:
    mean: np.ndarray
    std: np.ndarray

    @classmethod
    def fit(cls, matrix: np.ndarray) -> Standardizer:
        std = matrix.std(axis=0)
        std[std < 1e-8] = 1.0
        return cls(mean=matrix.mean(axis=0), std=std)

    def forward(self, matrix: np.ndarray) -> np.ndarray:
        return (matrix - self.mean) / self.std

    def inverse(self, matrix: np.ndarray) -> np.ndarray:
        return matrix * self.std + self.mean


def load_dataset(dataset_path: Path) -> tuple[GenotypeCodec, np.ndarray, np.ndarray]:
    genotype_rows: list[list[float]] = []
    phenotype_rows: list[list[float]] = []
    codec: GenotypeCodec | None = None
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if not record["phenotype"].get("is_stable"):
                continue
            if any(record["phenotype"].get(f) is None for f in PHENOTYPE_FIELDS):
                continue
            if codec is None:
                codec = GenotypeCodec.from_params(record["params"])
            genotype_rows.append(codec.flatten(record["params"]))
            phenotype_rows.append([float(record["phenotype"][f]) for f in PHENOTYPE_FIELDS])
    if codec is None:
        raise SystemExit("No usable stable rows in dataset")
    return (
        codec,
        np.asarray(genotype_rows, dtype=np.float64),
        np.asarray(phenotype_rows, dtype=np.float64),
    )


def clamp_params(
    params: dict[str, Any], ranges: dict[str, list[float]]
) -> tuple[dict[str, Any], int]:
    clamped = 0

    def clamp_scalar(value: float, key: str) -> float:
        nonlocal clamped
        low, high = ranges[key]
        bounded = min(max(value, low), high)
        if bounded != value:
            clamped += 1
        return bounded

    out: dict[str, Any] = {"R": clamp_scalar(params["R"], "R")}
    for scalar_key in ("m", "s", "h", "r"):
        out[scalar_key] = [clamp_scalar(v, scalar_key) for v in params[scalar_key]]
    for vector_key in ("a", "b", "w"):
        out[vector_key] = [
            [clamp_scalar(v, vector_key) for v in kernel] for kernel in params[vector_key]
        ]
    return out, clamped
