from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.fiber.cycle_lift import build_cycle_lift_packet


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_cycle_lift_packet_merges_dense_and_bidirectional(tmp_path: Path) -> None:
    report_root = tmp_path / "report"
    _write_json(
        report_root / "summary.json",
        {
            "packetPath": "/tmp/generator-packet.json",
            "representation": "fingerprint_plus_symmetry",
        },
    )
    _write_json(
        report_root / "generator-summaries.json",
        [
            {
                "generatorId": "g0",
                "persistence": 0.5,
            }
        ],
    )
    _write_json(
        report_root / "edge-summaries.json",
        [
            {
                "generatorId": "g0",
                "edgeIndex": 1,
                "leftSpecimenId": "s0",
                "rightSpecimenId": "s1",
                "outputDir": "/tmp/coarse",
                "successCount": 5,
                "failureCount": 0,
                "ambiguousCount": 0,
                "branchSwitchCount": 1,
                "collapsedControlPath": ["A", "B"],
                "hasReentry": False,
                "collapsedRepresentativePath": ["s0", "s1"],
                "representativeVisitCount": 2,
                "visitsNonEndpointRepresentative": False,
                "endpointPhenotypeDistance": 0.2,
                "maxNearestAnchorDistance": 0.1,
                "maxEscapeRatio": 0.5,
                "maxDistanceToCycleSupport": 0.05,
                "maxStepPhenotypeDelta": 0.07,
                "maxPhenotypeDistanceToA": 0.1,
                "maxPhenotypeDistanceToB": 0.2,
            }
        ],
    )
    dense = tmp_path / "dense.json"
    _write_json(
        dense,
        {
            "source": {"generatorId": "g0", "edgeIndex": 1},
            "outputDir": "/tmp/dense",
            "alphaCount": 17,
            "continuation": {
                "successCount": 17,
                "failureCount": 0,
                "ambiguousCount": 1,
                "branchSwitchCount": 5,
                "collapsedControlPath": ["A", "B", "A", "B"],
                "hasReentry": True,
                "collapsedRepresentativePath": ["s0", "s2", "s1"],
                "representativeVisitCount": 3,
                "visitsNonEndpointRepresentative": True,
                "endpointPhenotypeDistance": 0.2,
                "maxNearestAnchorDistance": 0.3,
                "maxEscapeRatio": 1.5,
                "maxDistanceToCycleSupport": 0.12,
                "maxStepPhenotypeDelta": 0.15,
                "maxPhenotypeDistanceToA": 0.3,
                "maxPhenotypeDistanceToB": 0.25,
            },
        },
    )
    bidirectional = tmp_path / "bidirectional.json"
    _write_json(
        bidirectional,
        {
            "source": {"generatorId": "g0", "edgeIndex": 1},
            "bidirectional": {
                "comparableCount": 17,
                "labelDisagreementCount": 0,
                "maxAnchorPhenotypeDelta": 0.0,
                "maxAnchorDivergenceRatio": 0.0,
                "meanAnchorPhenotypeDelta": 0.0,
            },
        },
    )

    packet = build_cycle_lift_packet(
        report_root=report_root,
        dense_summaries=[dense],
        bidirectional_summaries=[bidirectional],
    )

    assert packet["packetKind"] == "cycle_lift_packet_v1"
    assert packet["representation"] == "fingerprint_plus_symmetry"
    assert packet["generatorCount"] == 1
    edge = packet["generators"][0]["edges"][0]
    assert edge["alphaCount"] == 17
    assert edge["hasReentry"] is True
    assert edge["visitsNonEndpointRepresentative"] is True
    assert edge["anchorInvariance"]["checked"] is True
    assert packet["generators"][0]["reentryEdgeCount"] == 1
    assert packet["topEdges"][0]["edgeIndex"] == 1
