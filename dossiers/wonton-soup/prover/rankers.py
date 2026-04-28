from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from prover.mcts import TACTIC_FAMILIES
from prover.providers.base import normalize_tactic, tactic_family


def _sigmoid(x: float) -> float:
    # Numerically stable enough for our small models.
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass(frozen=True)
class FeatureScaler:
    mean: np.ndarray
    std: np.ndarray

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / self.std

    @classmethod
    def from_lists(cls, mean: list[float], std: list[float]) -> FeatureScaler:
        m = np.asarray(mean, dtype=np.float32)
        s = np.asarray(std, dtype=np.float32)
        if m.ndim != 1 or s.ndim != 1 or m.shape != s.shape:
            raise ValueError("Invalid scaler shapes")
        safe = np.where(s > 0, s, 1.0).astype(np.float32)
        return cls(mean=m, std=safe)


@dataclass(frozen=True)
class FamilyPriorModel:
    schema_version: int
    families: list[str]
    feature_dim: int
    scaler: FeatureScaler
    weights: np.ndarray  # (F, D)
    bias: np.ndarray  # (F,)
    meta: dict[str, Any]

    def family_index(self, family: str) -> int:
        try:
            return self.families.index(family)
        except ValueError:
            try:
                return self.families.index("other")
            except ValueError:
                return len(self.families) - 1

    def score(self, goal_features: list[float] | None, family: str) -> float:
        if goal_features is None:
            x = np.zeros(self.feature_dim, dtype=np.float32)
        else:
            x = np.asarray(goal_features, dtype=np.float32)
            if x.shape != (self.feature_dim,):
                x = np.zeros(self.feature_dim, dtype=np.float32)
        x = self.scaler.transform(x)
        fi = self.family_index(family)
        z = float(self.weights[fi].dot(x) + self.bias[fi])
        return _sigmoid(z)

    @classmethod
    def load(cls, path: Path) -> FamilyPriorModel:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("family prior model must be a dict")
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported family prior schema_version")
        families = data.get("families")
        if not isinstance(families, list) or not all(isinstance(f, str) for f in families):
            raise ValueError("families must be a list[str]")
        feature_dim = data.get("feature_dim")
        if not isinstance(feature_dim, int) or feature_dim <= 0:
            raise ValueError("feature_dim must be a positive int")
        scaler_data = data.get("scaler", {})
        if not isinstance(scaler_data, dict):
            raise ValueError("scaler must be a dict")
        mean = scaler_data.get("mean")
        std = scaler_data.get("std")
        if not isinstance(mean, list) or not isinstance(std, list):
            raise ValueError("scaler.mean/std must be lists")
        scaler = FeatureScaler.from_lists(mean, std)
        weights = np.asarray(data.get("weights"), dtype=np.float32)
        bias = np.asarray(data.get("bias"), dtype=np.float32)
        if weights.shape != (len(families), feature_dim):
            raise ValueError(f"weights shape must be ({len(families)},{feature_dim})")
        if bias.shape != (len(families),):
            raise ValueError(f"bias shape must be ({len(families)},)")
        meta = data.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}
        return cls(
            schema_version=1,
            families=families,
            feature_dim=feature_dim,
            scaler=scaler,
            weights=weights,
            bias=bias,
            meta=meta,
        )


def family_prior_ranker(
    model: FamilyPriorModel,
    *,
    alpha: float = 1.0,
) -> Callable[[list[tuple[str, float]], int, Any], list[tuple[str, float]]]:
    if not (0.0 <= alpha <= 1.0):
        raise ValueError("alpha must be in [0,1]")

    def rank(
        tactics_with_probs: list[tuple[str, float]],
        iteration: int,
        node: Any,
    ) -> list[tuple[str, float]]:
        goal_features = getattr(node, "goal_features", None)
        scored: list[tuple[float, float, int, str, float]] = []
        for i, (tactic, provider_score) in enumerate(tactics_with_probs):
            t_norm = normalize_tactic(tactic)
            fam = tactic_family(t_norm)
            if fam not in TACTIC_FAMILIES:
                fam = "other"
            m = model.score(goal_features, fam)
            combined = (alpha * m) + ((1.0 - alpha) * float(provider_score))
            scored.append((combined, float(provider_score), i, tactic, provider_score))
        scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
        return [(tactic, provider_score) for _, _, _, tactic, provider_score in scored]

    return rank

