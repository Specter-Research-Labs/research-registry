from __future__ import annotations

import pytest

from lenia_swarm_analysis.generators.reentry import (
    classify_control_label,
    has_reentry,
    summarize_continuation_rows,
)


def test_classify_control_label_marks_close_anchor_distances_ambiguous() -> None:
    assert classify_control_label(dist_to_a=0.0771, dist_to_b=0.0783) == "ambiguous"
    assert classify_control_label(dist_to_a=0.075, dist_to_b=0.092) == "A"
    assert classify_control_label(dist_to_a=0.095, dist_to_b=0.090) == "B"


def test_has_reentry_requires_return_after_switch() -> None:
    assert not has_reentry(["A", "B"])
    assert has_reentry(["A", "B", "A"])
    assert has_reentry(["A", "B", "A", "B"])


def test_summarize_continuation_rows_tracks_reentry_and_representative_visits() -> None:
    rows = [
        {
            "returncode": 0,
            "controlLabel": "A",
            "distToA": 0.0,
            "distToB": 0.1,
            "nearestRepresentativeSpecimenId": "left",
            "distToCycleSupport": 0.0,
            "stepPhenotypeDelta": None,
        },
        {
            "returncode": 0,
            "controlLabel": "B",
            "distToA": 0.09,
            "distToB": 0.08,
            "nearestRepresentativeSpecimenId": "middle",
            "distToCycleSupport": 0.05,
            "stepPhenotypeDelta": 0.09,
        },
        {
            "returncode": 0,
            "controlLabel": "A",
            "distToA": 0.08,
            "distToB": 0.11,
            "nearestRepresentativeSpecimenId": "left",
            "distToCycleSupport": 0.04,
            "stepPhenotypeDelta": 0.07,
        },
        {
            "returncode": 0,
            "controlLabel": "B",
            "distToA": 0.1,
            "distToB": 0.0,
            "nearestRepresentativeSpecimenId": "right",
            "distToCycleSupport": 0.0,
            "stepPhenotypeDelta": 0.1,
        },
    ]

    summary = summarize_continuation_rows(rows)

    assert summary["successCount"] == 4
    assert summary["ambiguousCount"] == 0
    assert summary["collapsedControlPath"] == ["A", "B", "A", "B"]
    assert summary["branchSwitchCount"] == 3
    assert summary["hasReentry"] is True
    assert summary["representativeVisitCount"] == 4
    assert summary["visitsNonEndpointRepresentative"] is True
    assert summary["endpointPhenotypeDistance"] == 0.1
    assert summary["maxEscapeRatio"] == pytest.approx(1.1)


def test_summarize_continuation_rows_supports_targeting_left_endpoint() -> None:
    rows = [
        {
            "returncode": 0,
            "controlLabel": "B",
            "distToA": 0.1,
            "distToB": 0.0,
            "nearestRepresentativeSpecimenId": "right",
            "distToCycleSupport": 0.0,
            "stepPhenotypeDelta": None,
        },
        {
            "returncode": 0,
            "controlLabel": "A",
            "distToA": 0.0,
            "distToB": 0.1,
            "nearestRepresentativeSpecimenId": "left",
            "distToCycleSupport": 0.0,
            "stepPhenotypeDelta": 0.1,
        },
    ]

    summary = summarize_continuation_rows(rows, target_control_label="A")

    assert summary["endpointPhenotypeDistance"] == 0.1
    assert summary["maxEscapeRatio"] == pytest.approx(1.0)
