from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis._io import read_json, read_jsonl
from lenia_swarm_analysis.paths import resolve_input_path, route_output_path

from .analysis import (
    _collect_genotype_groups,
    _diagram_summary,
    _extract_phenotype_matrix,
    _fiber_locality_summary,
    _pairwise_distance_matrix,
    _resolve_rows_path,
)
from .core import (
    distance_scale,
    max_dense_rips_points,
    peak_betti,
    persistence_threshold_counts,
    preflight_rips_request,
    run_ripser_precomputed,
    upper_triangle,
)

REPRESENTATION_NAMES = (
    "fingerprint_only",
    "fingerprint_plus_symmetry",
    "lowdim_descriptor",
)


def _default_output_dir(manifest_path: Path) -> Path:
    stem = manifest_path.name.removesuffix(".manifest.json")
    return manifest_path.parent.parent / "topology-comparison" / stem


def _normalized_fingerprint_rows(rows: list[dict[str, Any]]) -> np.ndarray:
    return _extract_phenotype_matrix(rows)


def _symmetry_matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    vectors: list[np.ndarray] = []
    widths: set[int] = set()
    for index, row in enumerate(rows):
        terminal = row.get("terminal")
        if not isinstance(terminal, dict):
            raise SystemExit(f"Row {index} is missing terminal")
        angular = terminal.get("angularSymmetry")
        if not isinstance(angular, dict):
            raise SystemExit(f"Row {index} is missing terminal.angularSymmetry")
        harmonics = angular.get("harmonics")
        dominant_order = angular.get("dominantOrder")
        max_order = angular.get("maxOrder")
        dominant_amplitude = angular.get("dominantAmplitude")
        normalized_entropy = angular.get("normalizedEntropy")
        if (
            not isinstance(harmonics, list)
            or not isinstance(dominant_order, (int, float))
            or not isinstance(max_order, (int, float))
            or not isinstance(dominant_amplitude, (int, float))
            or not isinstance(normalized_entropy, (int, float))
        ):
            raise SystemExit(f"Row {index} has an invalid angular symmetry payload")
        vector = np.asarray(
            [
                *[float(value) for value in harmonics],
                float(dominant_amplitude),
                float(dominant_order) / max(float(max_order), 1.0),
                float(normalized_entropy),
            ],
            dtype=np.float64,
        )
        widths.add(int(vector.shape[0]))
        vectors.append(vector)
    if len(widths) != 1:
        raise SystemExit("Angular symmetry vectors must have a constant width")
    return np.stack(vectors, axis=0)


def _standardize_columns(matrix: np.ndarray) -> np.ndarray:
    centered = matrix - np.mean(matrix, axis=0, keepdims=True)
    scales = np.std(centered, axis=0, keepdims=True)
    scales[scales <= 1e-12] = 1.0
    return centered / scales


def _require_float(row_index: int, section: dict[str, Any], key: str) -> float:
    value = section.get(key)
    if not isinstance(value, (int, float)):
        raise SystemExit(f"Row {row_index} is missing {key}")
    return float(value)


def _lowdim_descriptor_matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    vectors: list[np.ndarray] = []
    for index, row in enumerate(rows):
        terminal = row.get("terminal")
        trajectory = row.get("trajectory")
        if not isinstance(terminal, dict):
            raise SystemExit(f"Row {index} is missing terminal")
        if not isinstance(trajectory, dict):
            raise SystemExit(f"Row {index} is missing trajectory")
        angular = terminal.get("angularSymmetry")
        if not isinstance(angular, dict):
            raise SystemExit(f"Row {index} is missing terminal.angularSymmetry")
        dominant_order = angular.get("dominantOrder")
        max_order = angular.get("maxOrder")
        harmonics = angular.get("harmonics")
        if not isinstance(dominant_order, (int, float)) or not isinstance(max_order, (int, float)):
            raise SystemExit(f"Row {index} has an invalid dominantOrder/maxOrder payload")
        if not isinstance(harmonics, list) or len(harmonics) < 4:
            raise SystemExit(f"Row {index} has insufficient angular symmetry harmonics")
        vector = np.asarray(
            [
                _require_float(index, terminal, "finalMass"),
                _require_float(index, terminal, "finalOccupancy"),
                _require_float(index, terminal, "finalGyration"),
                _require_float(index, angular, "dominantAmplitude"),
                float(dominant_order) / max(float(max_order), 1.0),
                _require_float(index, angular, "normalizedEntropy"),
                float(harmonics[0]),
                float(harmonics[1]),
                float(harmonics[2]),
                float(harmonics[3]),
                _require_float(index, trajectory, "pathLength"),
                _require_float(index, trajectory, "displacement"),
                _require_float(index, trajectory, "pathTortuosity"),
                _require_float(index, trajectory, "movementEfficiency"),
                _require_float(index, trajectory, "headingCircularVariance"),
                _require_float(index, trajectory, "accumulatedTurnAbs"),
                _require_float(index, trajectory, "centerVelocity"),
                _require_float(index, trajectory, "speedMean"),
            ],
            dtype=np.float64,
        )
        vectors.append(vector)
    return _standardize_columns(np.stack(vectors, axis=0))


def _representation_matrix(rows: list[dict[str, Any]], name: str) -> np.ndarray:
    if name == "fingerprint_only":
        return _normalized_fingerprint_rows(rows)
    if name == "fingerprint_plus_symmetry":
        fingerprints = _normalized_fingerprint_rows(rows)
        symmetry = _symmetry_matrix(rows)
        return np.concatenate([fingerprints, symmetry], axis=1)
    if name == "lowdim_descriptor":
        return _lowdim_descriptor_matrix(rows)
    raise SystemExit(f"Unsupported representation: {name}")


def _representation_label(name: str) -> str:
    labels = {
        "fingerprint_only": "Normalized terminal fingerprint",
        "fingerprint_plus_symmetry": "Fingerprint plus angular symmetry",
        "lowdim_descriptor": "Low-dimensional descriptor control",
    }
    return labels[name]


def _representation_notes(name: str) -> str:
    notes = {
        "fingerprint_only": (
            "Primary proof geometry based on the normalized 32x32 terminal fingerprint."
        ),
        "fingerprint_plus_symmetry": (
            "Fingerprint with raw angular symmetry features appended as a secondary "
            "representation check."
        ),
        "lowdim_descriptor": (
            "Control geometry built from standardized scalar descriptors only; useful for "
            "stress-testing representation dependence, not as the primary proof object."
        ),
    }
    return notes[name]


def _h1_threshold_counts(diagrams: list[list[dict[str, Any]]]) -> dict[str, int]:
    return persistence_threshold_counts(
        diagrams,
        ratios=(0.005, 0.01, 0.015, 0.02),
    )


def _peak_betti_one(betti_curves: list[dict[str, Any]]) -> dict[str, Any] | None:
    return peak_betti(betti_curves)


def _genotype_space(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    genotype_groups = _collect_genotype_groups(rows)
    if len(genotype_groups) == 1:
        genotype_group = genotype_groups[0]
        return (
            {
                "status": "homogeneous",
                "pointCount": int(genotype_group["matrix"].shape[0]),
                "dimension": int(genotype_group["matrix"].shape[1]),
                "distanceMetric": "euclidean",
                "canonicalizer": genotype_group["canonicalizer"],
            },
            genotype_groups,
        )
    return (
        {
            "status": "heterogeneous",
            "pointCount": len(rows),
            "canonicalizerGroups": [
                {
                    "canonicalizer": group["canonicalizer"],
                    "pointCount": int(group["matrix"].shape[0]),
                    "dimension": int(group["matrix"].shape[1]),
                }
                for group in genotype_groups
            ],
        },
        genotype_groups,
    )


def run_comparison(
    manifest_path: Path,
    output_dir: Path,
    *,
    maxdim: int,
    neighbor_k: int,
    representations: tuple[str, ...] = REPRESENTATION_NAMES,
) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    rows_path = _resolve_rows_path(manifest_path, manifest)
    rows = read_jsonl(rows_path, max_rows=max_dense_rips_points(maxdim))
    if len(rows) < 2:
        raise SystemExit("Topology comparison requires at least 2 specimens.")
    ripser_budget = preflight_rips_request(len(rows), maxdim=maxdim)

    genotype_space, genotype_groups = _genotype_space(rows)
    genotype_distances = [_pairwise_distance_matrix(group["matrix"]) for group in genotype_groups]
    diagrams_out: dict[str, Any] = {}
    betti_out: dict[str, Any] = {}
    representation_summaries: dict[str, Any] = {}

    for name in representations:
        matrix = _representation_matrix(rows, name)
        phenotype_distances = _pairwise_distance_matrix(matrix)
        pairwise = upper_triangle(phenotype_distances)
        metric_scale, scale_kind = distance_scale(pairwise)
        ripser_result, _ = run_ripser_precomputed(
            phenotype_distances,
            maxdim=maxdim,
        )
        phenotype_summary = _diagram_summary(
            ripser_result["dgms"],
            metric_scale,
            scale_kind=scale_kind,
        )

        if len(genotype_groups) == 1:
            fiber_locality: dict[str, Any] = {
                "status": "homogeneous",
                **_fiber_locality_summary(genotype_distances[0], phenotype_distances, neighbor_k),
            }
        else:
            fiber_locality = {
                "status": "heterogeneous",
                "groups": [
                    {
                        "canonicalizer": group["canonicalizer"],
                        "pointCount": int(group["matrix"].shape[0]),
                        "dimension": int(group["matrix"].shape[1]),
                        "distanceMetric": "euclidean",
                        "summary": _fiber_locality_summary(
                            genotype_distances[group_index],
                            phenotype_distances[np.ix_(group["indices"], group["indices"])],
                            neighbor_k,
                        ),
                    }
                    for group_index, group in enumerate(genotype_groups)
                ],
            }

        diagrams_out[name] = phenotype_summary["diagrams"]
        betti_out[name] = phenotype_summary["bettiCurves"]
        representation_summaries[name] = {
            "label": _representation_label(name),
            "notes": _representation_notes(name),
            "pointCount": int(matrix.shape[0]),
            "dimension": int(matrix.shape[1]),
            "distanceMetric": "euclidean",
            "budget": ripser_budget,
            "scaleMax": phenotype_summary["scaleMax"],
            "scaleReference": phenotype_summary["scaleReference"],
            "ripser": phenotype_summary["summaries"],
            "h1ThresholdCounts": _h1_threshold_counts(phenotype_summary["diagrams"]),
            "persistenceThresholdUnits": "fraction_of_declared_scale",
            "peakBetti1": _peak_betti_one(phenotype_summary["bettiCurves"]),
            "fiberLocality": fiber_locality,
        }

    summary = {
        "sourceManifest": str(manifest_path),
        "rowsPath": str(rows_path),
        "specimenCount": len(rows),
        "analysisBackend": "numpy-gram-exact",
        "genotype": genotype_space,
        "representations": representation_summaries,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "diagrams.json").write_text(
        json.dumps(diagrams_out, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "betti_curves.json").write_text(
        json.dumps(betti_out, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "analysis-manifest.json").write_text(
        json.dumps(
            {
                "sourceManifest": str(manifest_path),
                "rowsPath": str(rows_path),
                "summaryPath": "summary.json",
                "diagramsPath": "diagrams.json",
                "bettiCurvesPath": "betti_curves.json",
                "representations": list(representations),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare persistent topology across phenotype-space representations."
    )
    parser.add_argument("--manifest", required=True, help="Path to topology manifest JSON")
    parser.add_argument(
        "--output",
        help=(
            "Output directory for topology-comparison artifacts. Defaults to "
            "outputs/topology-comparison/<stem>"
        ),
    )
    parser.add_argument(
        "--maxdim",
        type=int,
        default=1,
        help="Maximum homology dimension for ripser",
    )
    parser.add_argument(
        "--neighbor-k",
        type=int,
        default=8,
        help="Neighborhood size for genotype-phenotype fiber locality summary",
    )
    parser.add_argument(
        "--representations",
        default=",".join(REPRESENTATION_NAMES),
        help="Comma-separated representation names to compare",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    manifest_path = resolve_input_path(args.manifest)
    if not manifest_path.is_file():
        raise SystemExit(f"Missing manifest: {manifest_path}")
    output_dir = (
        route_output_path(args.output)
        if args.output
        else _default_output_dir(manifest_path).resolve()
    )
    representations = tuple(
        item.strip() for item in args.representations.split(",") if item.strip()
    )
    unknown = [name for name in representations if name not in REPRESENTATION_NAMES]
    if unknown:
        raise SystemExit(
            "Unsupported representations: "
            + ", ".join(sorted(unknown))
            + ". Supported: "
            + ", ".join(REPRESENTATION_NAMES)
        )
    summary = run_comparison(
        manifest_path,
        output_dir,
        maxdim=args.maxdim,
        neighbor_k=args.neighbor_k,
        representations=representations,
    )
    print(
        "Topology comparison:"
        f" specimens={summary['specimenCount']}"
        f" representations={','.join(representations)}"
        f" output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
