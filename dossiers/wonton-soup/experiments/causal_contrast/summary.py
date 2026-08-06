from __future__ import annotations

import gzip
import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODES = ("centralized", "distributed")
SUMMARY_NAME = "paired_contrast_summary.json"


def _read_json(path: Path) -> Any:
    if path.name.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def _load_summary(run_dir: Path) -> dict[str, Any] | None:
    for candidate in (run_dir / "summary.json.gz", run_dir / "summary.json"):
        if candidate.exists():
            payload = _read_json(candidate)
            return payload if isinstance(payload, dict) else None
    return None


def _load_comparisons(run_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    comparisons: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(run_dir.glob("*/*_comparison.json")):
        payload = _read_json(path)
        if isinstance(payload, dict):
            comparisons[(path.parent.name, path.name.removesuffix("_comparison.json"))] = payload
    return comparisons


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _ged_value(item: dict[str, Any]) -> float | None:
    for key in ("ged_search_graph", "ged_search_graph_soft", "ged_proof_graph", "ged_trace_graph"):
        raw = item.get(key)
        if not isinstance(raw, dict):
            continue
        value = raw.get("normalized")
        if not isinstance(value, (int, float)):
            value = raw.get("value")
        if isinstance(value, (int, float)):
            return float(value)
    raw = item.get("ged")
    return float(raw) if isinstance(raw, (int, float)) else None


def _graph_variants(theorem_dir: Path) -> dict[str, str]:
    variants: dict[str, str] = {}
    if not theorem_dir.exists():
        return variants
    for path in sorted(theorem_dir.glob("*_graph.json")):
        if path.name == "wild_type_graph.json":
            variants["wild_type"] = path.name
        else:
            variants[path.name.removesuffix("_graph.json")] = path.name
    return variants


def _intervention_name(item: dict[str, Any]) -> str:
    for key in ("name", "intervention", "variant"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return "intervention"


def _comparison_for(
    comparisons: dict[tuple[str, str], dict[str, Any]],
    theorem_name: Any,
    intervention: dict[str, Any],
) -> dict[str, Any] | None:
    name = _intervention_name(intervention)
    if isinstance(theorem_name, str):
        return comparisons.get((theorem_name, name))
    return None


def _hash_mismatch(
    comparisons: dict[tuple[str, str], dict[str, Any]],
    theorem_name: Any,
    intervention: dict[str, Any],
) -> bool:
    comparison = _comparison_for(comparisons, theorem_name, intervention)
    if comparison is not None:
        return bool(comparison.get("hash_mismatch"))
    return bool(intervention.get("hash_mismatch"))


def _run_metrics(
    summary: dict[str, Any] | None,
    comparisons: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    if summary is None:
        return {
            "summary_available": False,
            "theorem_count": 0,
            "wild_solved": 0,
            "wild_solve_rate": None,
            "baseline_solved_interventions": 0,
            "recovered_interventions": 0,
            "recovery_rate": None,
            "rerouted_interventions": 0,
            "reroute_rate_among_recovered": None,
            "rescues": 0,
            "collapses": 0,
            "mean_ged": None,
        }
    theorems = [item for item in summary.get("theorems", []) if isinstance(item, dict)]
    theorem_count = len(theorems)
    wild_solved = 0
    baseline_solved = 0
    recovered = 0
    rerouted = 0
    rescues = 0
    collapses = 0
    ged_values: list[float] = []
    for theorem in theorems:
        theorem_name = theorem.get("name")
        wild = theorem.get("wild_type")
        if isinstance(wild, dict) and bool(wild.get("solved")):
            wild_solved += 1
        for intervention in theorem.get("interventions", []) or []:
            if not isinstance(intervention, dict):
                continue
            solved = bool(intervention.get("solved"))
            base = bool(intervention.get("baseline_solved"))
            if base:
                baseline_solved += 1
                if solved:
                    recovered += 1
                else:
                    collapses += 1
            elif solved:
                rescues += 1
            if solved and _hash_mismatch(comparisons, theorem_name, intervention):
                rerouted += 1
            comparison = _comparison_for(comparisons, theorem_name, intervention)
            ged = _ged_value(comparison if comparison is not None else intervention)
            if ged is not None:
                ged_values.append(ged)
    return {
        "summary_available": True,
        "theorem_count": theorem_count,
        "wild_solved": wild_solved,
        "wild_solve_rate": _safe_rate(wild_solved, theorem_count),
        "baseline_solved_interventions": baseline_solved,
        "recovered_interventions": recovered,
        "recovery_rate": _safe_rate(recovered, baseline_solved),
        "rerouted_interventions": rerouted,
        "reroute_rate_among_recovered": _safe_rate(rerouted, recovered),
        "rescues": rescues,
        "collapses": collapses,
        "mean_ged": sum(ged_values) / len(ged_values) if ged_values else None,
    }


def _theorem_entry(summary: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    if summary is None:
        return None
    for item in summary.get("theorems", []) or []:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def _theorem_names(summaries: Iterable[dict[str, Any] | None]) -> list[str]:
    names: set[str] = set()
    for summary in summaries:
        if summary is None:
            continue
        for item in summary.get("theorems", []) or []:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.add(item["name"])
    return sorted(names)


def _theorem_mode_payload(
    run_dir: Path,
    summary: dict[str, Any] | None,
    comparisons: dict[tuple[str, str], dict[str, Any]],
    theorem_name: str,
) -> dict[str, Any]:
    entry = _theorem_entry(summary, theorem_name)
    variants = _graph_variants(run_dir / theorem_name)
    if entry is None:
        return {
            "present": False,
            "wild_solved": None,
            "wild_iterations": None,
            "intervention_count": 0,
            "baseline_solved_interventions": 0,
            "recovered_interventions": 0,
            "recovery_rate": None,
            "rerouted_interventions": 0,
            "mean_ged": None,
            "variants": variants,
        }
    wild = entry.get("wild_type") if isinstance(entry.get("wild_type"), dict) else {}
    interventions = [
        item for item in entry.get("interventions", []) or [] if isinstance(item, dict)
    ]
    baseline = [item for item in interventions if bool(item.get("baseline_solved"))]
    recovered = [item for item in baseline if bool(item.get("solved"))]
    rerouted = [item for item in recovered if _hash_mismatch(comparisons, theorem_name, item)]
    ged_values = [
        value
        for value in (
            _ged_value(comparison if comparison is not None else item)
            for item in interventions
            for comparison in [_comparison_for(comparisons, theorem_name, item)]
        )
        if value is not None
    ]
    return {
        "present": True,
        "wild_solved": bool(wild.get("solved")),
        "wild_iterations": wild.get("iterations"),
        "intervention_count": len(interventions),
        "baseline_solved_interventions": len(baseline),
        "recovered_interventions": len(recovered),
        "recovery_rate": _safe_rate(len(recovered), len(baseline)),
        "rerouted_interventions": len(rerouted),
        "mean_ged": sum(ged_values) / len(ged_values) if ged_values else None,
        "variants": variants,
        "interventions": [
            {
                "name": _intervention_name(item),
                "solved": bool(item.get("solved")),
                "baseline_solved": bool(item.get("baseline_solved")),
                "hash_mismatch": _hash_mismatch(comparisons, theorem_name, item),
                "ged": _ged_value(
                    _comparison_for(comparisons, theorem_name, item)
                    if _comparison_for(comparisons, theorem_name, item) is not None
                    else item
                ),
            }
            for item in interventions
        ],
    }


def _delta(distributed: float | None, centralized: float | None) -> float | None:
    if distributed is None or centralized is None:
        return None
    return distributed - centralized


def build_paired_contrast_summary(
    *,
    root_dir: Path,
    logs_dir: Path,
    run_id: str,
    providers: list[str],
    run_dirs: dict[str, dict[str, Path]],
    experiment: dict[str, Any],
) -> dict[str, Any]:
    summaries: dict[str, dict[str, dict[str, Any] | None]] = {}
    comparisons: dict[str, dict[str, dict[tuple[str, str], dict[str, Any]]]] = {}
    modes_payload: dict[str, dict[str, dict[str, Any]]] = {}
    for provider in providers:
        summaries[provider] = {}
        comparisons[provider] = {}
        modes_payload[provider] = {}
        for mode in MODES:
            run_dir = run_dirs[provider][mode]
            summary = _load_summary(run_dir)
            mode_comparisons = _load_comparisons(run_dir)
            summaries[provider][mode] = summary
            comparisons[provider][mode] = mode_comparisons
            modes_payload[provider][mode] = {
                "rel_run_dir": run_dir.relative_to(logs_dir).as_posix(),
                "run_dir": str(run_dir),
                "metrics": _run_metrics(summary, mode_comparisons),
            }

    provider_rows: list[dict[str, Any]] = []
    theorem_pairs: list[dict[str, Any]] = []
    for provider in providers:
        central_metrics = modes_payload[provider]["centralized"]["metrics"]
        dist_metrics = modes_payload[provider]["distributed"]["metrics"]
        provider_rows.append(
            {
                "provider": provider,
                "centralized": central_metrics,
                "distributed": dist_metrics,
                "delta": {
                    "wild_solve_rate": _delta(
                        dist_metrics["wild_solve_rate"],
                        central_metrics["wild_solve_rate"],
                    ),
                    "recovery_rate": _delta(
                        dist_metrics["recovery_rate"],
                        central_metrics["recovery_rate"],
                    ),
                    "reroute_rate_among_recovered": _delta(
                        dist_metrics["reroute_rate_among_recovered"],
                        central_metrics["reroute_rate_among_recovered"],
                    ),
                    "mean_ged": _delta(dist_metrics["mean_ged"], central_metrics["mean_ged"]),
                },
            }
        )
        names = _theorem_names(summaries[provider].values())
        for theorem_name in names:
            central = _theorem_mode_payload(
                run_dirs[provider]["centralized"],
                summaries[provider]["centralized"],
                comparisons[provider]["centralized"],
                theorem_name,
            )
            distributed = _theorem_mode_payload(
                run_dirs[provider]["distributed"],
                summaries[provider]["distributed"],
                comparisons[provider]["distributed"],
                theorem_name,
            )
            common_variants = sorted(set(central["variants"]) & set(distributed["variants"]))
            theorem_pairs.append(
                {
                    "provider": provider,
                    "theorem": theorem_name,
                    "centralized": central,
                    "distributed": distributed,
                    "common_variants": common_variants,
                    "delta": {
                        "wild_solved": (
                            int(bool(distributed["wild_solved"]))
                            - int(bool(central["wild_solved"]))
                            if distributed["wild_solved"] is not None
                            and central["wild_solved"] is not None
                            else None
                        ),
                        "recovery_rate": _delta(
                            distributed["recovery_rate"], central["recovery_rate"]
                        ),
                        "mean_ged": _delta(distributed["mean_ged"], central["mean_ged"]),
                    },
                }
            )

    payload = {
        "format_version": 1,
        "kind": "paired_centralized_distributed_contrast",
        "run_id": run_id,
        "root_dir": str(root_dir),
        "rel_root_dir": root_dir.relative_to(logs_dir).as_posix(),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "experiment": experiment,
        "modes": modes_payload,
        "providers": provider_rows,
        "theorem_pairs": theorem_pairs,
    }
    root_dir.mkdir(parents=True, exist_ok=True)
    (root_dir / SUMMARY_NAME).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
