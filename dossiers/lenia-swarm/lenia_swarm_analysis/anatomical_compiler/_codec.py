"""Flat-vector layout of a Flow Lenia genotype params dict."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


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
