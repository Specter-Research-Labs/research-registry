from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.agda.package import build_agda_package


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_agda_package_writes_generated_and_semantic_modules(tmp_path: Path) -> None:
    empirical_path = tmp_path / "empirical.json"
    _write_json(
        empirical_path,
        {
            "packetKind": "empirical_fibration_packet_v1",
            "summary": {
                "topologyRepresentation": "fingerprint_plus_symmetry",
                "attractorRepresentation": "fingerprint_only",
                "supportsCycleLinkedReentry": True,
                "supportsHiddenStateDominance": True,
                "supportsPositiveLoopSurplus": True,
            },
            "thresholds": {
                "hiddenStateDominanceRatioMin": 1.0,
                "positiveLoopSurplusMinStateClosure": 0.0,
                "anchorInvariantMaxPhenotypeDelta": 0.0,
            },
            "generators": [
                {
                    "id": "g0",
                    "persistenceRank": 1,
                    "hasReentryEdge": True,
                    "hasNonEndpointRepresentativeEdge": True,
                    "hasAnchorInvariantEdge": True,
                    "interestingEdgeIds": ["g0:edge00"],
                }
            ],
            "cycleEdges": [
                {
                    "id": "g0:edge00",
                    "generatorId": "g0",
                    "hasReentry": True,
                    "visitsNonEndpointRepresentative": True,
                    "anchorInvariant": True,
                    "representativeVisitCount": 3,
                    "branchSwitchCount": 4,
                }
            ],
            "openTransportRuns": [
                {
                    "id": "crystal-h0-open",
                    "coordinate": "h.0",
                    "hiddenStateDominant": True,
                    "pointCount": 5,
                }
            ],
            "transportGroups": [
                {
                    "id": "crystal-mh",
                    "bestScaleByState": "medium",
                    "bestScaleByRatio": "small",
                    "scaleCount": 3,
                    "loopBeatsControlByState": True,
                    "loopBeatsControlByRatio": True,
                }
            ],
            "attractorScales": [
                {
                    "id": "h0_scale_rank_01",
                    "rank": 1,
                    "componentCount": 1,
                    "topComponentIds": ["h0_scale_rank_01_component_01"],
                }
            ],
            "attractorComponents": [
                {
                    "id": "h0_scale_rank_01_component_01",
                    "scaleId": "h0_scale_rank_01",
                    "specimenCount": 7,
                    "representativeSpecimenId": "spec-a",
                }
            ],
            "topWitnesses": [{"kind": "cycle_generator", "id": "g0"}],
            "topHotspots": [{"kind": "transport_group", "id": "crystal-mh"}],
        },
    )

    semantic_root = tmp_path / "semantic"
    semantic_file = semantic_root / "Morphospace/Empirical/Fibration.agda"
    semantic_file.parent.mkdir(parents=True, exist_ok=True)
    semantic_file.write_text(
        "module Morphospace.Empirical.Fibration where\n",
        encoding="utf-8",
    )

    output_root = tmp_path / "out"
    result = build_agda_package(
        empirical_path,
        output_root=output_root,
        semantic_source_root=semantic_root,
    )

    assert result["generatedFileCount"] == 3
    assert result["semanticFileCount"] == 1
    assert (output_root / "agda-facing-packet.json").exists()
    assert (output_root / "Morphospace/Generated/Ids.agda").exists()
    assert (output_root / "Morphospace/Generated/Witnesses.agda").exists()
    assert (output_root / "Morphospace/Generated/Attractors.agda").exists()
    assert (output_root / "Morphospace/Empirical/Fibration.agda").exists()
