from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from lenia_swarm_analysis.topology.compare import run_comparison
from lenia_swarm_analysis.topology.core import max_dense_rips_points


def _fingerprint(theta: float) -> list[int]:
    values = [
        1.0 + math.cos(theta),
        1.0 + math.sin(theta),
        1.0 - math.cos(theta),
        1.0 - math.sin(theta),
    ]
    total = sum(values)
    return [round(value / total * 255) for value in values]


def _row(theta: float, index: int) -> dict[str, object]:
    return {
        "specimenId": f"specimen-{index}",
        "genotype": {
            "canonicalizer": "flow_lenia_params_v1",
            "vector": [math.cos(theta), math.sin(theta)],
        },
        "terminal": {
            "fingerprintResolution": 2,
            "fingerprintU8": _fingerprint(theta),
            "angularSymmetry": {
                "harmonics": [
                    abs(math.cos(theta)),
                    abs(math.sin(theta)),
                    0.5 * abs(math.cos(2.0 * theta)),
                    0.5 * abs(math.sin(2.0 * theta)),
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                ],
                "dominantAmplitude": 0.5 + 0.5 * abs(math.cos(theta)),
                "dominantOrder": 2,
                "maxOrder": 8,
                "normalizedEntropy": 0.75,
            },
            "finalMass": 1.0 + 0.1 * math.cos(theta),
            "finalOccupancy": 0.25 + 0.05 * math.sin(theta),
            "finalGyration": 2.0 + 0.3 * math.cos(theta),
            "componentCount": 1.0,
            "momentAnisotropy": 0.2 + 0.1 * abs(math.cos(theta)),
            "momentDensity": 0.1 + 0.05 * abs(math.sin(theta)),
            "largestComponentFraction": 1.0,
            "largestComponentAnisotropy": 0.3 + 0.05 * abs(math.cos(theta)),
            "hu1": 0.1 + 0.01 * math.cos(theta),
            "hu2": -0.2 + 0.01 * math.sin(theta),
            "hu3": -0.3 + 0.02 * math.cos(theta),
            "hu4": -0.4 + 0.02 * math.sin(theta),
        },
        "trajectory": {
            "pathLength": 1.0 + 0.2 * abs(math.sin(theta)),
            "displacement": 0.5 + 0.1 * math.cos(theta),
            "pathTortuosity": 2.0 + abs(math.sin(theta)),
            "movementEfficiency": 0.5 + 0.1 * math.cos(theta),
            "headingCircularVariance": 0.3 + 0.1 * abs(math.sin(theta)),
            "accumulatedTurnAbs": 0.4 + 0.2 * abs(math.cos(theta)),
            "centerVelocity": 0.01 + 0.001 * abs(math.sin(theta)),
            "speedMean": 0.02 + 0.001 * abs(math.cos(theta)),
        },
    }


def test_run_comparison_writes_representation_outputs(tmp_path: Path) -> None:
    rows_path = tmp_path / "rows.jsonl"
    manifest_path = tmp_path / "export.manifest.json"
    output_dir = tmp_path / "comparison"

    rows = []
    for index in range(8):
        theta = 2.0 * math.pi * index / 8.0
        rows.append(_row(theta, index))
    rows_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps({"rowsPath": rows_path.name}, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = run_comparison(manifest_path, output_dir, maxdim=1, neighbor_k=3)

    assert summary["specimenCount"] == 8
    assert set(summary["representations"]) == {
        "fingerprint_only",
        "fingerprint_plus_symmetry",
        "lowdim_descriptor",
    }
    assert summary["representations"]["fingerprint_only"]["dimension"] == 4
    assert summary["representations"]["fingerprint_plus_symmetry"]["dimension"] == 15
    assert summary["representations"]["lowdim_descriptor"]["dimension"] == 18
    assert summary["representations"]["fingerprint_only"]["budget"][
        "estimatedWorkingBytes"
    ] > 0
    assert summary["representations"]["fingerprint_only"]["ripser"][1]["featureCount"] >= 1
    assert (output_dir / "summary.json").is_file()
    assert (output_dir / "diagrams.json").is_file()
    assert (output_dir / "betti_curves.json").is_file()
    assert (output_dir / "analysis-manifest.json").is_file()


def test_comparison_preflights_before_genotype_or_pairwise_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lenia_swarm_analysis.topology import compare as module

    unsafe_count = max_dense_rips_points(1) + 1
    monkeypatch.setattr(module, "read_json", lambda path: {})
    monkeypatch.setattr(module, "_resolve_rows_path", lambda path, manifest: path)
    monkeypatch.setattr(
        module,
        "read_jsonl",
        lambda path, **_kwargs: [{}] * unsafe_count,
    )
    monkeypatch.setattr(
        module,
        "_genotype_space",
        lambda rows: pytest.fail("genotype allocation ran before Rips preflight"),
    )

    with pytest.raises(ValueError, match="estimated working memory"):
        module.run_comparison(
            tmp_path / "manifest.json",
            tmp_path / "out",
            maxdim=1,
            neighbor_k=2,
        )
