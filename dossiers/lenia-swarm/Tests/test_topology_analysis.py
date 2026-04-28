from __future__ import annotations

import json
import math
from pathlib import Path

from lenia_swarm_analysis.topology.analysis import run_analysis


def _fingerprint(theta: float) -> list[int]:
    values = [
        1.0 + math.cos(theta),
        1.0 + math.sin(theta),
        1.0 - math.cos(theta),
        1.0 - math.sin(theta),
    ]
    total = sum(values)
    return [round(value / total * 255) for value in values]


def test_run_analysis_writes_persistence_outputs(tmp_path: Path) -> None:
    rows_path = tmp_path / "rows.jsonl"
    manifest_path = tmp_path / "export.manifest.json"
    output_dir = tmp_path / "analysis"

    rows = []
    for index in range(8):
        theta = 2.0 * math.pi * index / 8.0
        rows.append(
            {
                "specimenId": f"specimen-{index}",
                "genotype": {
                    "vector": [math.cos(theta), math.sin(theta)],
                },
                "terminal": {
                    "fingerprintResolution": 2,
                    "fingerprintU8": _fingerprint(theta),
                },
            }
        )
    rows_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps({"rowsPath": rows_path.name}, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = run_analysis(manifest_path, output_dir, maxdim=1, neighbor_k=3)

    assert summary["specimenCount"] == 8
    assert summary["spaces"]["phenotype"]["dimension"] == 4
    assert summary["spaces"]["phenotype"]["ripser"][1]["featureCount"] >= 1
    assert (output_dir / "summary.json").is_file()
    assert (output_dir / "diagrams.json").is_file()
    assert (output_dir / "betti_curves.json").is_file()
    assert (output_dir / "analysis-manifest.json").is_file()


def test_run_analysis_reports_heterogeneous_genotype_spaces(tmp_path: Path) -> None:
    rows_path = tmp_path / "rows.jsonl"
    manifest_path = tmp_path / "export.manifest.json"
    output_dir = tmp_path / "analysis"

    rows = [
        {
            "specimenId": "flow-0",
            "genotype": {
                "canonicalizer": "flow_lenia_params_v1",
                "vector": [0.0, 1.0],
            },
            "terminal": {
                "fingerprintResolution": 2,
                "fingerprintU8": _fingerprint(0.0),
            },
        },
        {
            "specimenId": "flow-1",
            "genotype": {
                "canonicalizer": "flow_lenia_params_v1",
                "vector": [1.0, 0.0],
            },
            "terminal": {
                "fingerprintResolution": 2,
                "fingerprintU8": _fingerprint(math.pi / 2.0),
            },
        },
        {
            "specimenId": "qd-0",
            "genotype": {
                "canonicalizer": "leniabreeder24_policy_v1",
                "vector": [1.0, 2.0, 3.0],
            },
            "terminal": {
                "fingerprintResolution": 2,
                "fingerprintU8": _fingerprint(math.pi),
            },
        },
        {
            "specimenId": "qd-1",
            "genotype": {
                "canonicalizer": "leniabreeder24_policy_v1",
                "vector": [2.0, 3.0, 4.0],
            },
            "terminal": {
                "fingerprintResolution": 2,
                "fingerprintU8": _fingerprint(3.0 * math.pi / 2.0),
            },
        },
    ]
    rows_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps({"rowsPath": rows_path.name}, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = run_analysis(manifest_path, output_dir, maxdim=1, neighbor_k=2)

    assert summary["specimenCount"] == 4
    assert summary["spaces"]["phenotype"]["dimension"] == 4
    assert summary["spaces"]["genotype"]["status"] == "heterogeneous"
    assert summary["fiberLocality"]["status"] == "heterogeneous"
    groups = summary["spaces"]["genotype"]["canonicalizerGroups"]
    assert len(groups) == 2
    assert {group["canonicalizer"] for group in groups} == {
        "flow_lenia_params_v1",
        "leniabreeder24_policy_v1",
    }
