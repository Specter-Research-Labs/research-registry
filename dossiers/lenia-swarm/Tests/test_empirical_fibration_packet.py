from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.empirical_fibration_packet import build_empirical_fibration_packet


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_empirical_fibration_packet_keeps_only_finite_witness_fields(
    tmp_path: Path,
) -> None:
    arrangement_path = tmp_path / "arrangement.json"
    _write_json(
        arrangement_path,
        {
            "packetKind": "arrangement_witness_packet_v1",
            "supportsCycleLinkedReentry": True,
            "supportsHiddenStateDominance": True,
            "supportsPositiveLoopSurplus": True,
            "supportsTransportReproducibility": True,
            "supportsDenseWinnerExploration": True,
            "supportsValidatedLoopSurplus": True,
            "topWitnesses": [{"kind": "cycle_generator", "id": "g0"}],
            "topHotspots": [{"kind": "transport_group", "id": "crystal-mh"}],
            "openTransportWitnesses": [
                {
                    "id": "crystal-h0-open",
                    "bundle": "bundle-a",
                    "coordinate": "h.0",
                    "pointCount": 5,
                    "transportToPhenotypeRatio": 27.0,
                }
            ],
            "loopTransportWitnesses": [
                {
                    "id": "crystal-mh",
                    "scaleCount": 3,
                    "bestScaleByStateClosure": {
                        "scale": "medium",
                        "deltaStateClosure": 0.0002,
                    },
                    "bestScaleByRatio": {
                        "scale": "small",
                        "deltaRatio": 1.25,
                    },
                }
            ],
            "reproTransportWitnesses": [
                {
                    "id": "crystal-mh",
                    "kindCount": 4,
                    "allKindsStable": True,
                    "maxStateClosureRange": 0.0,
                    "maxRatioRange": 0.0,
                }
            ],
            "denseTransportWitnesses": [
                {
                    "id": "crystal-mh",
                    "controlGroup": "crystal-mh-medium",
                    "densePointCount": 17,
                    "denseStateClosure": 0.0023,
                    "denseRatio": 23.1,
                    "sparseWinnerControlGroup": "crystal-mh-medium",
                    "sparseWinnerStateSurplus": 0.0002,
                    "sparseWinnerRatioSurplus": 1.25,
                }
            ],
            "validationTransportWitnesses": [
                {
                    "id": "crystal-mixed-medium-wide-validation",
                    "canonicalGroup": "crystal-mixed",
                    "winnerControlGroup": "crystal-mixed-medium-wide",
                    "validationBestControlKind": "zeroarea-mh-dense",
                    "validationDeltaStateClosure": 0.00012,
                    "validationDeltaRatio": 0.9,
                    "survivesValidationByState": True,
                    "survivesValidationByRatio": True,
                    "survivesValidationStrongly": True,
                }
            ],
        },
    )
    cycle_path = tmp_path / "cycle.json"
    _write_json(
        cycle_path,
        {
            "packetKind": "cycle_lift_packet_v1",
            "representation": "fingerprint_plus_symmetry",
            "generators": [
                {
                    "generatorId": "g0",
                    "persistence": 0.2,
                    "edgeCount": 1,
                    "reentryEdgeCount": 1,
                    "nonEndpointRepresentativeEdgeCount": 1,
                    "anchorInvariantEdgeCount": 1,
                    "maxRepresentativeVisitCount": 3,
                    "interestingEdges": [0],
                    "edges": [
                        {
                            "edgeIndex": 0,
                            "fromSpecimenId": "spec-a",
                            "toSpecimenId": "spec-b",
                            "branchSwitchCount": 2,
                            "ambiguousCount": 0,
                            "representativeVisitCount": 3,
                            "hasReentry": True,
                            "visitsNonEndpointRepresentative": True,
                            "anchorInvariance": {
                                "labelDisagreementCount": 0,
                                "maxAnchorPhenotypeDelta": 0.0,
                            },
                        }
                    ],
                }
            ],
        },
    )
    attractor_path = tmp_path / "attractor.json"
    _write_json(
        attractor_path,
        {
            "packetKind": "attractor_packet_v1",
            "representation": "fingerprint_only",
            "scales": [
                {
                    "rank": 1,
                    "componentCount": 2,
                    "components": [
                        {
                            "membershipHash12": "abc123",
                            "specimenCount": 7,
                            "runCount": 2,
                            "campaignCount": 1,
                            "representative": {
                                "specimenId": "spec-a",
                                "dominantOrder": 8,
                            },
                        }
                    ],
                }
            ],
        },
    )

    packet = build_empirical_fibration_packet(
        arrangement_packet_path=arrangement_path,
        cycle_lift_packet_path=cycle_path,
        attractor_packet_path=attractor_path,
    )

    assert packet["packetKind"] == "empirical_fibration_packet_v1"
    assert packet["summary"]["supportsCycleLinkedReentry"] is True
    assert packet["summary"]["supportsHiddenStateDominance"] is True
    assert packet["summary"]["supportsTransportReproducibility"] is True
    assert packet["summary"]["supportsDenseWinnerExploration"] is True
    assert packet["summary"]["supportsValidatedLoopSurplus"] is True
    assert packet["generators"][0]["persistenceRank"] == 1
    assert packet["generators"][0]["interestingEdgeIds"] == ["g0:edge00"]
    assert packet["cycleEdges"][0]["anchorInvariant"] is True
    assert packet["openTransportRuns"][0]["hiddenStateDominant"] is True
    assert packet["transportGroups"][0]["bestScaleByState"] == "medium"
    assert packet["transportGroups"][0]["loopBeatsControlByState"] is True
    assert packet["reproTransportGroups"][0]["allKindsStable"] is True
    assert packet["denseTransportGroups"][0]["densePointCount"] == 17
    assert packet["validationTransportGroups"][0]["survivesValidationStrongly"] is True
    assert packet["attractorScales"][0]["id"] == "h0_scale_rank_01"
    assert packet["attractorComponents"][0]["representativeSpecimenId"] == "spec-a"
