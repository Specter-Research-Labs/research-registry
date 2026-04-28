from __future__ import annotations

import json
import math
from pathlib import Path

from lenia_swarm_analysis.generators.analysis import run_generator_analysis


def _fingerprint(theta: float) -> list[int]:
    values = [
        1.0 + math.cos(theta),
        1.0 + math.sin(theta),
        1.0 - math.cos(theta),
        1.0 - math.sin(theta),
    ]
    total = sum(values)
    return [round(value / total * 255) for value in values]


def _row(theta: float, index: int, *, heterogeneous: bool = False) -> dict[str, object]:
    genotype: dict[str, object]
    if heterogeneous:
        if index % 2 == 0:
            genotype = {
                "canonicalizer": "flow_lenia_params_v1",
                "vector": [math.cos(theta), math.sin(theta)],
            }
        else:
            genotype = {
                "canonicalizer": "leniabreeder24_policy_v1",
                "vector": [math.cos(theta), math.sin(theta), float(index)],
            }
    else:
        genotype = {
            "canonicalizer": "flow_lenia_params_v1",
            "vector": [math.cos(theta), math.sin(theta)],
        }
    return {
        "specimenId": f"specimen-{index}",
        "runId": "test-run",
        "campaignId": f"campaign-{index:02d}",
        "seed": index,
        "genotype": genotype,
        "terminal": {
            "fingerprintResolution": 2,
            "fingerprintU8": _fingerprint(theta),
            "angularSymmetry": {
                "harmonics": [0.0] * 8,
                "dominantAmplitude": 0.0,
                "dominantOrder": 0,
                "maxOrder": 8,
                "normalizedEntropy": 0.0,
            },
            "finalMass": 1.0,
            "finalOccupancy": 0.25,
            "finalGyration": 2.0,
        },
        "trajectory": {
            "pathTortuosity": 1.0,
            "movementEfficiency": 1.0,
        },
    }


def test_run_generator_analysis_writes_cycle_packet(tmp_path: Path) -> None:
    rows_path = tmp_path / "rows.jsonl"
    manifest_path = tmp_path / "export.manifest.json"
    output_dir = tmp_path / "generators"

    rows = []
    for index in range(12):
        theta = 2.0 * math.pi * index / 12.0
        rows.append(_row(theta, index))
    rows_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps({"rowsPath": rows_path.name}, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = run_generator_analysis(
        manifest_path,
        output_dir,
        representation="fingerprint_only",
        maxdim=1,
        top_h1=2,
        coeff=2,
    )

    assert summary["specimenCount"] == 12
    assert summary["selectedGeneratorCount"] >= 1
    generators = json.loads((output_dir / "generators.json").read_text(encoding="utf-8"))
    packet = json.loads((output_dir / "generator-packet.json").read_text(encoding="utf-8"))
    assert len(generators) >= 1
    first = generators[0]
    representative = first["representativeCycle"]
    assert representative is not None
    assert representative["vertexCount"] >= 4
    assert first["controlLift"]["status"] == "homogeneous"
    assert first["controlLift"]["genotypeJumpStepCount95"] == 0
    assert packet["version"] == 1
    assert packet["packetKind"] == "topology_generator_packet_v1"
    assert packet["representation"] == "fingerprint_only"
    assert len(packet["generators"]) >= 1
    first_packet = packet["generators"][0]
    assert first_packet["generatorId"].startswith("h1-rank")
    assert len(first_packet["representativeSpecimenIds"]) >= 4
    assert len(first_packet["memberSpecimenIds"]) >= len(first_packet["representativeSpecimenIds"])
    assert (output_dir / "summary.json").is_file()
    assert (output_dir / "analysis-manifest.json").is_file()


def test_run_generator_analysis_marks_heterogeneous_control_lift(tmp_path: Path) -> None:
    rows_path = tmp_path / "rows.jsonl"
    manifest_path = tmp_path / "export.manifest.json"
    output_dir = tmp_path / "generators"

    rows = []
    for index in range(12):
        theta = 2.0 * math.pi * index / 12.0
        rows.append(_row(theta, index, heterogeneous=True))
    rows_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps({"rowsPath": rows_path.name}, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    run_generator_analysis(
        manifest_path,
        output_dir,
        representation="fingerprint_only",
        maxdim=1,
        top_h1=1,
        coeff=2,
    )

    generators = json.loads((output_dir / "generators.json").read_text(encoding="utf-8"))
    assert generators[0]["controlLift"]["status"] == "heterogeneous"
