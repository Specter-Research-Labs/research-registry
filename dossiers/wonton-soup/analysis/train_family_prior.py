from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from analysis.learning_common import build_sig_features, load_goal_cache
from analysis.logs import iter_provider_runs, read_json, relpath_under, write_json_atomic
from prover.goal_features import FEATURE_DIM
from prover.mcts import TACTIC_FAMILIES


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass(frozen=True)
class TrainResult:
    provider: str | None
    model_path: Path
    examples: int


def _iter_goal_cache_examples(goal_cache: dict[str, Any]) -> list[tuple[str, int, int, int]]:
    """Return aggregated (sig, family_idx, success_count, total_count) tuples."""
    entries = goal_cache.get("entries", {})
    if not isinstance(entries, dict):
        raise ValueError("goal_cache.entries must be a dict")

    examples: list[tuple[str, int, int, int]] = []
    for sig, entry in entries.items():
        if not isinstance(sig, str) or not isinstance(entry, dict):
            continue
        occurrences = entry.get("occurrences", {})
        if not isinstance(occurrences, dict):
            continue
        fam_success: dict[int, int] = {}
        fam_total: dict[int, int] = {}
        for occ in occurrences.values():
            if not isinstance(occ, dict):
                continue
            outcomes = occ.get("outcomes", {})
            if not isinstance(outcomes, dict):
                continue
            for fam_key, vals in outcomes.items():
                try:
                    fam_idx = int(fam_key)
                except (TypeError, ValueError):
                    continue
                if not isinstance(vals, list):
                    continue
                total = len(vals)
                success = sum(1 for v in vals if v is True)
                if total <= 0:
                    continue
                fam_success[fam_idx] = fam_success.get(fam_idx, 0) + success
                fam_total[fam_idx] = fam_total.get(fam_idx, 0) + total
        for fam_idx, total in fam_total.items():
            success = fam_success.get(fam_idx, 0)
            examples.append((sig, fam_idx, success, total))
    examples.sort(key=lambda t: (t[0], t[1]))
    return examples


def _feature_stats(
    sig_features: dict[str, list[float]],
    examples: list[tuple[str, int, int, int]],
) -> tuple[np.ndarray, np.ndarray]:
    total = 0.0
    sum_x = np.zeros(FEATURE_DIM, dtype=np.float64)
    sum_x2 = np.zeros(FEATURE_DIM, dtype=np.float64)
    for sig, _, _, n in examples:
        feats = sig_features.get(sig)
        if feats is None:
            continue
        x = np.asarray(feats, dtype=np.float64)
        if x.shape != (FEATURE_DIM,):
            continue
        w = float(n)
        total += w
        sum_x += w * x
        sum_x2 += w * (x * x)
    if total <= 0:
        mean = np.zeros(FEATURE_DIM, dtype=np.float32)
        std = np.ones(FEATURE_DIM, dtype=np.float32)
        return mean, std
    mean = (sum_x / total).astype(np.float32)
    var = (sum_x2 / total) - (mean.astype(np.float64) ** 2)
    var = np.maximum(var, 0.0).astype(np.float32)
    std = np.sqrt(var).astype(np.float32)
    std = np.where(std > 1e-6, std, 1.0).astype(np.float32)
    return mean, std


def train_family_prior_from_run(
    run_dir: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
    epochs: int = 25,
    lr: float = 0.2,
    l2: float = 1e-3,
    max_weight: int = 50,
) -> list[TrainResult]:
    results: list[TrainResult] = []
    providers = iter_provider_runs(run_dir)

    for provider_run in providers:
        single_run_dir = provider_run.run_dir
        run_config = read_json(single_run_dir / "run_config.json")
        if not isinstance(run_config, dict):
            raise ValueError("run_config.json must be a dict")
        run_id = run_config.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_config.json missing run_id")

        goal_cache = load_goal_cache(single_run_dir)
        sig_features = build_sig_features(goal_cache)
        examples = _iter_goal_cache_examples(goal_cache)
        if not examples:
            raise ValueError(f"No outcomes found in goal_cache for: {single_run_dir}")

        mean, std = _feature_stats(sig_features, examples)

        n_fam = len(TACTIC_FAMILIES)
        w = np.zeros((n_fam, FEATURE_DIM), dtype=np.float32)
        b = np.zeros(n_fam, dtype=np.float32)

        for _ in range(epochs):
            for sig, fam_idx, success, total in examples:
                feats = sig_features.get(sig)
                if feats is None:
                    continue
                x = np.asarray(feats, dtype=np.float32)
                if x.shape != (FEATURE_DIM,):
                    continue
                x = (x - mean) / std

                if fam_idx < 0 or fam_idx >= n_fam:
                    fam_idx = n_fam - 1
                y = success / total
                weight = min(int(total), max_weight)
                z = float(w[fam_idx].dot(x) + b[fam_idx])
                p = _sigmoid(z)
                err = weight * (p - y)
                # L2 regularization on weights.
                w[fam_idx] -= lr * (err * x + (l2 * w[fam_idx]))
                b[fam_idx] -= lr * err

        model = {
            "schema_version": 1,
            "model": "family_prior_logreg",
            "families": list(TACTIC_FAMILIES),
            "feature_dim": FEATURE_DIM,
            "scaler": {
                "mean": [float(x) for x in mean.tolist()],
                "std": [float(x) for x in std.tolist()],
            },
            "weights": [[float(x) for x in row.tolist()] for row in w],
            "bias": [float(x) for x in b.tolist()],
            "meta": {
                "trained_at": datetime.now().isoformat(timespec="seconds"),
                "run_id": run_id,
                "provider": provider_run.provider,
                "source_run_subdir": relpath_under(run_dir, single_run_dir),
                "hyperparams": {
                    "epochs": epochs,
                    "lr": lr,
                    "l2": l2,
                    "max_weight": max_weight,
                },
                "examples": len(examples),
            },
        }

        dest = out_dir / run_id
        if provider_run.provider:
            dest = dest / f"provider={provider_run.provider}"
        dest.mkdir(parents=True, exist_ok=True)
        model_path = dest / "family_prior.json"
        if not overwrite and model_path.exists():
            raise FileExistsError(f"Refusing to overwrite: {model_path}")
        write_json_atomic(model_path, model)

        results.append(
            TrainResult(
                provider=provider_run.provider,
                model_path=model_path,
                examples=len(examples),
            )
        )

    return results
