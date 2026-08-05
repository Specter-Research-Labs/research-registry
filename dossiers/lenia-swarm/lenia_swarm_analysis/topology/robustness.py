from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis._io import read_json, read_jsonl

from .analysis import _diagram_summary, _resolve_rows_path
from .compare import _representation_matrix
from .core import (
    distance_scale,
    pairwise_distance_matrix,
    peak_betti,
    persistence_threshold_counts,
    preflight_rips_request,
    run_ripser_precomputed,
    sample_plan_hash,
    stable_sample_indices,
    upper_triangle,
)


def _default_output_dir(manifest_path: Path) -> Path:
    stem = manifest_path.name.removesuffix(".manifest.json")
    return manifest_path.parent.parent / "topology-robustness" / stem


def _parse_sizes(raw: str) -> list[int]:
    sizes = [int(item.strip()) for item in raw.split(",") if item.strip()]
    if not sizes:
        raise SystemExit("At least one sample size is required")
    return sizes


def _persistence_threshold_counts(diagrams: list[list[dict[str, Any]]]) -> dict[str, int]:
    return persistence_threshold_counts(
        diagrams,
        ratios=(0.005, 0.01, 0.015, 0.02),
    )


def _peak_betti_one(betti_curves: list[dict[str, Any]]) -> dict[str, Any] | None:
    return peak_betti(betti_curves)


def _metrics_for_matrix(matrix: np.ndarray, *, maxdim: int) -> dict[str, Any]:
    ripser_budget = preflight_rips_request(int(matrix.shape[0]), maxdim=maxdim)
    distances = pairwise_distance_matrix(matrix)
    pairwise = upper_triangle(distances)
    metric_scale, scale_kind = distance_scale(pairwise)
    result, _ = run_ripser_precomputed(distances, maxdim=maxdim)
    diagram_summary = _diagram_summary(
        result["dgms"],
        pairwise_max=metric_scale,
        scale_kind=scale_kind,
    )
    h1 = diagram_summary["summaries"][1] if len(diagram_summary["summaries"]) > 1 else None
    return {
        "pointCount": int(matrix.shape[0]),
        "dimension": int(matrix.shape[1]),
        "budget": ripser_budget,
        "ripser": diagram_summary["summaries"],
        "scaleReference": diagram_summary["scaleReference"],
        "h1ThresholdCounts": _persistence_threshold_counts(diagram_summary["diagrams"]),
        "persistenceThresholdUnits": "fraction_of_declared_scale",
        "peakBetti1": _peak_betti_one(diagram_summary["bettiCurves"]),
        "topH1Persistence": h1["topPersistence"][0] if h1 and h1["topPersistence"] else None,
    }


def _bounded_metrics_for_matrix(matrix: np.ndarray, *, maxdim: int) -> dict[str, Any]:
    try:
        preflight_rips_request(int(matrix.shape[0]), maxdim=maxdim)
    except ValueError as exc:
        return {
            "status": "skipped",
            "pointCount": int(matrix.shape[0]),
            "reason": str(exc),
        }
    return _metrics_for_matrix(matrix, maxdim=maxdim)


def run_robustness(
    manifest_path: Path,
    output_dir: Path,
    *,
    representations: tuple[str, ...],
    sample_sizes: list[int],
    replicates: int,
    slice_key: str,
    min_slice_size: int,
    seed: int,
    maxdim: int,
) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    rows_path = _resolve_rows_path(manifest_path, manifest)
    rows = read_jsonl(rows_path)
    if len(rows) < 2:
        raise SystemExit("Topology robustness requires at least 2 rows")

    slices: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        key = row.get(slice_key)
        if isinstance(key, str) and key:
            slices[key].append(index)

    sample_keys = [str(row.get("specimenId") or index) for index, row in enumerate(rows)]
    sample_plans = {
        (size, replicate_index): stable_sample_indices(
            sample_keys,
            sample_size=size,
            seed=seed,
            replicate=replicate_index,
        )
        for size in sample_sizes
        if size <= len(rows)
        for replicate_index in range(replicates)
    }
    representation_summary: dict[str, Any] = {}
    for representation in representations:
        matrix = _representation_matrix(rows, representation)
        full_metrics = _bounded_metrics_for_matrix(matrix, maxdim=maxdim)

        subsamples: list[dict[str, Any]] = []
        for size in sample_sizes:
            if size > matrix.shape[0]:
                continue
            for replicate_index in range(replicates):
                indices = sample_plans[(size, replicate_index)]
                metrics = _bounded_metrics_for_matrix(matrix[indices], maxdim=maxdim)
                subsamples.append(
                    {
                        "sampleSize": size,
                        "replicate": replicate_index,
                        "samplePlanHash": sample_plan_hash(
                            [sample_keys[int(index)] for index in indices]
                        ),
                        "metrics": metrics,
                    }
                )

        slice_summaries: list[dict[str, Any]] = []
        for key, indices in sorted(slices.items()):
            if len(indices) < min_slice_size:
                continue
            slice_matrix = matrix[np.asarray(indices, dtype=np.int64)]
            slice_summaries.append(
                {
                    "sliceKey": key,
                    "pointCount": len(indices),
                    "metrics": _bounded_metrics_for_matrix(slice_matrix, maxdim=maxdim),
                }
            )

        representation_summary[representation] = {
            "full": full_metrics,
            "subsamples": subsamples,
            "slices": slice_summaries,
        }

    summary = {
        "sourceManifest": str(manifest_path),
        "rowsPath": str(rows_path),
        "specimenCount": len(rows),
        "analysisBackend": "ripser-euclidean",
        "representations": representation_summary,
        "sampleSizes": sample_sizes,
        "replicates": replicates,
        "sliceKey": slice_key,
        "minSliceSize": min_slice_size,
        "seed": seed,
        "samplePlan": "sha256_key_rank_v1",
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "analysis-manifest.json").write_text(
        json.dumps(
            {
                "sourceManifest": str(manifest_path),
                "rowsPath": str(rows_path),
                "summaryPath": "summary.json",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run subsample and cohort-slice topology robustness checks."
    )
    parser.add_argument("--manifest", required=True, help="Path to topology manifest JSON")
    parser.add_argument("--output", help="Output directory for robustness artifacts")
    parser.add_argument(
        "--representations",
        default="fingerprint_only,fingerprint_plus_symmetry",
        help="Comma-separated phenotype representations",
    )
    parser.add_argument(
        "--sample-sizes",
        default="512,1024,2048,4096",
        help="Comma-separated subsample sizes",
    )
    parser.add_argument("--replicates", type=int, default=3, help="Replicates per sample size")
    parser.add_argument("--slice-key", default="runId", help="Row key used for cohort slices")
    parser.add_argument(
        "--min-slice-size",
        type=int,
        default=256,
        help="Minimum cohort-slice size to analyze",
    )
    parser.add_argument("--seed", type=int, default=0, help="Random seed for subsampling")
    parser.add_argument("--maxdim", type=int, default=1, help="Maximum homology dimension")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    manifest_path = Path(args.manifest).expanduser().resolve()
    if not manifest_path.is_file():
        raise SystemExit(f"Missing manifest: {manifest_path}")
    output_dir = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _default_output_dir(manifest_path).resolve()
    )
    summary = run_robustness(
        manifest_path,
        output_dir,
        representations=tuple(
            item.strip() for item in args.representations.split(",") if item.strip()
        ),
        sample_sizes=_parse_sizes(args.sample_sizes),
        replicates=args.replicates,
        slice_key=args.slice_key,
        min_slice_size=args.min_slice_size,
        seed=args.seed,
        maxdim=args.maxdim,
    )
    print(
        "Topology robustness:"
        f" specimens={summary['specimenCount']}"
        f" output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
