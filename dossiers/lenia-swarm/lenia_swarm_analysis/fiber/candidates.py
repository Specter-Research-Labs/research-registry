from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import read_json, read_jsonl
from lenia_swarm_analysis.topology.analysis import (
    _collect_genotype_groups,
    _nearest_neighbors,
    _pairwise_distance_matrix,
    _resolve_rows_path,
)
from lenia_swarm_analysis.topology.compare import _representation_matrix


def _default_output_dir(manifest_path: Path) -> Path:
    stem = manifest_path.name.removesuffix(".manifest.json")
    return manifest_path.parent.parent / "fiber-candidates" / stem


def _specimen_summary(row: dict[str, Any]) -> dict[str, Any]:
    genotype = row["genotype"]
    terminal = row["terminal"]
    angular = terminal["angularSymmetry"]
    return {
        "specimenId": row.get("specimenId"),
        "runId": row.get("runId"),
        "campaignId": row.get("campaignId"),
        "seed": row.get("seed"),
        "genotypeHash12": genotype.get("hash12"),
        "fingerprintHash12": terminal.get("fingerprintHash12"),
        "dominantOrder": angular.get("dominantOrder"),
        "dominantAmplitude": angular.get("dominantAmplitude"),
    }


def run_candidate_mining(
    manifest_path: Path,
    output_dir: Path,
    *,
    representation: str,
    phenotype_k: int,
    max_candidates: int,
    max_phenotype_distance: float | None,
) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    rows_path = _resolve_rows_path(manifest_path, manifest)
    rows = read_jsonl(rows_path)
    genotype_groups = _collect_genotype_groups(rows)

    group_summaries: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    seen_pairs: set[tuple[int, int]] = set()
    for group in genotype_groups:
        indices: list[int] = list(group["indices"])
        group_rows = [rows[index] for index in indices]
        phenotype_matrix = _representation_matrix(group_rows, representation)
        phenotype_distances = _pairwise_distance_matrix(phenotype_matrix)
        genotype_distances = _pairwise_distance_matrix(group["matrix"])
        neighbors = _nearest_neighbors(phenotype_distances, phenotype_k)

        group_candidates = 0
        for local_i in range(len(indices)):
            for local_j in neighbors[local_i]:
                global_i = indices[local_i]
                global_j = indices[int(local_j)]
                pair = (min(global_i, global_j), max(global_i, global_j))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                phenotype_distance = float(phenotype_distances[local_i, local_j])
                if (
                    max_phenotype_distance is not None
                    and phenotype_distance > max_phenotype_distance
                ):
                    continue
                genotype_distance = float(genotype_distances[local_i, local_j])
                score = genotype_distance / max(phenotype_distance, 1e-12)
                all_candidates.append(
                    {
                        "groupCanonicalizer": group["canonicalizer"],
                        "groupDimension": int(group["matrix"].shape[1]),
                        "phenotypeDistance": phenotype_distance,
                        "genotypeDistance": genotype_distance,
                        "genotypeOverPhenotype": score,
                        "specimenA": _specimen_summary(rows[global_i]),
                        "specimenB": _specimen_summary(rows[global_j]),
                    }
                )
                group_candidates += 1

        group_summaries.append(
            {
                "canonicalizer": group["canonicalizer"],
                "dimension": int(group["matrix"].shape[1]),
                "pointCount": len(indices),
                "candidateCount": group_candidates,
            }
        )

    all_candidates.sort(
        key=lambda candidate: (
            -float(candidate["genotypeOverPhenotype"]),
            -float(candidate["genotypeDistance"]),
            float(candidate["phenotypeDistance"]),
        )
    )
    top_candidates = all_candidates[:max_candidates]

    summary = {
        "sourceManifest": str(manifest_path),
        "rowsPath": str(rows_path),
        "specimenCount": len(rows),
        "representation": representation,
        "phenotypeNeighborK": phenotype_k,
        "maxPhenotypeDistance": max_phenotype_distance,
        "candidateCount": len(all_candidates),
        "returnedCount": len(top_candidates),
        "groups": group_summaries,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "candidates.json").write_text(
        json.dumps(top_candidates, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "analysis-manifest.json").write_text(
        json.dumps(
            {
                "sourceManifest": str(manifest_path),
                "rowsPath": str(rows_path),
                "summaryPath": "summary.json",
                "candidatesPath": "candidates.json",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mine phenotype-near / genotype-far candidate pairs from topology exports."
    )
    parser.add_argument("--manifest", required=True, help="Path to topology manifest JSON")
    parser.add_argument("--output", help="Output directory for fiber-candidate artifacts")
    parser.add_argument(
        "--representation",
        default="fingerprint_only",
        help="Phenotype representation to use for neighborhood search",
    )
    parser.add_argument(
        "--phenotype-k",
        type=int,
        default=8,
        help="Number of nearest phenotype neighbors to inspect per specimen",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=200,
        help="Maximum number of ranked candidates to write",
    )
    parser.add_argument(
        "--max-phenotype-distance",
        type=float,
        help="Optional maximum phenotype distance threshold",
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
    summary = run_candidate_mining(
        manifest_path,
        output_dir,
        representation=args.representation,
        phenotype_k=args.phenotype_k,
        max_candidates=args.max_candidates,
        max_phenotype_distance=args.max_phenotype_distance,
    )
    print(
        "Fiber candidates:"
        f" specimens={summary['specimenCount']}"
        f" candidates={summary['candidateCount']}"
        f" output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
