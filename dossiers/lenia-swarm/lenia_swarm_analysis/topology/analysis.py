from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from ripser import ripser


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return data


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise SystemExit(f"{path}:{line_no}: expected a JSON object per row")
            rows.append(row)
    return rows


def _default_output_dir(manifest_path: Path) -> Path:
    stem = manifest_path.name.removesuffix(".manifest.json")
    return manifest_path.parent.parent / "topology-analysis" / stem


def _resolve_rows_path(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    rows_name = manifest.get("rowsPath")
    if not isinstance(rows_name, str) or not rows_name:
        raise SystemExit(f"{manifest_path}: missing rowsPath")
    rows_path = manifest_path.parent / rows_name
    if not rows_path.is_file():
        raise SystemExit(f"Missing topology rows file: {rows_path}")
    return rows_path


def _collect_genotype_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for index, row in enumerate(rows):
        genotype = row.get("genotype")
        if not isinstance(genotype, dict):
            raise SystemExit(f"Row {index} is missing genotype")
        values = genotype.get("vector")
        array = np.asarray(values, dtype=np.float64)
        if array.ndim != 1:
            raise SystemExit(f"Row {index} genotype.vector is not 1D")
        canonicalizer = genotype.get("canonicalizer")
        if not isinstance(canonicalizer, str) or not canonicalizer:
            canonicalizer = "unknown"
        dimension = int(array.shape[0])
        key = (canonicalizer, dimension)
        if key not in groups_by_key:
            groups_by_key[key] = {
                "canonicalizer": canonicalizer,
                "dimension": dimension,
                "indices": [],
                "vectors": [],
            }
        groups_by_key[key]["indices"].append(index)
        groups_by_key[key]["vectors"].append(array)

    groups: list[dict[str, Any]] = []
    for canonicalizer, dimension in sorted(groups_by_key):
        group = groups_by_key[(canonicalizer, dimension)]
        groups.append(
            {
                "canonicalizer": canonicalizer,
                "dimension": dimension,
                "indices": list(group["indices"]),
                "matrix": np.stack(group["vectors"], axis=0),
            }
        )
    return groups


def _extract_phenotype_matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    vectors: list[np.ndarray] = []
    for index, row in enumerate(rows):
        terminal = row.get("terminal")
        if not isinstance(terminal, dict):
            raise SystemExit(f"Row {index} is missing terminal")
        values = terminal.get("fingerprintU8")
        resolution = terminal.get("fingerprintResolution")
        if not isinstance(values, list) or not isinstance(resolution, int):
            raise SystemExit(f"Row {index} is missing terminal fingerprint payload")
        expected = resolution * resolution
        if len(values) != expected:
            raise SystemExit(
                "Row "
                f"{index} fingerprint length {len(values)} does not match resolution {resolution}"
            )
        vector = np.asarray(values, dtype=np.float64) / 255.0
        total = float(vector.sum())
        if total > 1e-12:
            vector /= total
        vectors.append(vector)
    widths = {vector.shape[0] for vector in vectors}
    if len(widths) != 1:
        raise SystemExit("Phenotype fingerprints must have a constant width")
    return np.stack(vectors, axis=0)


def _pairwise_distance_matrix(matrix: np.ndarray) -> np.ndarray:
    if matrix.ndim != 2:
        raise SystemExit("Distance matrices require a 2D input matrix")
    if matrix.shape[0] == 0:
        return np.zeros((0, 0), dtype=np.float64)
    features = np.asarray(matrix, dtype=np.float64, order="C")
    squared_norms = np.sum(features * features, axis=1, dtype=np.float64)
    distances = features @ features.T
    distances *= -2.0
    distances += squared_norms[:, None]
    distances += squared_norms[None, :]
    np.maximum(distances, 0.0, out=distances)
    np.sqrt(distances, out=distances)
    np.fill_diagonal(distances, 0.0)
    return distances


def _upper_triangle(distances: np.ndarray) -> np.ndarray:
    if distances.shape[0] < 2:
        return np.zeros((0,), dtype=np.float64)
    tri = np.triu_indices(distances.shape[0], k=1)
    return distances[tri]


def _pearson_correlation(lhs: np.ndarray, rhs: np.ndarray) -> float | None:
    if lhs.shape != rhs.shape:
        raise SystemExit("Pearson correlation requires arrays with matching shape")
    if lhs.size == 0:
        return None
    lhs_centered = lhs - np.mean(lhs)
    rhs_centered = rhs - np.mean(rhs)
    lhs_norm = float(np.linalg.norm(lhs_centered))
    rhs_norm = float(np.linalg.norm(rhs_centered))
    if lhs_norm <= 1e-12 or rhs_norm <= 1e-12:
        return None
    return float(np.dot(lhs_centered, rhs_centered) / (lhs_norm * rhs_norm))


def _nearest_neighbors(distances: np.ndarray, neighbor_k: int) -> np.ndarray:
    point_count = distances.shape[0]
    if point_count < 2:
        return np.zeros((point_count, 0), dtype=np.int64)
    effective_k = min(max(1, neighbor_k), point_count - 1)
    neighbors = np.empty((point_count, effective_k), dtype=np.int64)
    for index in range(point_count):
        row = distances[index].copy()
        row[index] = np.inf
        candidate_indices = np.argpartition(row, effective_k - 1)[:effective_k]
        ordered = np.argsort(row[candidate_indices])
        neighbors[index] = candidate_indices[ordered]
    return neighbors


def _betti_curve(diagram: np.ndarray, grid: np.ndarray) -> list[int]:
    if diagram.size == 0:
        return [0 for _ in grid]
    births = diagram[:, 0]
    deaths = diagram[:, 1]
    curve: list[int] = []
    for radius in grid:
        alive = (births <= radius) & ((radius < deaths) | np.isinf(deaths))
        curve.append(int(np.count_nonzero(alive)))
    return curve


def _diagram_summary(diagrams: list[np.ndarray], pairwise_max: float) -> dict[str, Any]:
    finite_deaths = [
        float(death)
        for diagram in diagrams
        for death in diagram[:, 1]
        if math.isfinite(float(death))
    ]
    scale_max = max(finite_deaths, default=pairwise_max)
    scale_max = max(scale_max, 1e-6)
    grid = np.linspace(0.0, scale_max, num=64, dtype=np.float64)

    summaries: list[dict[str, Any]] = []
    json_diagrams: list[list[dict[str, Any]]] = []
    betti_curves: list[dict[str, Any]] = []
    for dimension, diagram in enumerate(diagrams):
        entries: list[dict[str, Any]] = []
        persistences: list[float] = []
        essential_count = 0
        for birth, death in diagram.tolist():
            finite_death = None if math.isinf(death) else float(death)
            persistence = None if finite_death is None else finite_death - float(birth)
            if persistence is not None:
                persistences.append(persistence)
            else:
                essential_count += 1
            entries.append(
                {
                    "birth": float(birth),
                    "death": finite_death,
                    "persistence": persistence,
                }
            )
        persistences.sort(reverse=True)
        json_diagrams.append(entries)
        betti_curves.append(
            {
                "dimension": dimension,
                "scale": [float(value) for value in grid],
                "betti": _betti_curve(diagram, grid),
            }
        )
        summaries.append(
            {
                "dimension": dimension,
                "featureCount": len(entries),
                "essentialCount": essential_count,
                "topPersistence": persistences[:8],
            }
        )
    return {
        "scaleMax": scale_max,
        "summaries": summaries,
        "diagrams": json_diagrams,
        "bettiCurves": betti_curves,
    }


def _fiber_locality_summary(
    genotype_distances: np.ndarray,
    phenotype_distances: np.ndarray,
    neighbor_k: int,
) -> dict[str, Any]:
    if genotype_distances.shape != phenotype_distances.shape:
        raise SystemExit(
            "Fiber locality requires genotype and phenotype distance matrices of equal shape"
        )
    if genotype_distances.ndim != 2:
        raise SystemExit("Fiber locality requires square distance matrices")
    if genotype_distances.shape[0] < 2:
        return {
            "neighborK": neighbor_k,
            "pairwiseDistanceCorrelation": None,
            "meanPhenotypeDistanceOfGenotypeNeighbors": None,
            "meanGenotypeDistanceOfPhenotypeNeighbors": None,
        }

    genotype_pairwise = _upper_triangle(genotype_distances)
    phenotype_pairwise = _upper_triangle(phenotype_distances)
    pairwise_correlation = _pearson_correlation(genotype_pairwise, phenotype_pairwise)

    effective_k = min(max(1, neighbor_k), genotype_distances.shape[0] - 1)
    genotype_neighbors = _nearest_neighbors(genotype_distances, effective_k)
    phenotype_neighbors = _nearest_neighbors(phenotype_distances, effective_k)
    genotype_neighbor_means: list[float] = []
    phenotype_neighbor_means: list[float] = []
    for index in range(genotype_distances.shape[0]):
        genotype_neighbor_means.append(
            float(np.mean(phenotype_distances[index, genotype_neighbors[index]]))
        )
        phenotype_neighbor_means.append(
            float(np.mean(genotype_distances[index, phenotype_neighbors[index]]))
        )

    return {
        "neighborK": effective_k,
        "pairwiseDistanceCorrelation": pairwise_correlation,
        "meanPhenotypeDistanceOfGenotypeNeighbors": float(np.mean(genotype_neighbor_means)),
        "meanGenotypeDistanceOfPhenotypeNeighbors": float(np.mean(phenotype_neighbor_means)),
    }


def run_analysis(
    manifest_path: Path,
    output_dir: Path,
    *,
    maxdim: int,
    neighbor_k: int,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    rows_path = _resolve_rows_path(manifest_path, manifest)
    rows = _read_jsonl(rows_path)
    if len(rows) < 2:
        raise SystemExit("Topology analysis requires at least 2 specimens.")

    phenotype = _extract_phenotype_matrix(rows)
    phenotype_distances = _pairwise_distance_matrix(phenotype)
    pairwise_max = float(np.max(phenotype_distances))

    phenotype_result = ripser(phenotype, maxdim=maxdim, metric="euclidean")
    phenotype_summary = _diagram_summary(phenotype_result["dgms"], pairwise_max)

    genotype_groups = _collect_genotype_groups(rows)
    if len(genotype_groups) == 1:
        genotype_group = genotype_groups[0]
        genotype_space: dict[str, Any] = {
            "status": "homogeneous",
            "pointCount": int(genotype_group["matrix"].shape[0]),
            "dimension": int(genotype_group["matrix"].shape[1]),
            "distanceMetric": "euclidean",
            "canonicalizer": genotype_group["canonicalizer"],
        }
        genotype_distances = _pairwise_distance_matrix(genotype_group["matrix"])
        fiber_locality: dict[str, Any] = {
            "status": "homogeneous",
            **_fiber_locality_summary(
                genotype_distances,
                phenotype_distances,
                neighbor_k=neighbor_k,
            ),
        }
    else:
        genotype_space = {
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
        }
        fiber_locality = {
            "status": "heterogeneous",
            "groups": [
                {
                    "canonicalizer": group["canonicalizer"],
                    "pointCount": int(group["matrix"].shape[0]),
                    "dimension": int(group["matrix"].shape[1]),
                    "distanceMetric": "euclidean",
                    "summary": _fiber_locality_summary(
                        _pairwise_distance_matrix(group["matrix"]),
                        phenotype_distances[np.ix_(group["indices"], group["indices"])],
                        neighbor_k=neighbor_k,
                    ),
                }
                for group in genotype_groups
            ],
        }

    summary = {
        "sourceManifest": str(manifest_path),
        "rowsPath": str(rows_path),
        "specimenCount": len(rows),
        "analysisBackend": "numpy-gram-exact",
        "spaces": {
            "phenotype": {
                "pointCount": int(phenotype.shape[0]),
                "dimension": int(phenotype.shape[1]),
                "distanceMetric": "euclidean",
                "ripser": phenotype_summary["summaries"],
                "scaleMax": phenotype_summary["scaleMax"],
            },
            "genotype": genotype_space,
        },
        "fiberLocality": fiber_locality,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_out = {
        "createdAt": Path(rows_path).stat().st_mtime,
        "sourceManifest": str(manifest_path),
        "rowsPath": str(rows_path),
        "summaryPath": "summary.json",
        "diagramsPath": "diagrams.json",
        "bettiCurvesPath": "betti_curves.json",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "diagrams.json").write_text(
        json.dumps({"phenotype": phenotype_summary["diagrams"]}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "betti_curves.json").write_text(
        json.dumps({"phenotype": phenotype_summary["bettiCurves"]}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "analysis-manifest.json").write_text(
        json.dumps(manifest_out, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute persistent topology summaries from lenia-swarm topology artifacts."
        )
    )
    parser.add_argument("--manifest", required=True, help="Path to topology manifest JSON")
    parser.add_argument(
        "--output",
        help=(
            "Output directory for topology analysis artifacts. Defaults to "
            "outputs/topology-analysis/<stem>"
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
    summary = run_analysis(
        manifest_path,
        output_dir,
        maxdim=args.maxdim,
        neighbor_k=args.neighbor_k,
    )
    print(
        "Topology analysis:"
        f" specimens={summary['specimenCount']}"
        f" phenotype_dim={summary['spaces']['phenotype']['dimension']}"
        f" output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
