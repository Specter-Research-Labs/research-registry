from __future__ import annotations

import argparse
import gzip
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy import optimize, stats

from runtime_paths import resolve_logs_root

CONTROL_NAMES = {"control_null", "random_nonpath", "random_nonpath_control"}


@dataclass(frozen=True)
class BasinMetrics:
    theorem: str
    seeds: int
    solved_seeds: int
    solve_rate: float
    unique_structures: int
    dominant_structure_frequency: float
    entropy_bits: float
    normalized_entropy: float


@dataclass(frozen=True)
class InterventionRow:
    theorem: str
    intervention: str
    blocked: tuple[str, ...]
    baseline_solved: bool
    solved: bool
    is_control: bool
    rerouted: bool
    ged: float | None
    wild_iterations: int | None


def _read_json(path: Path) -> Any:
    if path.name.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _shannon_entropy(counts: list[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in counts:
        if count <= 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def _load_basin_metrics(basin_dir: Path) -> dict[str, BasinMetrics]:
    metrics: dict[str, BasinMetrics] = {}
    for path in sorted(basin_dir.glob("*/basin_analysis.json")):
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue
        theorem = payload.get("theorem_name")
        if not isinstance(theorem, str):
            theorem = path.parent.name
        seed_results = payload.get("seed_results")
        seeds = (
            len(seed_results)
            if isinstance(seed_results, list)
            else len(payload.get("seeds", []))
        )
        solved_seeds = 0
        if isinstance(seed_results, list):
            solved_seeds = sum(
                1 for row in seed_results if isinstance(row, dict) and row.get("solved") is True
            )
        structure_distribution = payload.get("structure_distribution")
        if isinstance(structure_distribution, dict):
            counts = [
                int(value)
                for value in structure_distribution.values()
                if isinstance(value, int)
            ]
        else:
            counts = []
        unique_structures = int(payload.get("unique_structures") or len(counts))
        entropy = _shannon_entropy(counts)
        max_entropy = math.log2(unique_structures) if unique_structures > 1 else 0.0
        metrics[theorem] = BasinMetrics(
            theorem=theorem,
            seeds=seeds,
            solved_seeds=solved_seeds,
            solve_rate=float(payload.get("solve_rate") or 0.0),
            unique_structures=unique_structures,
            dominant_structure_frequency=float(payload.get("dominant_structure_frequency") or 0.0),
            entropy_bits=entropy,
            normalized_entropy=(entropy / max_entropy) if max_entropy > 0 else 0.0,
        )
    return metrics


def _comparison_payloads(lesion_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    comparisons: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(lesion_dir.glob("*/*_comparison.json")):
        payload = _read_json(path)
        if isinstance(payload, dict):
            comparisons[(path.parent.name, path.name.removesuffix("_comparison.json"))] = payload
    return comparisons


def _ged_value(payload: dict[str, Any]) -> float | None:
    for key in ("ged_search_graph", "ged_search_graph_soft", "ged_proof_graph", "ged_trace_graph"):
        raw = payload.get(key)
        if not isinstance(raw, dict):
            continue
        value = raw.get("normalized")
        if not isinstance(value, (int, float)):
            value = raw.get("value")
        if isinstance(value, (int, float)):
            return float(value)
    value = payload.get("ged")
    return float(value) if isinstance(value, (int, float)) else None


def _intervention_name(row: dict[str, Any]) -> str:
    for key in ("name", "intervention", "variant"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return "intervention"


def _load_intervention_rows(lesion_dir: Path) -> list[InterventionRow]:
    summary = None
    for candidate in (lesion_dir / "summary.json.gz", lesion_dir / "summary.json"):
        if candidate.exists():
            summary = _read_json(candidate)
            break
    if not isinstance(summary, dict):
        raise FileNotFoundError(f"summary.json[.gz] not found under {lesion_dir}")

    comparisons = _comparison_payloads(lesion_dir)
    rows: list[InterventionRow] = []
    for theorem in summary.get("theorems", []) or []:
        if not isinstance(theorem, dict) or not isinstance(theorem.get("name"), str):
            continue
        theorem_name = theorem["name"]
        wild = theorem.get("wild_type") if isinstance(theorem.get("wild_type"), dict) else {}
        wild_iterations = wild.get("iterations")
        if not isinstance(wild_iterations, int):
            wild_iterations = None
        for raw_intervention in theorem.get("interventions", []) or []:
            if not isinstance(raw_intervention, dict):
                continue
            name = _intervention_name(raw_intervention)
            comparison = comparisons.get((theorem_name, name))
            comparison_or_raw = comparison if comparison is not None else raw_intervention
            blocked = raw_intervention.get("blocked")
            if not isinstance(blocked, list):
                blocked = []
            is_control = bool(raw_intervention.get("is_control")) or name in CONTROL_NAMES
            rows.append(
                InterventionRow(
                    theorem=theorem_name,
                    intervention=name,
                    blocked=tuple(str(item) for item in blocked),
                    baseline_solved=bool(raw_intervention.get("baseline_solved")),
                    solved=bool(raw_intervention.get("solved")),
                    is_control=is_control,
                    rerouted=bool(comparison_or_raw.get("hash_mismatch")),
                    ged=_ged_value(comparison_or_raw),
                    wild_iterations=wild_iterations,
                )
            )
    return rows


def _bucket(width: int) -> str:
    if width <= 0:
        return "0"
    if width == 1:
        return "1"
    if width == 2:
        return "2"
    return "3+"


def _correlation(xs: list[float], ys: list[float]) -> dict[str, Any]:
    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return {
            "n": len(xs),
            "pearson_r": None,
            "pearson_p": None,
            "spearman_r": None,
            "spearman_p": None,
        }
    pearson = stats.pearsonr(xs, ys)
    spearman = stats.spearmanr(xs, ys)
    return {
        "n": len(xs),
        "pearson_r": float(pearson.statistic),
        "pearson_p": float(pearson.pvalue),
        "spearman_r": float(spearman.statistic),
        "spearman_p": float(spearman.pvalue),
    }


def _zscore(values: list[float]) -> list[float]:
    if not values:
        return []
    arr = np.asarray(values, dtype=float)
    std = float(arr.std())
    if std == 0.0:
        return [0.0 for _ in values]
    mean = float(arr.mean())
    return [float((value - mean) / std) for value in values]


def _ridge_logistic(
    rows: list[dict[str, Any]],
    *,
    outcome: str,
    feature: str,
) -> dict[str, Any]:
    usable = [row for row in rows if isinstance(row.get(outcome), bool)]
    if len(usable) < 8 or len({row[outcome] for row in usable}) < 2:
        return {"n": len(usable), "available": False, "reason": "insufficient outcome variation"}

    interventions = sorted({str(row["intervention"]) for row in usable})
    dropped_intervention = interventions[0] if interventions else None
    intervention_columns = interventions[1:]
    width_values = _zscore([float(row[feature]) for row in usable])
    difficulty_raw = [
        float(row["wild_iterations"]) if isinstance(row.get("wild_iterations"), int) else math.nan
        for row in usable
    ]
    finite_difficulty = [value for value in difficulty_raw if math.isfinite(value)]
    fill = float(np.median(finite_difficulty)) if finite_difficulty else 0.0
    difficulty_values = _zscore(
        [value if math.isfinite(value) else fill for value in difficulty_raw]
    )

    feature_names = ["intercept", f"{feature}_z", "wild_iterations_z"] + [
        f"intervention={name}" for name in intervention_columns
    ]
    x_rows: list[list[float]] = []
    y = np.asarray([1.0 if row[outcome] else 0.0 for row in usable], dtype=float)
    for idx, row in enumerate(usable):
        x_rows.append(
            [1.0, width_values[idx], difficulty_values[idx]]
            + [1.0 if row["intervention"] == name else 0.0 for name in intervention_columns]
        )
    x = np.asarray(x_rows, dtype=float)
    ridge = 1.0

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        logits = x @ beta
        probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -35, 35)))
        eps = 1e-9
        nll = -float(np.sum(y * np.log(probs + eps) + (1.0 - y) * np.log(1.0 - probs + eps)))
        penalty = 0.5 * ridge * float(np.sum(beta[1:] ** 2))
        grad = x.T @ (probs - y)
        grad[1:] += ridge * beta[1:]
        return nll + penalty, grad

    result = optimize.minimize(
        lambda beta: objective(beta)[0],
        np.zeros(x.shape[1], dtype=float),
        jac=lambda beta: objective(beta)[1],
        method="BFGS",
    )
    beta = result.x
    return {
        "n": len(usable),
        "available": True,
        "outcome_rate": float(y.mean()),
        "feature": feature,
        "ridge_penalty": ridge,
        "dropped_intervention": dropped_intervention,
        "converged": bool(result.success),
        "coefficients": {
            name: float(value) for name, value in zip(feature_names, beta, strict=True)
        },
        "odds_ratio_for_feature": float(math.exp(beta[1])),
    }


def build_summary(
    *,
    basin_dir: Path,
    lesion_dir: Path,
    provider: str,
    run_id: str | None,
) -> dict[str, Any]:
    basin = _load_basin_metrics(basin_dir)
    interventions = _load_intervention_rows(lesion_dir)
    by_theorem: dict[str, list[InterventionRow]] = defaultdict(list)
    for row in interventions:
        by_theorem[row.theorem].append(row)

    joined_theorems = sorted(set(basin) & set(by_theorem))
    theorem_rows: list[dict[str, Any]] = []
    model_rows: list[dict[str, Any]] = []
    buckets: dict[str, Counter[str]] = defaultdict(Counter)

    for theorem in joined_theorems:
        b = basin[theorem]
        path_rows = [
            row
            for row in by_theorem[theorem]
            if row.baseline_solved and not row.is_control
        ]
        control_rows = [
            row
            for row in by_theorem[theorem]
            if row.baseline_solved and row.is_control
        ]
        recovered = sum(1 for row in path_rows if row.solved)
        rerouted = sum(1 for row in path_rows if row.solved and row.rerouted)
        control_recovered = sum(1 for row in control_rows if row.solved)
        bucket = _bucket(b.unique_structures)
        buckets[bucket]["theorems"] += 1
        buckets[bucket]["path_rows"] += len(path_rows)
        buckets[bucket]["recovered"] += recovered
        buckets[bucket]["rerouted"] += rerouted

        theorem_rows.append(
            {
                "theorem": theorem,
                "provider": provider,
                "basin": b.__dict__,
                "path_block_rows": len(path_rows),
                "path_recovered": recovered,
                "path_recovery_rate": _safe_rate(recovered, len(path_rows)),
                "path_rerouted": rerouted,
                "path_reroute_rate_among_recovered": _safe_rate(rerouted, recovered),
                "control_rows": len(control_rows),
                "control_recovered": control_recovered,
                "control_recovery_rate": _safe_rate(control_recovered, len(control_rows)),
            }
        )

        for row in path_rows:
            model_rows.append(
                {
                    "theorem": theorem,
                    "provider": provider,
                    "intervention": row.intervention,
                    "unique_structures": b.unique_structures,
                    "entropy_bits": b.entropy_bits,
                    "normalized_entropy": b.normalized_entropy,
                    "dominant_structure_frequency": b.dominant_structure_frequency,
                    "wild_iterations": row.wild_iterations,
                    "recovered": row.solved,
                    "rerouted": bool(row.solved and row.rerouted),
                }
            )

    corr_inputs = [
        row
        for row in theorem_rows
        if row["path_block_rows"] > 0 and row["path_recovery_rate"] is not None
    ]
    reroute_inputs = [
        row
        for row in theorem_rows
        if row["path_recovered"] > 0 and row["path_reroute_rate_among_recovered"] is not None
    ]
    bucket_rows = []
    for name in ("0", "1", "2", "3+"):
        counts = buckets[name]
        bucket_rows.append(
            {
                "bucket": name,
                "theorems": counts["theorems"],
                "path_rows": counts["path_rows"],
                "recovered": counts["recovered"],
                "recovery_rate": _safe_rate(counts["recovered"], counts["path_rows"]),
                "rerouted": counts["rerouted"],
                "reroute_rate_among_recovered": _safe_rate(counts["rerouted"], counts["recovered"]),
            }
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "provider": provider,
        "basin_dir": str(basin_dir),
        "lesion_dir": str(lesion_dir),
        "basin_theorems": len(basin),
        "lesion_theorems": len(by_theorem),
        "joined_theorems": len(joined_theorems),
        "path_block_rows": len(model_rows),
        "controls": {
            "control_rows": sum(row["control_rows"] for row in theorem_rows),
            "control_recovered": sum(row["control_recovered"] for row in theorem_rows),
        },
        "bucket_summary": bucket_rows,
        "correlations": {
            "unique_structures_vs_recovery_rate": _correlation(
                [float(row["basin"]["unique_structures"]) for row in corr_inputs],
                [float(row["path_recovery_rate"]) for row in corr_inputs],
            ),
            "entropy_bits_vs_recovery_rate": _correlation(
                [float(row["basin"]["entropy_bits"]) for row in corr_inputs],
                [float(row["path_recovery_rate"]) for row in corr_inputs],
            ),
            "unique_structures_vs_reroute_rate": _correlation(
                [float(row["basin"]["unique_structures"]) for row in reroute_inputs],
                [float(row["path_reroute_rate_among_recovered"]) for row in reroute_inputs],
            ),
            "entropy_bits_vs_reroute_rate": _correlation(
                [float(row["basin"]["entropy_bits"]) for row in reroute_inputs],
                [float(row["path_reroute_rate_among_recovered"]) for row in reroute_inputs],
            ),
        },
        "models": {
            "recovery_unique_structures": _ridge_logistic(
                model_rows,
                outcome="recovered",
                feature="unique_structures",
            ),
            "recovery_entropy_bits": _ridge_logistic(
                model_rows,
                outcome="recovered",
                feature="entropy_bits",
            ),
            "reroute_unique_structures": _ridge_logistic(
                [row for row in model_rows if row["recovered"]],
                outcome="rerouted",
                feature="unique_structures",
            ),
            "reroute_entropy_bits": _ridge_logistic(
                [row for row in model_rows if row["recovered"]],
                outcome="rerouted",
                feature="entropy_bits",
            ),
        },
        "theorems": theorem_rows,
        "model_rows": model_rows,
    }


def _infer_dirs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    logs_root = Path(args.logs_root).expanduser() if args.logs_root else resolve_logs_root()
    if args.basin_dir and args.lesion_dir:
        basin_dir = Path(args.basin_dir).expanduser()
        lesion_dir = Path(args.lesion_dir).expanduser()
        output = (
            Path(args.output).expanduser()
            if args.output
            else lesion_dir.parent / "basin_width_reroute_summary.json"
        )
        return basin_dir, lesion_dir, output
    if not args.program_root:
        raise SystemExit("--program-root is required unless --basin-dir and --lesion-dir are set")
    root = logs_root / args.program_root
    basin_parent = root / "basin" / f"provider={args.provider}"
    seed_dirs = sorted(path for path in basin_parent.glob("seeds=*") if path.is_dir())
    if not seed_dirs:
        raise SystemExit(f"No basin seeds directory found under {basin_parent}")
    basin_dir = seed_dirs[-1]
    lesion_dir = root / "lesions" / f"provider={args.provider}"
    output = (
        Path(args.output).expanduser()
        if args.output
        else root / "basin_width_reroute_summary.json"
    )
    return basin_dir, lesion_dir, output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze basin width against lesion recovery.")
    parser.add_argument("--program-root", type=str, default=None)
    parser.add_argument("--provider", type=str, default="reprover")
    parser.add_argument("--logs-root", type=str, default=None)
    parser.add_argument("--basin-dir", type=str, default=None)
    parser.add_argument("--lesion-dir", type=str, default=None)
    parser.add_argument("--output", type=str, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    basin_dir, lesion_dir, output = _infer_dirs(args)
    summary = build_summary(
        basin_dir=basin_dir,
        lesion_dir=lesion_dir,
        provider=args.provider,
        run_id=args.program_root,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    print(
        "basin-width analysis: "
        f"{summary['joined_theorems']} joined theorems, "
        f"{summary['path_block_rows']} path-block rows"
    )


if __name__ == "__main__":
    main()
