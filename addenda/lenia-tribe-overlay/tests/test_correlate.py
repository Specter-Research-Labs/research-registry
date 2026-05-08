from __future__ import annotations

import json
from pathlib import Path

import pytest

from lenia_tribe_overlay.correlate import correlate


def _write_overlay(
    path: Path,
    rows: list[dict[str, object]],
    rois: list[str] | None = None,
) -> None:
    payload = {
        "feature_space": "lenia_terminal_v1",
        "warehouse": "/tmp/m.duckdb",
        "score_report": "/tmp/s.json",
        "n_linked": len(rows),
        "n_unlinked": 0,
        "unlinked_names": [],
        "rois": rois if rois is not None else ["sts", "v1_proxy"],
        "rows": rows,
    }
    path.write_text(json.dumps(payload))


def _row(
    name: str,
    sts: float,
    v1: float,
    spread: float,
    compactness: float,
) -> dict[str, object]:
    return {
        "name": name,
        "specimen_id": f"spec-{name}",
        "whole_cortex": 0.0,
        "roi_scores": {"sts": sts, "v1_proxy": v1},
        "descriptor_axes": {"spread": spread, "compactness": compactness},
    }


def test_correlate_flags_perfect_correlation_as_redundant(tmp_path: Path) -> None:
    overlay = tmp_path / "ov.json"
    _write_overlay(
        overlay,
        [
            _row("a", sts=0.10, v1=0.5, spread=0.10, compactness=0.9),
            _row("b", sts=0.20, v1=0.5, spread=0.20, compactness=0.7),
            _row("c", sts=0.30, v1=0.5, spread=0.30, compactness=0.5),
            _row("d", sts=0.40, v1=0.5, spread=0.40, compactness=0.3),
        ],
    )
    report = correlate(overlay)
    assert report.n_specimens == 4
    assert report.rois == ["sts", "v1_proxy"]
    assert report.axes == ["compactness", "spread"]

    by_pair = {(c.roi, c.axis): c.pearson_r for c in report.cells}
    assert by_pair[("sts", "spread")] == pytest.approx(1.0)
    assert by_pair[("sts", "compactness")] == pytest.approx(-1.0)
    # v1 is constant so all correlations collapse to 0.0
    assert by_pair[("v1_proxy", "spread")] == 0.0
    assert by_pair[("v1_proxy", "compactness")] == 0.0

    top = report.max_per_roi()
    assert abs(top["sts"].pearson_r) == pytest.approx(1.0)
    assert top["v1_proxy"].pearson_r == 0.0


def test_correlate_returns_zero_for_constant_roi(tmp_path: Path) -> None:
    overlay = tmp_path / "ov.json"
    _write_overlay(
        overlay,
        [
            _row("a", sts=0.5, v1=0.5, spread=0.10, compactness=0.9),
            _row("b", sts=0.5, v1=0.5, spread=0.20, compactness=0.7),
            _row("c", sts=0.5, v1=0.5, spread=0.30, compactness=0.5),
            _row("d", sts=0.5, v1=0.5, spread=0.40, compactness=0.3),
        ],
    )
    report = correlate(overlay)
    for cell in report.cells:
        assert cell.pearson_r == 0.0


def test_correlate_rejects_under_four_rows(tmp_path: Path) -> None:
    overlay = tmp_path / "ov.json"
    _write_overlay(
        overlay,
        [
            _row("a", sts=0.1, v1=0.5, spread=0.10, compactness=0.9),
            _row("b", sts=0.2, v1=0.5, spread=0.20, compactness=0.7),
            _row("c", sts=0.3, v1=0.5, spread=0.30, compactness=0.5),
        ],
    )
    with pytest.raises(ValueError, match="at least 4"):
        correlate(overlay)


def test_correlate_rejects_row_missing_roi(tmp_path: Path) -> None:
    overlay = tmp_path / "ov.json"
    bad_row = _row("a", sts=0.1, v1=0.5, spread=0.1, compactness=0.9)
    bad_row["roi_scores"] = {"sts": 0.1}
    _write_overlay(
        overlay,
        [
            bad_row,
            _row("b", sts=0.2, v1=0.5, spread=0.2, compactness=0.7),
            _row("c", sts=0.3, v1=0.5, spread=0.3, compactness=0.5),
            _row("d", sts=0.4, v1=0.5, spread=0.4, compactness=0.3),
        ],
    )
    with pytest.raises(KeyError, match="v1_proxy"):
        correlate(overlay)


def test_correlate_to_json_roundtrip(tmp_path: Path) -> None:
    overlay = tmp_path / "ov.json"
    _write_overlay(
        overlay,
        [
            _row("a", sts=0.10, v1=0.5, spread=0.10, compactness=0.9),
            _row("b", sts=0.20, v1=0.5, spread=0.20, compactness=0.7),
            _row("c", sts=0.30, v1=0.5, spread=0.30, compactness=0.5),
            _row("d", sts=0.40, v1=0.5, spread=0.40, compactness=0.3),
        ],
    )
    report = correlate(overlay)
    parsed = json.loads(report.to_json())
    assert parsed["n_specimens"] == 4
    assert parsed["rois"] == ["sts", "v1_proxy"]
    assert parsed["axes"] == ["compactness", "spread"]
    assert len(parsed["cells"]) == 4
