from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.generators.bidirectional import (
    analyze_bidirectional_summaries,
)


def _summary_payload(source_anchor: str, rows_path: Path) -> dict[str, object]:
    return {
        "source": {
            "representation": "fingerprint_plus_symmetry",
            "generatorId": "sym-rank02",
            "edgeIndex": 2,
        },
        "sourceAnchor": source_anchor,
        "rowsPath": str(rows_path),
        "continuation": {
            "successCount": 3,
            "failureCount": 0,
            "ambiguousCount": 0,
            "branchSwitchCount": 1,
            "hasReentry": True,
            "visitsNonEndpointRepresentative": True,
            "representativeVisitCount": 3,
            "endpointPhenotypeDistance": 0.02,
            "maxEscapeRatio": 1.2,
            "maxNearestAnchorDistance": 0.1,
            "maxDistanceToCycleSupport": 0.08,
            "maxStepPhenotypeDelta": 0.06,
        },
    }


def test_analyze_bidirectional_summaries_aligns_by_global_alpha(tmp_path: Path) -> None:
    left_rows = [
        {
            "globalAlpha": 0.0,
            "controlLabel": "A",
            "distToA": 0.0,
            "distToB": 0.1,
            "distToCycleSupport": 0.0,
            "nearestRepresentativeSpecimenId": "left",
        },
        {
            "globalAlpha": 0.5,
            "controlLabel": "B",
            "distToA": 0.08,
            "distToB": 0.07,
            "distToCycleSupport": 0.05,
            "nearestRepresentativeSpecimenId": "middle",
        },
        {
            "globalAlpha": 1.0,
            "controlLabel": "B",
            "distToA": 0.1,
            "distToB": 0.0,
            "distToCycleSupport": 0.0,
            "nearestRepresentativeSpecimenId": "right",
        },
    ]
    right_rows = [
        {
            "globalAlpha": 0.0,
            "controlLabel": "A",
            "distToA": 0.0,
            "distToB": 0.1,
            "distToCycleSupport": 0.01,
            "nearestRepresentativeSpecimenId": "left",
        },
        {
            "globalAlpha": 0.5,
            "controlLabel": "B",
            "distToA": 0.09,
            "distToB": 0.08,
            "distToCycleSupport": 0.04,
            "nearestRepresentativeSpecimenId": "middle",
        },
        {
            "globalAlpha": 1.0,
            "controlLabel": "B",
            "distToA": 0.1,
            "distToB": 0.0,
            "distToCycleSupport": 0.0,
            "nearestRepresentativeSpecimenId": "right",
        },
    ]
    left_rows_path = tmp_path / "left-rows.json"
    right_rows_path = tmp_path / "right-rows.json"
    left_rows_path.write_text(json.dumps(left_rows, indent=2), encoding="utf-8")
    right_rows_path.write_text(json.dumps(right_rows, indent=2), encoding="utf-8")

    left_summary_path = tmp_path / "left-summary.json"
    right_summary_path = tmp_path / "right-summary.json"
    left_summary_path.write_text(
        json.dumps(_summary_payload("left", left_rows_path), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    right_summary_path.write_text(
        json.dumps(_summary_payload("right", right_rows_path), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = analyze_bidirectional_summaries(
        [left_summary_path, right_summary_path],
        tmp_path / "out",
    )

    assert summary["pairCount"] == 1
    pair = summary["pairs"][0]
    assert pair["comparableCount"] == 3
    assert pair["labelDisagreementCount"] == 0
    assert pair["representativeDisagreementCount"] == 0
    assert pair["maxAnchorDistanceDelta"] > 0.0
    assert (tmp_path / "out" / "summary.json").is_file()
