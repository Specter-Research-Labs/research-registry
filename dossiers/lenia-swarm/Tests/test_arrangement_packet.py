from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.arrangement_packet import build_arrangement_witness_packet


def test_build_arrangement_witness_packet_merges_cycle_and_transport_layers(
    tmp_path: Path,
) -> None:
    cycle_path = tmp_path / "cycle.json"
    cycle_path.write_text(
        json.dumps(
            {
                "packetKind": "cycle_lift_packet_v1",
                "representation": "fingerprint_plus_symmetry",
                "generators": [
                    {
                        "generatorId": "g0",
                        "persistence": 0.1,
                        "edgeCount": 3,
                        "reentryEdgeCount": 2,
                        "nonEndpointRepresentativeEdgeCount": 3,
                        "anchorInvariantEdgeCount": 1,
                        "maxEscapeRatio": 1.5,
                        "maxDistanceToCycleSupport": 0.2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    atlas_path = tmp_path / "atlas.json"
    atlas_path.write_text(
        json.dumps(
            {
                "packetKind": "stateful_continuation_batch_packet_v1",
                "runs": [
                    {
                        "name": "crystal-m0-open",
                        "bundle": "bundle-a",
                        "coordinate": "m.0",
                        "pointCount": 5,
                        "endpointPhenotypeDistance": 0.00005,
                        "endpointTransportedStateDistance": 0.0014,
                        "transportToPhenotypeRatio": 28.0,
                        "maxTransportedStateDistanceFromStart": 0.0014,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    scale_path = tmp_path / "scale.json"
    scale_path.write_text(
        json.dumps(
            {
                "packetKind": "transport_scale_report_v1",
                "groups": [
                    {
                        "controlGroup": "crystal-mh",
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
            }
        ),
        encoding="utf-8",
    )
    hotspot_path = tmp_path / "hotspot.json"
    hotspot_path.write_text(
        json.dumps(
            {
                "packetKind": "morphospace_hotspot_packet_v1",
                "topHotspots": [
                    {"kind": "cycle_generator", "id": "g0"},
                    {"kind": "transport_group", "id": "crystal-mh"},
                ],
            }
        ),
        encoding="utf-8",
    )
    repro_path = tmp_path / "repro.json"
    repro_path.write_text(
        json.dumps(
            {
                "packetKind": "transport_repro_report_v1",
                "groups": [
                    {
                        "controlGroup": "crystal-mh",
                        "kindCount": 4,
                        "allKindsStable": True,
                        "maxStateClosureRange": 0.0,
                        "maxRatioRange": 0.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    dense_path = tmp_path / "dense.json"
    dense_path.write_text(
        json.dumps(
            {
                "packetKind": "transport_dense_report_v1",
                "groups": [
                    {
                        "controlGroup": "crystal-mh-medium",
                        "canonicalGroup": "crystal-mh",
                        "densePointCount": 17,
                        "denseStateClosure": 0.0023,
                        "denseRatio": 23.1,
                        "sparseWinnerControlGroup": "crystal-mh-medium",
                        "sparseWinnerStateSurplus": 0.0002,
                        "sparseWinnerRatioSurplus": 1.25,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    validation_path = tmp_path / "validation.json"
    validation_path.write_text(
        json.dumps(
            {
                "packetKind": "transport_validation_report_v1",
                "groups": [
                    {
                        "validationControlGroup": "crystal-mixed-medium-wide-validation",
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
            }
        ),
        encoding="utf-8",
    )

    packet = build_arrangement_witness_packet(
        cycle_lift_packet=cycle_path,
        atlas_batch_packet=atlas_path,
        transport_scale_report=scale_path,
        transport_repro_report=repro_path,
        transport_dense_report=dense_path,
        transport_validation_report=validation_path,
        hotspot_packet=hotspot_path,
    )

    assert packet["packetKind"] == "arrangement_witness_packet_v1"
    assert packet["supportsCycleLinkedReentry"] is True
    assert packet["supportsHiddenStateDominance"] is True
    assert packet["supportsPositiveLoopSurplus"] is True
    assert packet["supportsTransportReproducibility"] is True
    assert packet["supportsDenseWinnerExploration"] is True
    assert packet["supportsValidatedLoopSurplus"] is True
    assert packet["cycleWitnessCount"] == 1
    assert packet["openTransportWitnessCount"] == 1
    assert packet["loopTransportWitnessCount"] == 1
    assert packet["reproTransportWitnessCount"] == 1
    assert packet["denseTransportWitnessCount"] == 1
    assert packet["validationTransportWitnessCount"] == 1
    assert packet["topWitnesses"][0]["kind"] in {
        "cycle_generator",
        "open_transport",
        "loop_transport_group",
        "transport_repro_group",
        "transport_dense_group",
        "transport_validation_group",
    }
    assert packet["topHotspots"][0] == {"kind": "cycle_generator", "id": "g0"}


def test_build_arrangement_witness_packet_accepts_transport_winner_packet(
    tmp_path: Path,
) -> None:
    atlas_path = tmp_path / "atlas.json"
    atlas_path.write_text(
        json.dumps(
            {
                "packetKind": "stateful_continuation_batch_packet_v1",
                "runs": [
                    {
                        "name": "mystic-m0-open",
                        "bundle": "bundle-b",
                        "coordinate": "m.0",
                        "pointCount": 5,
                        "endpointPhenotypeDistance": 0.00007,
                        "endpointTransportedStateDistance": 0.0015,
                        "transportToPhenotypeRatio": 21.0,
                        "maxTransportedStateDistanceFromStart": 0.0015,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    winner_path = tmp_path / "winner.json"
    winner_path.write_text(
        json.dumps(
            {
                "packetKind": "transport_winner_packet_v1",
                "groups": [
                    {
                        "controlGroup": "mystic-mixed",
                        "scaleCount": 3,
                        "bestScaleByStateClosure": {
                            "scale": "small-wide",
                            "deltaStateClosure": 0.00036,
                        },
                        "bestScaleByRatio": {
                            "scale": "small",
                            "deltaRatio": 3.08,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    packet = build_arrangement_witness_packet(
        cycle_lift_packet=None,
        atlas_batch_packet=atlas_path,
        transport_scale_report=winner_path,
        transport_repro_report=None,
        transport_dense_report=None,
        transport_validation_report=None,
        hotspot_packet=None,
    )

    assert packet["supportsHiddenStateDominance"] is True
    assert packet["supportsPositiveLoopSurplus"] is True
    assert packet["loopTransportWitnessCount"] == 1
    assert packet["loopTransportWitnesses"][0]["id"] == "mystic-mixed"
