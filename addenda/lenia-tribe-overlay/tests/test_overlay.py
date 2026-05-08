from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from lenia_tribe_overlay.overlay import LENIA_FEATURE_SPACE, join


def _build_warehouse(path: Path, rows: list[tuple[str, str, float]]) -> None:
    """Create a minimal morphospace.duckdb with just the tables overlay needs."""
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE specimens (specimen_id VARCHAR PRIMARY KEY)")
        con.execute("CREATE TABLE observations (observation_id VARCHAR PRIMARY KEY, specimen_id VARCHAR)")
        con.execute(
            "CREATE TABLE feature_values "
            "(observation_id VARCHAR, axis_id VARCHAR, "
            "feature_space_id VARCHAR, normalized_value DOUBLE)"
        )
        seen_specs: set[str] = set()
        seen_obs: set[str] = set()
        for sid, axis_id, value in rows:
            if sid not in seen_specs:
                con.execute("INSERT INTO specimens VALUES (?)", [sid])
                seen_specs.add(sid)
            obs_id = f"obs-{sid}"
            if obs_id not in seen_obs:
                con.execute("INSERT INTO observations VALUES (?, ?)", [obs_id, sid])
                seen_obs.add(obs_id)
            con.execute(
                "INSERT INTO feature_values VALUES (?, ?, ?, ?)",
                [obs_id, axis_id, LENIA_FEATURE_SPACE, value],
            )
    finally:
        con.close()


def _write_score_report(path: Path, rows: list[dict[str, object]]) -> None:
    payload = {
        "checkpoint_revision": "facebook/tribev2",
        "n_voxels": 20484,
        "source": {"kind": "manifest", "path": "/tmp/m.json"},
        "n_videos": len(rows),
        "timestamp": "2026-05-02T00:00:00+00:00",
        "rois": {
            "sts": {"label_names": ["S_temporal_sup"], "n_vertices": 905},
            "lateral_ot": {"label_names": ["S_oc-temp_lat"], "n_vertices": 597},
            "v1_proxy": {"label_names": ["S_calcarine"], "n_vertices": 844},
        },
        "rows": rows,
    }
    path.write_text(json.dumps(payload))


def test_join_emits_descriptor_axes_and_roi_scores(tmp_path: Path) -> None:
    warehouse = tmp_path / "morphospace.duckdb"
    _build_warehouse(
        warehouse,
        [
            ("spec-1", "spread", 0.5),
            ("spec-1", "compactness", 0.7),
            ("spec-2", "spread", 0.1),
            ("spec-2", "compactness", 0.9),
        ],
    )
    report = tmp_path / "score.json"
    _write_score_report(
        report,
        [
            {
                "name": "creature-a",
                "specimen_id": "spec-1",
                "path": "/x.mp4",
                "notes": None,
                "whole_cortex": 0.05,
                "sts": 0.10,
                "lateral_ot": 0.20,
                "v1_proxy": 0.30,
            },
            {
                "name": "creature-b",
                "specimen_id": "spec-2",
                "path": "/y.mp4",
                "notes": None,
                "whole_cortex": -0.01,
                "sts": -0.02,
                "lateral_ot": 0.01,
                "v1_proxy": 0.04,
            },
        ],
    )
    payload = join(report, warehouse)
    assert payload.n_linked == 2
    assert payload.n_unlinked == 0
    by_name = {row.name: row for row in payload.rows}
    assert by_name["creature-a"].roi_scores == {"sts": 0.10, "lateral_ot": 0.20, "v1_proxy": 0.30}
    assert by_name["creature-a"].descriptor_axes == {"spread": 0.5, "compactness": 0.7}
    assert by_name["creature-b"].descriptor_axes == {"spread": 0.1, "compactness": 0.9}


def test_join_skips_unlinked_rows_and_records_count(tmp_path: Path) -> None:
    warehouse = tmp_path / "morphospace.duckdb"
    _build_warehouse(warehouse, [("spec-1", "spread", 0.5)])
    report = tmp_path / "score.json"
    _write_score_report(
        report,
        [
            {
                "name": "linked",
                "specimen_id": "spec-1",
                "path": "/x.mp4",
                "notes": None,
                "whole_cortex": 0.0,
                "sts": 0.0,
                "lateral_ot": 0.0,
                "v1_proxy": 0.0,
            },
            {
                "name": "showcase",
                "specimen_id": None,
                "path": "/y.mp4",
                "notes": "no warehouse linkage",
                "whole_cortex": 0.0,
                "sts": 0.0,
                "lateral_ot": 0.0,
                "v1_proxy": 0.0,
            },
        ],
    )
    payload = join(report, warehouse)
    assert payload.n_linked == 1
    assert payload.n_unlinked == 1
    assert payload.unlinked_names == ["showcase"]


def test_join_raises_when_specimen_missing_from_warehouse(tmp_path: Path) -> None:
    warehouse = tmp_path / "morphospace.duckdb"
    _build_warehouse(warehouse, [("spec-1", "spread", 0.5)])
    report = tmp_path / "score.json"
    _write_score_report(
        report,
        [
            {
                "name": "missing",
                "specimen_id": "spec-ghost",
                "path": "/x.mp4",
                "notes": None,
                "whole_cortex": 0.0,
                "sts": 0.0,
                "lateral_ot": 0.0,
                "v1_proxy": 0.0,
            }
        ],
    )
    with pytest.raises(KeyError, match="spec-ghost"):
        join(report, warehouse)


def test_join_raises_when_no_specimen_ids(tmp_path: Path) -> None:
    warehouse = tmp_path / "morphospace.duckdb"
    _build_warehouse(warehouse, [("spec-1", "spread", 0.5)])
    report = tmp_path / "score.json"
    _write_score_report(
        report,
        [
            {
                "name": "showcase",
                "specimen_id": None,
                "path": "/x.mp4",
                "notes": None,
                "whole_cortex": 0.0,
                "sts": 0.0,
                "lateral_ot": 0.0,
                "v1_proxy": 0.0,
            }
        ],
    )
    with pytest.raises(ValueError, match="no rows with specimen_id"):
        join(report, warehouse)
