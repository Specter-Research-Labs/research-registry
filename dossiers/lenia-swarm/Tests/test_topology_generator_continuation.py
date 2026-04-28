from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.generators.continuation import (
    analyze_continuation_summaries,
)


def _summary_payload(
    *,
    representation: str,
    generator_id: str,
    edge_index: int,
    ambiguous_count: int,
    branch_switch_count: int,
    has_reentry: bool,
    max_escape_ratio: float,
    support_distance: float,
    visit_count: int,
) -> dict[str, object]:
    return {
        "source": {
            "representation": representation,
            "generatorId": generator_id,
            "edgeIndex": edge_index,
        },
        "sourceAnchor": "left",
        "alphaCount": 17,
        "continuation": {
            "successCount": 17,
            "failureCount": 0,
            "ambiguousCount": ambiguous_count,
            "branchSwitchCount": branch_switch_count,
            "hasReentry": has_reentry,
            "visitsNonEndpointRepresentative": True,
            "representativeVisitCount": visit_count,
            "endpointPhenotypeDistance": 0.02,
            "maxEscapeRatio": max_escape_ratio,
            "maxNearestAnchorDistance": 0.2,
            "maxDistanceToCycleSupport": support_distance,
            "maxStepPhenotypeDelta": 0.1,
        },
    }


def test_analyze_continuation_summaries_groups_by_representation(tmp_path: Path) -> None:
    fp = tmp_path / "fp-summary.json"
    sym = tmp_path / "sym-summary.json"
    fp.write_text(
        json.dumps(
            _summary_payload(
                representation="fingerprint_only",
                generator_id="fp-rank01",
                edge_index=1,
                ambiguous_count=7,
                branch_switch_count=7,
                has_reentry=True,
                max_escape_ratio=3.0,
                support_distance=0.18,
                visit_count=5,
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    sym.write_text(
        json.dumps(
            _summary_payload(
                representation="fingerprint_plus_symmetry",
                generator_id="sym-rank01",
                edge_index=3,
                ambiguous_count=2,
                branch_switch_count=5,
                has_reentry=True,
                max_escape_ratio=1.4,
                support_distance=0.14,
                visit_count=8,
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    summary = analyze_continuation_summaries([fp, sym], tmp_path / "out")

    assert summary["runCount"] == 2
    reps = summary["aggregate"]["representations"]
    assert set(reps) == {"fingerprint_only", "fingerprint_plus_symmetry"}
    assert (
        reps["fingerprint_plus_symmetry"]["ambiguityRateMean"]
        < reps["fingerprint_only"]["ambiguityRateMean"]
    )
    assert (
        reps["fingerprint_plus_symmetry"]["maxEscapeRatioMean"]
        < reps["fingerprint_only"]["maxEscapeRatioMean"]
    )
    assert (tmp_path / "out" / "summary.json").is_file()
