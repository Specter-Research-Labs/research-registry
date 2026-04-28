from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lenia_swarm_analysis.generators.cycle_transport import (
    analyze_cycle_transport,
)


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")


def _write_summary(path: Path, rows_path: Path, representative_path: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "rowsPath": str(rows_path),
        "continuation": {
            "hasReentry": True,
            "ambiguousCount": 0,
            "representativeVisitCount": len(representative_path),
            "collapsedRepresentativePath": representative_path,
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_analyze_cycle_transport_detects_interior_cycle_visits(tmp_path: Path) -> None:
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
                ],
            }
        ],
    }
    packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")

    left_rows = [
        {
            "globalAlpha": 0.0,
            "controlLabel": "A",
            "distToA": 0.0,
            "distToB": 0.1,
            "distToCycleSupport": 0.0,
            "nearestRepresentativeSpecimenId": "a",
        },
        {
            "globalAlpha": 1.0,
            "controlLabel": "B",
            "distToA": 0.1,
            "distToB": 0.0,
            "distToCycleSupport": 0.0,
            "nearestRepresentativeSpecimenId": "b",
        },
    ]
    right_rows = list(left_rows)
    left_rows_path = sweep_root / "g1" / "edge00" / "left-anchor" / "rows.json"
    right_rows_path = sweep_root / "g1" / "edge00" / "right-anchor" / "rows.json"
    _write_rows(left_rows_path, left_rows)
    _write_rows(right_rows_path, right_rows)
    _write_summary(
        sweep_root / "g1" / "edge00" / "left-anchor" / "summary.json",
        left_rows_path,
        ["a", "c", "b"],
    )
    _write_summary(
        sweep_root / "g1" / "edge00" / "right-anchor" / "summary.json",
        right_rows_path,
        ["a", "c", "b"],
    )

    edge1_rows_path = sweep_root / "g1" / "edge01" / "left-anchor" / "rows.json"
    _write_rows(edge1_rows_path, left_rows)
    _write_summary(
        sweep_root / "g1" / "edge01" / "left-anchor" / "summary.json",
        edge1_rows_path,
        ["b", "d", "c"],
    )

    summary = analyze_cycle_transport(packet_path, sweep_root, output_dir)

    assert summary["generatorCount"] == 1
    assert summary["aggregate"]["fullCoverageCount"] == 1
    assert summary["aggregate"]["interiorCycleVertexGeneratorCount"] == 1
    report = summary["generators"][0]
    assert report["coveredEdgeCount"] == 2
    assert report["anchorEquivalentEdgeCount"] == 1
    assert report["interiorCycleVertexEdgeCount"] == 2
    assert report["interiorCycleVertexLabels"] == ["c", "d"]
    assert report["repeatedCycleVertexVisits"] == {"b": 2, "c": 2}
    assert report["edgeReports"][0]["anchorEquivalent"] is True
    assert report["edgeReports"][0]["interiorCycleVertexPath"] == ["c"]
    assert report["edgeReports"][1]["anchorEquivalent"] is None
    assert (output_dir / "summary.json").is_file()
    assert (output_dir / "g1.json").is_file()
