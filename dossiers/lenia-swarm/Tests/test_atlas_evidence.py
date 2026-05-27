from __future__ import annotations

from lenia_swarm_analysis.morphospace.atlas_evidence import build_atlas_evidence_packet


def test_build_atlas_evidence_packet_selects_validation_seeds() -> None:
    packet = build_atlas_evidence_packet(
        generated_at="2026-05-21T00:00:00+00:00",
        atlas_findings={
            "runId": "run-a",
            "resultCount": 10,
            "featureSpaceId": "common_morphology_v1",
            "motionSummary": {
                "counts": {"coherentMover": 2},
                "displacement": {"count": 10, "max": 12.0},
            },
            "biologicalNearSummary": {
                "fishDistance": {"count": 10, "min": 0.9},
                "fishDistanceLt1": 1,
                "fishDistanceLt2": 2,
                "embryomakerDistance": {"count": 10, "min": 1.4},
                "embryomakerDistanceLt1": 0,
                "embryomakerDistanceLt2": 1,
            },
            "genotypePhenotypeDistortion": {
                "sampleCount": 8,
                "sensitivityRatio": {"p99": 20.0, "max": 40.0},
                "degeneracyRatio": {"max": 5.0},
                "highSensitivityExamples": [{"seed": 7, "neighborSeed": 8}],
                "highDegeneracyExamples": [{"seed": 8, "neighborSeed": 9}],
            },
            "candidates": {
                "compactConnectedMovers": [{"seed": 1}],
                "fishNearest": [{"seed": 2}],
                "embryomakerNearest": [{"seed": 3}],
                "topDisplacement": [{"seed": 4}],
            },
        },
        common_tda={
            "summary": {"observationCount": 10},
            "landmarks": [
                {
                    "label": "landmark-4",
                    "landmarkCount": 4,
                    "pointCount": 10,
                    "topology": {
                        "h1TopPersistence": 0.5,
                        "h1ThresholdCounts": {">=0.100": 1},
                        "peakBetti1": {"count": 1, "scale": 0.3},
                    },
                }
            ],
        },
        h1_regions={
            "topRegions": [
                {
                    "rank": 1,
                    "persistence": 0.5,
                    "endpointRepresentatives": [{"seed": 5}, {"seed": 6}],
                }
            ]
        },
        validation256={
            "summary": {
                "moving128": 2,
                "moving256": 1,
                "compactMoving128": 1,
                "compactMoving256": 0,
            },
            "rows": [{"seed": 1}],
        },
    )

    assert packet["packetKind"] == "fl2c20_motion_atlas_evidence_v1"
    assert packet["finiteSizeValidation"]["movingSurvivalFraction"] == 0.5
    assert packet["finiteSizeValidation"]["compactMovingSurvivalFraction"] == 0.0
    assert packet["topology"]["commonLandmarks"][0]["h1TopPersistence"] == 0.5
    assert packet["selection"]["validationSeeds"] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
