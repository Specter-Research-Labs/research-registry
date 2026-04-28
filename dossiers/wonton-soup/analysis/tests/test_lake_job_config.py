from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.lake.job_config import load_job_config


def test_job_config_round_trip_preserves_payload_shape(tmp_path: Path) -> None:
    payload = {
        "schema_version": 2,
        "name": "typed_job",
        "selection": {
            "provider": ["reprover"],
            "require_completed": True,
            "dedupe_run_id": False,
            "same_method_as": {"run_id": "corpus-1"},
            "custom_note": "kept",
        },
        "reference": {
            "selection": {"provider": ["reprover"]},
            "build_outcomes": {"alpha": 1.0, "meta": {}},
            "ref_id": "ref-123",
            "score_k": True,
        },
        "datasets": [
            {
                "name": "runs",
                "query": "SELECT * FROM selected_runs ORDER BY run_key",
                "generator": None,
                "format": "jsonl",
                "file": None,
            }
        ],
    }
    path = tmp_path / "job.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    job = load_job_config(path)

    assert job["selection"] == payload["selection"]
    assert job["reference"] == payload["reference"]
    assert job == payload
    assert job["datasets"][0] == payload["datasets"][0]


def test_job_config_rejects_empty_reference_selection_for_build_outcomes(tmp_path: Path) -> None:
    path = tmp_path / "job.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "name": "broken_job",
                "selection": {},
                "reference": {"build_outcomes": {"alpha": 1.0}, "selection": {}},
                "datasets": [
                    {
                        "name": "runs",
                        "query": "SELECT * FROM selected_runs ORDER BY run_key",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=(
            "reference.selection must be a non-empty object "
            "when reference.build_outcomes is set"
        ),
    ):
        load_job_config(path)
