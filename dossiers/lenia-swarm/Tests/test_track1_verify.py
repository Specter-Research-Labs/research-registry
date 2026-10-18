from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from lenia_swarm_analysis.morphospace.track1_verify import (
    BUGGY_SHADER,
    CORRECTED_DENOMINATOR,
    CORRECTED_SHADER,
    engine_signature,
    inspect_run,
    orientation_signature,
)


def test_inspect_run_checks_seed_range_exports_and_archive(tmp_path: Path) -> None:
    run_id = "track1b-2c20-harvest-8192-s100"
    run_dir = tmp_path / run_id
    (run_dir / "exports" / "a").mkdir(parents=True)
    (run_dir / "exports" / "b").mkdir()
    (run_dir / "exports" / "index.jsonl").write_text("", encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps({"seedStart": 100, "count": 4, "resultsCount": 4,
                    "collectedCount": 2, "exportedCount": 2}),
        encoding="utf-8",
    )
    (run_dir / "checkpoint.json").write_text(
        json.dumps({"batchSize": 2, "completedBatches": [0, 1], "inputHash": "x"}),
        encoding="utf-8",
    )
    (run_dir / "config.json").write_text("{}", encoding="utf-8")
    (run_dir / "search.json").write_text("{}", encoding="utf-8")
    rows = [
        {"seed": 100 + i, "filters_passed": i % 2 == 0,
         "metrics": {"displacement": 10.0 if i < 2 else 1.0, "heading_rad": math.pi / 4 * i}}
        for i in range(4)
    ]
    results = "".join(json.dumps(row) + "\n" for row in rows).encode()
    (run_dir / "results.jsonl").write_bytes(results)
    archive = tmp_path / "archive"
    archive.mkdir()
    with gzip.open(archive / f"{run_id}.manifest.json.gz", "wt", encoding="utf-8") as handle:
        json.dump({f"{run_id}/results.jsonl": {"sha256": "old"}}, handle)

    row = inspect_run(run_dir, archive_dir=archive)

    assert row["complete"] is True
    assert row["completeness"]["filtersPassed"] == 2
    assert row["provenance"]["resultsSha256"] == hashlib.sha256(results).hexdigest()
    assert row["provenance"]["resultsDifferFromArchive"] is True
    assert row["orientation"]["movers"] == 2
    assert row["orientation"]["nearDiagonalFraction"] == 0.5


def test_inspect_run_flags_missing_seed(tmp_path: Path) -> None:
    run_id = "track1b-3c15-harvest-8192-s0"
    run_dir = tmp_path / run_id
    (run_dir / "exports").mkdir(parents=True)
    (run_dir / "summary.json").write_text(
        json.dumps({"seedStart": 0, "count": 2, "resultsCount": 2,
                    "collectedCount": 0, "exportedCount": 0}),
        encoding="utf-8",
    )
    (run_dir / "checkpoint.json").write_text(
        json.dumps({"batchSize": 2, "completedBatches": [0], "inputHash": "x"}),
        encoding="utf-8",
    )
    (run_dir / "config.json").write_text("{}", encoding="utf-8")
    (run_dir / "search.json").write_text("{}", encoding="utf-8")
    row = {"seed": 0, "metrics": {"displacement": 0.0, "heading_rad": 0.0}}
    (run_dir / "results.jsonl").write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")
    with gzip.open(tmp_path / f"{run_id}.manifest.json.gz", "wt", encoding="utf-8") as handle:
        json.dump({f"{run_id}/results.jsonl": {"sha256": "old"}}, handle)

    assert inspect_run(run_dir, archive_dir=tmp_path)["complete"] is False


def test_orientation_signature_uniform_headings_sit_at_a_quarter() -> None:
    headings = [2 * math.pi * (i + 0.5) / 4096 - math.pi for i in range(4096)]
    signature = orientation_signature(headings)
    assert abs(signature["nearDiagonalFraction"] - 0.25) < 1e-3
    assert abs(signature["meanCos4Theta"]) < 1e-9


def test_engine_signature_classifies_static_shader(tmp_path: Path) -> None:
    corrected = tmp_path / "corrected"
    corrected.write_bytes(b"x" + CORRECTED_SHADER + b"y" + CORRECTED_DENOMINATOR)
    buggy = tmp_path / "buggy"
    buggy.write_bytes(b"x" + BUGGY_SHADER)
    neither = tmp_path / "neither"
    neither.write_bytes(b"x")
    assert engine_signature(corrected)["class"] == "corrected"
    assert engine_signature(buggy)["class"] == "buggy"
    with pytest.raises(SystemExit):
        engine_signature(neither)
