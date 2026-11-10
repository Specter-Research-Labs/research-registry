from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from analysis.logs import ProviderRun
from analysis.postprocess_metrics import PostprocessParams, postprocess_provider_run


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as handle:
        json.dump(payload, handle)


def test_postprocess_provider_run_coq_stdlib_writes_explicit_skip_report(tmp_path: Path) -> None:
    run_dir = tmp_path / "coq-stdlib-run"
    _write_json_gz(run_dir / "summary.json.gz", {"theorems": [], "aggregates": {}})
    _write_json(
        run_dir / "run_config.json",
        {
            "mode": "external",
            "corpus": "coq-stdlib",
            "corpus_meta": {"stdlib_root": "/tmp/coq-stdlib"},
            "theorem_selection": {
                "selected_theorems": ["proj1", "proj2"],
            },
        },
    )

    report = postprocess_provider_run(
        ProviderRun(run_dir=run_dir, provider="coq"),
        params=PostprocessParams(),
    )

    ext = report["external_statement_similarity"]
    assert ext["valid"] is False
    assert ext["problem_count_total"] == 2

    artifact = json.loads((run_dir / "external_statement_similarity.json").read_text())
    notes = artifact.get("validity_notes")
    assert artifact["valid"] is False
    assert isinstance(notes, list)
    assert any("not implemented" in note for note in notes if isinstance(note, str))


def test_postprocess_provider_run_external_unknown_corpus_raises(tmp_path: Path) -> None:
    run_dir = tmp_path / "unknown-external-run"
    _write_json_gz(run_dir / "summary.json.gz", {"theorems": [], "aggregates": {}})
    _write_json(
        run_dir / "run_config.json",
        {
            "mode": "external",
            "corpus": "unknown-corpus",
            "corpus_meta": {},
        },
    )

    with pytest.raises(ValueError, match="unsupported external corpus"):
        postprocess_provider_run(
            ProviderRun(run_dir=run_dir, provider="unknown"),
            params=PostprocessParams(),
        )
