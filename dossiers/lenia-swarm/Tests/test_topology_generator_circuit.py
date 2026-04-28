from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.generators.circuit import analyze_generator_circuits


def _write_summary(path: Path, representative_path: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "continuation": {
            "collapsedRepresentativePath": representative_path,
        }
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_analyze_generator_circuits_composes_oriented_loop(tmp_path: Path) -> None:
    packet_path = tmp_path / "packet.json"
    sweep_root = tmp_path / "sweep"
    output_dir = tmp_path / "out"
    packet = {
        "representation": "fingerprint_plus_symmetry",
        "generators": [
            {
                "generatorId": "g1",
                "persistence": 0.5,
                "representativeSpecimenIds": ["a", "b", "c", "d"],
                "cycleEdges": [
                    {"fromSpecimenId": "a", "toSpecimenId": "b"},
                    {"fromSpecimenId": "b", "toSpecimenId": "c"},
                    {"fromSpecimenId": "d", "toSpecimenId": "c"},
                    {"fromSpecimenId": "a", "toSpecimenId": "d"},
                ],
            }
        ],
    }
    packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")

    _write_summary(sweep_root / "g1" / "edge00" / "left-anchor" / "summary.json", ["a", "b"])
    _write_summary(sweep_root / "g1" / "edge00" / "right-anchor" / "summary.json", ["b", "a"])
    _write_summary(sweep_root / "g1" / "edge01" / "left-anchor" / "summary.json", ["b", "c"])
    _write_summary(sweep_root / "g1" / "edge01" / "right-anchor" / "summary.json", ["c", "b"])
    _write_summary(
        sweep_root / "g1" / "edge02" / "left-anchor" / "summary.json",
        ["d", "c"],
    )
    _write_summary(
        sweep_root / "g1" / "edge02" / "right-anchor" / "summary.json",
        ["c", "d"],
    )
    _write_summary(
        sweep_root / "g1" / "edge03" / "left-anchor" / "summary.json",
        ["a", "d"],
    )
    _write_summary(
        sweep_root / "g1" / "edge03" / "right-anchor" / "summary.json",
        ["d", "a"],
    )

    summary = analyze_generator_circuits(packet_path, sweep_root, output_dir)

    assert summary["generatorCount"] == 1
    assert summary["aggregate"]["exactVertexReturnGeneratorCount"] == 1
    assert summary["aggregate"]["fullCycleCoverageGeneratorCount"] == 1
    report = summary["generators"][0]
    assert report["circuitCount"] == 4
    assert report["exactVertexReturnCount"] == 4
    assert report["visitedAllCycleVerticesCount"] == 4
    first = report["circuits"][0]
    assert first["startSpecimenLabel"] == "a"
    assert first["returnsToStart"] is True
    assert first["endSpecimenLabel"] == "a"
    assert first["returnOffset"] == 0
    assert first["visitedAllCycleVertices"] is True
    assert first["concatenatedCycleVertexPath"] == ["a", "b", "c", "d", "a"]
    assert first["orientationConsistent"] is True
    assert (output_dir / "summary.json").is_file()
    assert (output_dir / "g1.json").is_file()
