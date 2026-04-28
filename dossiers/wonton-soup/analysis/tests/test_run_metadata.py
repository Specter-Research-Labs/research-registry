from __future__ import annotations

import gzip
import json
from pathlib import Path

from analysis.run_metadata import (
    build_run_label,
    build_run_meta,
    load_run_config,
    load_run_snapshot,
    load_run_status,
    load_summary_aggregates,
    providers_from_config,
    selected_theorem_count,
    settings_summary,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)


def test_providers_from_config_prefers_explicit_list() -> None:
    run_config = {
        "providers": ["deepseek", 3, "reprover"],
        "providers_meta": {"names": ["ignored"]},
        "provider": "fallback",
    }

    assert providers_from_config(run_config) == ["deepseek", "reprover"]


def test_settings_summary_formats_budget_and_execution_knobs() -> None:
    run_config = {
        "budget_tiers": [10, "50", 200.0],
        "workers": 4,
        "mcts_mode": "distributed",
        "timeout_sec": 12.5,
        "extra_args": ["--foo", "bar", "--baz", "ignored"],
    }

    assert settings_summary(run_config) == (
        "tiers 10,50,200.0 | wk 4 | mcts distributed | timeout 12.5s | args --foo bar --baz"
    )


def test_build_run_label_formats_dashboard_style() -> None:
    label = build_run_label(
        "run-1",
        {"provider": "deepseek", "corpus": "mathlib", "budget_tiers": [10, 50]},
        {"status": "running"},
        theorem_count=7,
    )

    assert label == "run-1 | deepseek | mathlib | tiers 10,50 | 7 thm | RUNNING"


def test_build_run_label_formats_viz_style() -> None:
    label = build_run_label(
        "run-2",
        {"mode": "research", "corpus": "easy", "budget_tiers": [10], "providers": ["a", "b"]},
        {"partial_results": True},
        theorem_count=3,
        style="viz",
    )

    assert label == "run-2 | research | easy | 3 thm | tiers 10 | 2 providers | PARTIAL"


def test_build_run_meta_merges_summary_config_and_status() -> None:
    meta = build_run_meta(
        {
            "theorem_count": 12,
            "crashed_count": 2,
            "wild_type_solve_rate": 0.75,
            "intervention_solve_rate": 0.5,
        },
        {
            "created_at": "2026-04-06T12:00:00",
            "mode": "research",
            "corpus": "easy",
            "budget_label": "deep",
            "providers": ["deepseek", "reprover"],
            "providers_meta": {"label": "meta label", "names": ["deepseek", "reprover"]},
            "budget_tiers": [10, 50, 200],
            "workers": 8,
        },
        {
            "status": "completed",
            "partial_results": False,
            "goal_id_scheme": "checkpoint",
            "capabilities": {"has_history": True},
        },
        theorem_count=3,
    )

    assert meta == {
        "theorem_count": 3,
        "crashed_count": 2,
        "wild_type_solve_rate": 0.75,
        "intervention_solve_rate": 0.5,
        "created_at": "2026-04-06T12:00:00",
        "mode": "research",
        "corpus": "easy",
        "budget_label": "deep",
        "providers": ["deepseek", "reprover"],
        "provider_label": "meta label",
        "settings_summary": "tiers 10,50,200 | wk 8",
        "status": "completed",
        "partial_results": False,
        "goal_id_scheme": "checkpoint",
        "capabilities": {"has_history": True},
    }


def test_selected_theorem_count_falls_back_to_selected_theorem_names() -> None:
    assert selected_theorem_count({"theorem_selection": {"selected_theorems": ["a", 2, "b"]}}) == 2


def test_run_snapshot_helpers_load_run_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "logs" / "run-a"
    _write_json(
        run_dir / "run_config.json",
        {"run_id": "run-a", "theorem_selection": {"selected_count": 3}},
    )
    _write_json(run_dir / "run_status.json", {"status": "completed"})
    _write_json_gz(run_dir / "summary.json.gz", {"aggregates": {"theorem_count": 3}})

    assert load_run_config(run_dir) == {
        "run_id": "run-a",
        "theorem_selection": {"selected_count": 3},
    }
    assert load_run_status(run_dir) == {"status": "completed"}
    assert load_summary_aggregates(run_dir) == {"theorem_count": 3}
    assert load_run_snapshot(run_dir)._asdict() == {
        "config": {"run_id": "run-a", "theorem_selection": {"selected_count": 3}},
        "status": {"status": "completed"},
        "aggregates": {"theorem_count": 3},
        "theorem_count": 3,
    }
