from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from analysis.cross_assistant_alignment import (
    LexicalAblationConfig,
    NameObfuscationConfig,
    _normalize_lexical_ablation_mode,
    aggregate_theorem_distance,
    group_signatures_by_theorem,
    load_signature_pool,
    normalize_proof_aggregation,
    rank_theorem_candidates,
)

DEFAULT_KS = (1, 3, 5, 10)
VALID_GATE_CLAIMS = frozenset({"all", "global", "cross_kind", "same_kind"})
VALID_GATE_AXES = frozenset({"all", "coverage", "quality"})


def _require_object(value: Any, *, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(message)
    return dict(value)


def _require_non_empty_str(value: Any, *, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(message)
    return value.strip()


def _optional_non_empty_str(value: Any, *, message: str) -> str | None:
    if value is None:
        return None
    return _require_non_empty_str(value, message=message)


def _as_optional_rate(value: Any, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, int):
        value = float(value)
    if not isinstance(value, float):
        raise ValueError(f"{field} must be numeric")
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{field} must be within [0, 1]")
    return value


def _as_optional_positive_int(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < 0:
        raise ValueError(f"{field} must be >= 0")
    return value


@dataclass(frozen=True)
class PairSpec:
    pair_id: str
    lean_theorem: str
    coq_theorem: str
    lean_display_name: str | None = None
    lean_statement: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class BucketGateThresholds:
    min_pairs: int | None = None
    min_eval_rate: float | None = None
    min_recall_at_1: float | None = None
    min_recall_at_10: float | None = None
    min_mrr: float | None = None


@dataclass(frozen=True)
class CoverageThresholds:
    min_pairs_evaluated: int | None = None
    min_eval_rate: float | None = None


@dataclass(frozen=True)
class QualityThresholds:
    min_recall_at_1: float | None = None
    min_recall_at_10: float | None = None
    min_mrr: float | None = None


@dataclass(frozen=True)
class GateThresholds:
    coverage: CoverageThresholds = field(default_factory=CoverageThresholds)
    quality: QualityThresholds = field(default_factory=QualityThresholds)
    by_kind: dict[str, BucketGateThresholds] = field(default_factory=dict)
    bucket_groups: dict[str, dict[str, BucketGateThresholds]] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkManifest:
    schema_version: int
    benchmark_id: str
    description: str | None
    path: Path
    pairs: tuple[PairSpec, ...]
    gate: GateThresholds

    def meta(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "benchmark_id": self.benchmark_id,
            "description": self.description,
            "pairs_path": str(self.path.resolve()),
        }


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failures: list[str]
    coverage_failures: list[str]
    quality_failures: list[str]


def _normalize_k_values(raw: list[int] | tuple[int, ...] | None) -> list[int]:
    if raw is None:
        raw_values = list(DEFAULT_KS)
    else:
        raw_values = [int(value) for value in raw]
    ks = sorted({value for value in raw_values if value > 0})
    if not ks:
        raise ValueError("k values must contain at least one positive integer")
    return ks


def _normalize_gate_claim(gate_claim: str) -> str:
    norm = gate_claim.strip().lower()
    if norm not in VALID_GATE_CLAIMS:
        raise ValueError(
            f"gate_claim must be one of {sorted(VALID_GATE_CLAIMS)}; got {gate_claim}"
        )
    return norm


def _normalize_gate_axis(gate_axis: str) -> str:
    norm = gate_axis.strip().lower()
    if norm not in VALID_GATE_AXES:
        raise ValueError(
            f"gate_axis must be one of {sorted(VALID_GATE_AXES)}; got {gate_axis}"
        )
    return norm


def _parse_bucket_gate(
    bucket_name: str,
    payload: Any,
    *,
    field: str,
) -> BucketGateThresholds:
    data = _require_object(payload, message=f"{field}.{bucket_name} must be an object")
    return BucketGateThresholds(
        min_pairs=_as_optional_positive_int(
            data.get("min_pairs"),
            field=f"{field}.{bucket_name}.min_pairs",
        ),
        min_eval_rate=_as_optional_rate(
            data.get("min_eval_rate"),
            field=f"{field}.{bucket_name}.min_eval_rate",
        ),
        min_recall_at_1=_as_optional_rate(
            data.get("min_recall_at_1"),
            field=f"{field}.{bucket_name}.min_recall_at_1",
        ),
        min_recall_at_10=_as_optional_rate(
            data.get("min_recall_at_10"),
            field=f"{field}.{bucket_name}.min_recall_at_10",
        ),
        min_mrr=_as_optional_rate(
            data.get("min_mrr"),
            field=f"{field}.{bucket_name}.min_mrr",
        ),
    )


def _parse_bucket_group(payload: Any, *, field: str) -> dict[str, BucketGateThresholds]:
    if payload is None:
        return {}
    data = _require_object(payload, message=f"{field} must be an object")
    out: dict[str, BucketGateThresholds] = {}
    for bucket_name, bucket_payload in data.items():
        name = _require_non_empty_str(
            bucket_name,
            message=f"{field} keys must be non-empty strings",
        )
        out[name] = _parse_bucket_gate(name, bucket_payload, field=field)
    return out


def load_benchmark_manifest(path: Path) -> BenchmarkManifest:
    if not path.exists():
        raise FileNotFoundError(f"benchmark manifest not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    data = _require_object(payload, message="benchmark manifest must be a JSON object")
    schema_version = _as_optional_positive_int(data.get("schema_version"), field="schema_version")
    if schema_version is None:
        raise ValueError("benchmark manifest missing schema_version")
    benchmark_id = _require_non_empty_str(
        data.get("benchmark_id"),
        message="benchmark manifest missing benchmark_id",
    )

    raw_pairs = data.get("pairs")
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise ValueError("benchmark manifest must contain a non-empty pairs list")

    pairs: list[PairSpec] = []
    seen_ids: set[str] = set()
    for idx, raw_pair in enumerate(raw_pairs):
        pair = _require_object(raw_pair, message=f"pairs[{idx}] must be an object")
        pair_id = _require_non_empty_str(
            pair.get("pair_id"),
            message=f"pairs[{idx}] missing pair_id",
        )
        if pair_id in seen_ids:
            raise ValueError(f"duplicate pair_id: {pair_id}")
        seen_ids.add(pair_id)
        pairs.append(
            PairSpec(
                pair_id=pair_id,
                lean_theorem=_require_non_empty_str(
                    pair.get("lean_item_id"),
                    message=f"pairs[{idx}] missing lean_item_id",
                ),
                coq_theorem=_require_non_empty_str(
                    pair.get("coq_theorem"),
                    message=f"pairs[{idx}] missing coq_theorem",
                ),
                lean_display_name=_optional_non_empty_str(
                    pair.get("lean_display_name"),
                    message=f"pairs[{idx}].lean_display_name must be a non-empty string",
                ),
                lean_statement=_optional_non_empty_str(
                    pair.get("lean_statement"),
                    message=f"pairs[{idx}].lean_statement must be a non-empty string",
                ),
                notes=_optional_non_empty_str(
                    pair.get("notes"),
                    message=f"pairs[{idx}].notes must be a non-empty string",
                ),
            )
        )

    gate_raw = _require_object(data.get("gate", {}), message="gate must be an object")
    by_kind = _parse_bucket_group(gate_raw.get("by_kind"), field="gate.by_kind")
    bucket_gates = _parse_bucket_group(gate_raw.get("bucket_gates"), field="gate.bucket_gates")
    bucket_groups: dict[str, dict[str, BucketGateThresholds]] = {}
    if by_kind:
        bucket_groups["by_kind"] = by_kind
    by_cohort = _parse_bucket_group(gate_raw.get("by_cohort"), field="gate.by_cohort")
    if by_cohort:
        bucket_groups["by_cohort"] = by_cohort
    if bucket_gates:
        bucket_groups["bucket_gates"] = bucket_gates

    gate = GateThresholds(
        coverage=CoverageThresholds(
            min_pairs_evaluated=_as_optional_positive_int(
                gate_raw.get("min_pairs_evaluated"),
                field="gate.min_pairs_evaluated",
            ),
            min_eval_rate=_as_optional_rate(
                gate_raw.get("min_eval_rate"),
                field="gate.min_eval_rate",
            ),
        ),
        quality=QualityThresholds(
            min_recall_at_1=_as_optional_rate(
                gate_raw.get("min_recall_at_1"),
                field="gate.min_recall_at_1",
            ),
            min_recall_at_10=_as_optional_rate(
                gate_raw.get("min_recall_at_10"),
                field="gate.min_recall_at_10",
            ),
            min_mrr=_as_optional_rate(
                gate_raw.get("min_mrr"),
                field="gate.min_mrr",
            ),
        ),
        by_kind=by_kind or bucket_gates,
        bucket_groups=bucket_groups,
    )
    return BenchmarkManifest(
        schema_version=schema_version,
        benchmark_id=benchmark_id,
        description=_optional_non_empty_str(
            data.get("description"),
            message="description must be a non-empty string",
        ),
        path=path.resolve(),
        pairs=tuple(pairs),
        gate=gate,
    )


def load_pair_specs(path: Path) -> tuple[list[PairSpec], dict[str, Any], GateThresholds]:
    manifest = load_benchmark_manifest(path)
    return list(manifest.pairs), manifest.meta(), manifest.gate


def _summary_from_ranks(
    ranks: list[int],
    *,
    total_pairs: int,
    k_values: list[int],
) -> dict[str, Any]:
    evaluated = len(ranks)
    missing = total_pairs - evaluated
    eval_rate = (evaluated / total_pairs) if total_pairs > 0 else None
    recalls = {
        f"recall_at_{k}": (sum(1 for rank in ranks if rank <= k) / evaluated if evaluated else None)
        for k in k_values
    }
    mean_rank = (sum(ranks) / evaluated) if evaluated else None
    median_rank = statistics.median(ranks) if evaluated else None
    mrr = (sum(1.0 / rank for rank in ranks) / evaluated) if evaluated else None
    return {
        "pairs_total": total_pairs,
        "pairs_evaluated": evaluated,
        "pairs_missing": missing,
        "eval_rate": round(eval_rate, 6) if eval_rate is not None else None,
        "mrr": round(mrr, 6) if mrr is not None else None,
        "mean_rank": round(mean_rank, 6) if mean_rank is not None else None,
        "median_rank": round(float(median_rank), 6) if median_rank is not None else None,
        **{key: round(value, 6) if value is not None else None for key, value in recalls.items()},
    }


def evaluate_paired_benchmark(
    run_lean_dir: Path,
    run_coq_dir: Path,
    pairs_path: Path,
    *,
    solved_only: bool = False,
    ks: list[int] | tuple[int, ...] | None = None,
    name_obfuscation_mode: str = "none",
    name_obfuscation_salt: str = "cross-assistant-obfuscation-v1",
    lexical_ablation_mode: str = "none",
    graph_source_lean: str = "wild_type_graph",
    graph_source_coq: str = "wild_type_graph",
    gate_claim: str = "all",
    gate_axis: str = "all",
    proof_aggregation: str = "single",
    max_proofs_per_theorem: int | None = None,
) -> dict[str, Any]:
    k_values = _normalize_k_values(ks)
    pair_specs, meta, gate_thresholds = load_pair_specs(pairs_path)
    normalized_gate_claim = _normalize_gate_claim(gate_claim)
    normalized_gate_axis = _normalize_gate_axis(gate_axis)
    normalized_proof_aggregation = normalize_proof_aggregation(proof_aggregation)
    obfuscation = NameObfuscationConfig(
        mode=name_obfuscation_mode,
        salt=name_obfuscation_salt,
    )
    lexical_ablation = LexicalAblationConfig(
        mode=_normalize_lexical_ablation_mode(lexical_ablation_mode)
    )
    include_interventions = normalized_proof_aggregation != "single"

    lean_sigs = load_signature_pool(
        run_lean_dir,
        solved_only=solved_only,
        name_obfuscation=obfuscation,
        lexical_ablation=lexical_ablation,
        graph_source=graph_source_lean,
        include_interventions=include_interventions,
        max_proofs_per_theorem=max_proofs_per_theorem,
    )
    coq_sigs = load_signature_pool(
        run_coq_dir,
        solved_only=solved_only,
        name_obfuscation=obfuscation,
        lexical_ablation=lexical_ablation,
        graph_source=graph_source_coq,
        include_interventions=include_interventions,
        max_proofs_per_theorem=max_proofs_per_theorem,
    )
    if not lean_sigs:
        raise ValueError(f"No theorem signatures found in Lean run: {run_lean_dir}")
    if not coq_sigs:
        raise ValueError(f"No theorem signatures found in Coq run: {run_coq_dir}")

    lean_by_theorem = group_signatures_by_theorem(lean_sigs)
    coq_by_theorem = group_signatures_by_theorem(coq_sigs)

    pair_rows: list[dict[str, Any]] = []
    ranks: list[int] = []
    ranks_by_kind: dict[str, list[int]] = {
        "same_kind": [],
        "cross_kind": [],
    }
    totals_by_kind: dict[str, int] = {
        "same_kind": 0,
        "cross_kind": 0,
    }
    max_k = max(k_values)

    for pair in pair_specs:
        lean_proofs = lean_by_theorem.get(pair.lean_theorem)
        coq_proofs = coq_by_theorem.get(pair.coq_theorem)
        if lean_proofs is None or coq_proofs is None:
            pair_rows.append(
                {
                    "pair_id": pair.pair_id,
                    "lean_theorem": pair.lean_theorem,
                    "coq_theorem": pair.coq_theorem,
                    "status": "missing_theorem",
                    "lean_present": lean_proofs is not None,
                    "coq_present": coq_proofs is not None,
                }
            )
            continue

        ranked = rank_theorem_candidates(
            pair.lean_theorem,
            lean_by_theorem,
            coq_by_theorem,
            proof_aggregation=normalized_proof_aggregation,
        )
        rank = None
        for idx, candidate in enumerate(ranked, start=1):
            if candidate.theorem_b == pair.coq_theorem:
                rank = idx
                break
        if rank is None:
            pair_rows.append(
                {
                    "pair_id": pair.pair_id,
                    "lean_theorem": pair.lean_theorem,
                    "coq_theorem": pair.coq_theorem,
                    "status": "not_ranked",
                }
            )
            continue

        resolved = aggregate_theorem_distance(
            lean_proofs,
            coq_proofs,
            proof_aggregation=normalized_proof_aggregation,
        )
        rep = resolved.representative_pair
        pair_kind = "cross_kind" if rep.cross_kind else "same_kind"
        totals_by_kind[pair_kind] += 1
        ranks.append(rank)
        ranks_by_kind[pair_kind].append(rank)

        pair_rows.append(
            {
                "pair_id": pair.pair_id,
                "lean_theorem": pair.lean_theorem,
                "coq_theorem": pair.coq_theorem,
                "proof_aggregation": normalized_proof_aggregation,
                "lean_graph_kind": rep.graph_kind_a,
                "coq_graph_kind": rep.graph_kind_b,
                "pair_kind": pair_kind,
                "status": "ok",
                "rank": rank,
                "reciprocal_rank": round(1.0 / rank, 6),
                "distance": round(resolved.distance, 6),
                "proof_support": {
                    "lean": resolved.proof_count_a,
                    "coq": resolved.proof_count_b,
                },
                "representative_pair": {
                    "proof_id_lean": rep.proof_id_a,
                    "proof_id_coq": rep.proof_id_b,
                    "variant_lean": rep.variant_a,
                    "variant_coq": rep.variant_b,
                },
                "nearest_neighbor_stats": resolved.nearest_neighbor_stats,
                "top_candidates": [
                    {
                        "coq_theorem": candidate.theorem_b,
                        "coq_graph_kind": candidate.representative_pair.graph_kind_b,
                        "cross_kind": candidate.representative_pair.cross_kind,
                        "distance": round(candidate.distance, 6),
                        "graph_distance": round(
                            candidate.representative_pair.graph_distance, 6
                        ),
                        "lexical_distance": round(
                            candidate.representative_pair.lexical_distance, 6
                        ),
                        "connective_distance": round(
                            candidate.representative_pair.connective_distance, 6
                        ),
                        "proof_support": {
                            "lean": candidate.proof_count_a,
                            "coq": candidate.proof_count_b,
                        },
                        "representative_pair": {
                            "proof_id_lean": candidate.representative_pair.proof_id_a,
                            "proof_id_coq": candidate.representative_pair.proof_id_b,
                            "variant_lean": candidate.representative_pair.variant_a,
                            "variant_coq": candidate.representative_pair.variant_b,
                        },
                        "nearest_neighbor_stats": candidate.nearest_neighbor_stats,
                    }
                    for candidate in ranked[:max_k]
                ],
            }
        )

    global_summary = _summary_from_ranks(ranks, total_pairs=len(pair_specs), k_values=k_values)
    summary_by_kind: dict[str, dict[str, Any]] = {
        kind: _summary_from_ranks(
            bucket_ranks,
            total_pairs=totals_by_kind[kind],
            k_values=k_values,
        )
        for kind, bucket_ranks in sorted(ranks_by_kind.items())
    }
    summary = dict(global_summary)
    summary["by_kind"] = summary_by_kind
    summary["cohorts"] = {
        "global": dict(global_summary),
        **{kind: dict(bucket) for kind, bucket in summary_by_kind.items()},
    }
    summary["denominator_policy"] = {
        "global": "all benchmark pairs",
        "same_kind": (
            "pair rows where both theorems are present and the representative aggregated pair is "
            "same_kind"
        ),
        "cross_kind": (
            "pair rows where both theorems are present and the representative aggregated pair is "
            "cross_kind"
        ),
    }

    gate = evaluate_gate(
        summary,
        gate_thresholds,
        gate_claim=normalized_gate_claim,
        gate_axis=normalized_gate_axis,
    )

    return {
        "schema_version": 4,
        "benchmark": meta,
        "run_lean": str(run_lean_dir.resolve()),
        "run_coq": str(run_coq_dir.resolve()),
        "solved_only": solved_only,
        "proof_aggregation": normalized_proof_aggregation,
        "max_proofs_per_theorem": max_proofs_per_theorem,
        "graph_sources": {
            "run_lean": graph_source_lean,
            "run_coq": graph_source_coq,
        },
        "name_obfuscation": {
            "mode": obfuscation.mode,
            "salt": obfuscation.salt,
        },
        "lexical_ablation": {
            "mode": lexical_ablation.mode,
        },
        "k_values": k_values,
        "summary": summary,
        "gate": {
            "claim": normalized_gate_claim,
            "axis": normalized_gate_axis,
            "thresholds": {
                "coverage": {
                    "min_pairs_evaluated": gate_thresholds.coverage.min_pairs_evaluated,
                    "min_eval_rate": gate_thresholds.coverage.min_eval_rate,
                },
                "quality": {
                    "min_recall_at_1": gate_thresholds.quality.min_recall_at_1,
                    "min_recall_at_10": gate_thresholds.quality.min_recall_at_10,
                    "min_mrr": gate_thresholds.quality.min_mrr,
                },
                "by_kind": {
                    kind: {
                        "min_pairs": bucket.min_pairs,
                        "min_eval_rate": bucket.min_eval_rate,
                        "min_recall_at_1": bucket.min_recall_at_1,
                        "min_recall_at_10": bucket.min_recall_at_10,
                        "min_mrr": bucket.min_mrr,
                    }
                    for kind, bucket in sorted(gate_thresholds.by_kind.items())
                },
            },
            "passed": gate.passed,
            "failures": gate.failures,
            "coverage_failures": gate.coverage_failures,
            "quality_failures": gate.quality_failures,
        },
        "pairs": pair_rows,
    }


def evaluate_gate(
    summary: dict[str, Any],
    thresholds: GateThresholds,
    *,
    gate_claim: str = "all",
    gate_axis: str = "all",
) -> GateResult:
    failures: list[str] = []
    coverage_failures: list[str] = []
    quality_failures: list[str] = []
    normalized_gate_claim = _normalize_gate_claim(gate_claim)
    normalized_gate_axis = _normalize_gate_axis(gate_axis)

    cohorts = summary.get("cohorts")
    by_kind = summary.get("by_kind")
    if not isinstance(cohorts, dict):
        cohorts = {}
    if not isinstance(by_kind, dict):
        by_kind = {}
    if "global" not in cohorts:
        cohorts["global"] = summary
    for kind in ("cross_kind", "same_kind"):
        if kind not in cohorts and isinstance(by_kind.get(kind), dict):
            cohorts[kind] = by_kind[kind]

    scopes: set[str]
    if normalized_gate_claim == "all":
        scopes = {"global", "cross_kind", "same_kind"}
    elif normalized_gate_claim == "global":
        scopes = {"global"}
    else:
        scopes = {normalized_gate_claim}

    def check_rate(
        cohort_summary: dict[str, Any],
        *,
        metric: str,
        threshold: float | None,
        scope: str,
        out_failures: list[str],
    ) -> None:
        if threshold is None:
            return
        value = cohort_summary.get(metric)
        if not isinstance(value, (int, float)):
            out_failures.append(f"{scope}.{metric} missing")
            return
        if float(value) < threshold:
            out_failures.append(f"{scope}.{metric}={value:.6f} < {threshold:.6f}")

    def check_int(
        cohort_summary: dict[str, Any],
        *,
        metric: str,
        threshold: int | None,
        scope: str,
        out_failures: list[str],
    ) -> None:
        if threshold is None:
            return
        value = cohort_summary.get(metric)
        if not isinstance(value, int):
            out_failures.append(f"{scope}.{metric} missing")
            return
        if value < threshold:
            out_failures.append(f"{scope}.{metric}={value} < {threshold}")

    coverage_enabled = normalized_gate_axis in {"all", "coverage"}
    quality_enabled = normalized_gate_axis in {"all", "quality"}

    if "global" in scopes:
        global_summary = cohorts.get("global")
        if not isinstance(global_summary, dict):
            global_summary = {}
        if coverage_enabled:
            check_int(
                global_summary,
                metric="pairs_evaluated",
                threshold=thresholds.coverage.min_pairs_evaluated,
                scope="cohorts.global",
                out_failures=coverage_failures,
            )
            check_rate(
                global_summary,
                metric="eval_rate",
                threshold=thresholds.coverage.min_eval_rate,
                scope="cohorts.global",
                out_failures=coverage_failures,
            )
        if quality_enabled:
            check_rate(
                global_summary,
                metric="recall_at_1",
                threshold=thresholds.quality.min_recall_at_1,
                scope="cohorts.global",
                out_failures=quality_failures,
            )
            check_rate(
                global_summary,
                metric="recall_at_10",
                threshold=thresholds.quality.min_recall_at_10,
                scope="cohorts.global",
                out_failures=quality_failures,
            )
            check_rate(
                global_summary,
                metric="mrr",
                threshold=thresholds.quality.min_mrr,
                scope="cohorts.global",
                out_failures=quality_failures,
            )

    for kind, gate in sorted(thresholds.by_kind.items()):
        if kind not in scopes:
            continue
        bucket_summary = cohorts.get(kind)
        scope = f"cohorts.{kind}"
        if not isinstance(bucket_summary, dict):
            missing_checks = (
                gate.min_pairs is not None
                or gate.min_eval_rate is not None
                or gate.min_recall_at_1 is not None
                or gate.min_recall_at_10 is not None
                or gate.min_mrr is not None
            )
            if missing_checks:
                failures.append(f"{scope} missing")
            continue

        if coverage_enabled:
            check_int(
                bucket_summary,
                metric="pairs_evaluated",
                threshold=gate.min_pairs,
                scope=scope,
                out_failures=coverage_failures,
            )
            check_rate(
                bucket_summary,
                metric="eval_rate",
                threshold=gate.min_eval_rate,
                scope=scope,
                out_failures=coverage_failures,
            )

        if quality_enabled:
            check_rate(
                bucket_summary,
                metric="recall_at_1",
                threshold=gate.min_recall_at_1,
                scope=scope,
                out_failures=quality_failures,
            )
            check_rate(
                bucket_summary,
                metric="recall_at_10",
                threshold=gate.min_recall_at_10,
                scope=scope,
                out_failures=quality_failures,
            )
            check_rate(
                bucket_summary,
                metric="mrr",
                threshold=gate.min_mrr,
                scope=scope,
                out_failures=quality_failures,
            )

    failures.extend(coverage_failures)
    failures.extend(quality_failures)
    return GateResult(
        passed=not failures,
        failures=failures,
        coverage_failures=coverage_failures,
        quality_failures=quality_failures,
    )
