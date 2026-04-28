from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.agda.facing_packet import build_agda_facing_packet


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_agda_facing_packet_adds_stable_constructors_and_witness_sets(
    tmp_path: Path,
) -> None:
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
                "supportsPositiveLoopSurplus": False,
                "supportsTransportReproducibility": True,
                "supportsDenseWinnerExploration": True,
                "supportsValidatedLoopSurplus": True,
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
                    "hasNonEndpointRepresentativeEdge": False,
                    "hasAnchorInvariantEdge": True,
                    "interestingEdgeIds": ["g0:edge00"],
                }
            ],
            "cycleEdges": [
                {
                    "id": "g0:edge00",
                    "generatorId": "g0",
                    "hasReentry": True,
                    "visitsNonEndpointRepresentative": False,
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
                    "loopBeatsControlByRatio": False,
                }
            ],
            "reproTransportGroups": [
                {
                    "id": "crystal-mixed-medium-wide",
                    "kindCount": 4,
                    "allKindsStable": True,
                    "maxStateClosureRange": 0.0,
                    "maxRatioRange": 0.0,
                }
            ],
            "denseTransportGroups": [
                {
                    "id": "crystal-mixed",
                    "controlGroup": "crystal-mh",
                    "densePointCount": 17,
                    "denseStateClosure": 0.0023,
                    "denseRatio": 23.1,
                    "sparseWinnerControlGroup": "crystal-mh",
                }
            ],
            "validationTransportGroups": [
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
            "attractorScales": [
                {
                    "id": "h0_scale_rank_01",
                    "rank": 1,
                    "componentCount": 2,
                    "topComponentIds": ["h0_scale_rank_01_component_01"],
                }
            ],
            "attractorComponents": [
                {
                    "id": "h0_scale_rank_01_component_01",
                    "scaleId": "h0_scale_rank_01",
                    "specimenCount": 8,
                    "representativeSpecimenId": "spec-a",
                }
            ],
            "topWitnesses": [{"kind": "cycle_generator", "id": "g0"}],
            "topHotspots": [{"kind": "transport_group", "id": "crystal-mh"}],
        },
    )

    packet = build_agda_facing_packet(empirical_path)

    assert packet["packetKind"] == "agda_facing_packet_v1"
    assert packet["ids"]["generators"][0] == {"id": "g0", "ctor": "g_g0"}
    assert packet["generators"][0]["interestingEdgeCtors"] == ["e_g0_edge00"]
    assert packet["cycleEdges"][0]["generatorCtor"] == "g_g0"
    assert packet["summary"]["supportsTransportReproducibility"] is True
    assert packet["summary"]["supportsDenseWinnerExploration"] is True
    assert packet["summary"]["supportsValidatedLoopSurplus"] is True
    assert packet["summary"]["reproTransportGroupCount"] == 1
    assert packet["summary"]["denseTransportGroupCount"] == 1
    assert packet["summary"]["validationTransportGroupCount"] == 1
    assert packet["ids"]["reproTransportGroups"][0]["ctor"] == "trg_crystal_mixed_medium_wide"
    assert packet["ids"]["denseTransportGroups"][0]["ctor"] == "tdg_crystal_mixed"
    assert (
        packet["ids"]["validationTransportGroups"][0]["ctor"]
        == "tvg_crystal_mixed_medium_wide_validation"
    )
    assert packet["denseTransportGroups"][0]["controlGroupCtor"] == "tg_crystal_mh"
    assert packet["validationTransportGroups"][0]["survivesValidationStrongly"] is True
    assert packet["witnessSets"]["reproTransportAllKindsStable"] == [
        "crystal-mixed-medium-wide"
    ]
    assert packet["witnessSets"]["validationTransportStrong"] == [
        "crystal-mixed-medium-wide-validation"
    ]
    assert packet["witnessSets"]["generatorHasReentry"] == ["g0"]
    assert packet["witnessSets"]["edgeAnchorInvariant"] == ["g0:edge00"]


def test_build_agda_facing_packet_escapes_agda_keywords_in_constructors(
    tmp_path: Path,
) -> None:
    empirical_path = tmp_path / "empirical-keyword.json"
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
                "supportsTransportReproducibility": False,
                "supportsDenseWinnerExploration": False,
            },
            "thresholds": {
                "hiddenStateDominanceRatioMin": 1.0,
                "positiveLoopSurplusMinStateClosure": 0.0,
                "anchorInvariantMaxPhenotypeDelta": 0.0,
            },
            "generators": [],
            "cycleEdges": [],
            "openTransportRuns": [
                {
                    "id": "crystal-h0-open",
                    "coordinate": "h.0",
                    "hiddenStateDominant": True,
                    "pointCount": 5,
                }
            ],
            "transportGroups": [],
            "reproTransportGroups": [],
            "denseTransportGroups": [],
            "validationTransportGroups": [],
            "attractorScales": [],
            "attractorComponents": [],
            "topWitnesses": [],
            "topHotspots": [],
        },
    )

    packet = build_agda_facing_packet(empirical_path)

    assert packet["ids"]["openTransportRuns"][0]["ctor"] == "ot_crystal_h0_openkw"


def test_build_agda_facing_packet_escapes_numeric_identifier_parts(
    tmp_path: Path,
) -> None:
    empirical_path = tmp_path / "empirical-numeric.json"
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
                "supportsTransportReproducibility": False,
                "supportsDenseWinnerExploration": False,
            },
            "thresholds": {
                "hiddenStateDominanceRatioMin": 1.0,
                "positiveLoopSurplusMinStateClosure": 0.0,
                "anchorInvariantMaxPhenotypeDelta": 0.0,
            },
            "generators": [],
            "cycleEdges": [],
            "openTransportRuns": [],
            "transportGroups": [],
            "reproTransportGroups": [],
            "denseTransportGroups": [],
            "validationTransportGroups": [],
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
            "topWitnesses": [],
            "topHotspots": [],
        },
    )

    packet = build_agda_facing_packet(empirical_path)

    assert packet["ids"]["attractorScales"][0]["ctor"] == "as_h0_scale_rank_n01"
    assert (
        packet["ids"]["attractorComponents"][0]["ctor"]
        == "ac_h0_scale_rank_n01_component_n01"
    )
