from __future__ import annotations

import json
from pathlib import Path

from corpus.lean.theorems import Theorem
from orchestrator import lean as runtime
from orchestrator import lean_cli


def test_run_from_args_multi_provider_uses_runtime_selection_for_top_run_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    logs_dir = tmp_path / "logs"
    project_path = tmp_path / "lean_project"
    project_path.mkdir()
    theorem = Theorem("t2", "theorem {name} : True := by trivial")
    selection_calls: list[dict[str, object]] = []
    provider_calls: list[dict[str, object]] = []

    monkeypatch.setattr(runtime, "_assert_lean_project_ready", lambda path: Path(path))
    monkeypatch.setattr(runtime, "resolve_logs_dir", lambda: logs_dir)
    monkeypatch.setattr(
        lean_cli.lean_inputs,
        "load_corpus",
        lambda _corpus: (
            [theorem],
            {"name": "test", "total_theorems": 1},
            {"corpus_id": "lean:test"},
        ),
    )

    def _fake_select_theorems_for_run(
        theorem_corpus,
        *,
        theorem_name,
        corpus_label,
        logger,
        resume,
        log_dir,
        corpus,
        offset,
        limit,
        sample,
        seed,
    ):
        selection_calls.append(
            {
                "theorem_names": [item.name for item in theorem_corpus],
                "theorem_name": theorem_name,
                "corpus_label": corpus_label,
                "resume": resume,
                "log_dir": log_dir,
                "corpus": corpus,
                "offset": offset,
                "limit": limit,
                "sample": sample,
                "seed": seed,
            }
        )
        return [theorem], None, "resume_saved_selection", 123

    monkeypatch.setattr(runtime, "_select_theorems_for_run", _fake_select_theorems_for_run)
    async def _fake_run_corpus(*args, **kwargs):
        provider_calls.append(kwargs)
        provider_dir = logs_dir / kwargs["run_id"]
        provider_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(runtime, "run_corpus", _fake_run_corpus)
    monkeypatch.setattr(
        lean_cli._lean_reporting,
        "_load_summary",
        lambda _path: {
            "aggregates": {
                "run_stats": {
                    "theorem_total": 1,
                    "crashed": 0,
                    "wild_solved": 1,
                    "wild_aborted": 0,
                    "intervention_total": 0,
                    "intervention_solved": 0,
                    "avg_iters": 1,
                }
            }
        },
    )
    monkeypatch.setattr(
        lean_cli._lean_reporting,
        "_summarize_from_summary",
        lambda summary: summary["aggregates"]["run_stats"],
    )
    monkeypatch.setattr(
        lean_cli._lean_reporting,
        "_build_providers_theorem_summary",
        lambda *_args, **_kwargs: {"providers": [], "theorems": []},
    )
    monkeypatch.setattr(
        lean_cli._lean_reporting,
        "_format_multi_provider_summary",
        lambda *_args, **_kwargs: "summary",
    )
    monkeypatch.setattr(runtime, "_sync_run_dir_to_remote", lambda **_kwargs: None)
    monkeypatch.setattr(runtime, "_cleanup_torch_memory", lambda: None)

    args = lean_cli._build_parser().parse_args(
        [
            "--lean-project",
            str(project_path),
            "--providers",
            "reprover,deepseek",
            "--deepseek-backend",
            "transformers",
            "--baseline-solved-only",
            "--run-id",
            "corpus-multi",
            "--resume",
        ]
    )
    lean_cli.run_from_args(args)

    top_log_dir = logs_dir / "corpus-multi"
    run_config = json.loads((top_log_dir / "run_config.json").read_text(encoding="utf-8"))

    assert selection_calls == [
        {
            "theorem_names": ["t2"],
            "theorem_name": None,
            "corpus_label": "test",
            "resume": True,
            "log_dir": top_log_dir,
            "corpus": "easy",
            "offset": 0,
            "limit": 5,
            "sample": None,
            "seed": None,
        }
    ]
    assert run_config["theorem_selection"] == {
        "method": "resume_saved_selection",
        "limit": 5,
        "offset": 0,
        "sample": None,
        "selection_seed": 123,
        "seed": 123,
        "selected_count": 1,
        "selected_theorems": ["t2"],
        "error": None,
    }
    assert run_config["providers"] == ["reprover", "deepseek"]
    assert run_config["mcts_expansion_policy"] == "all-successes"
    assert run_config["mcts"]["expansion_policy"] == "all-successes"
    assert run_config["skip_interventions_after_wild_failure"] is True
    assert run_config["resolved"]["mcts_expansion_policy"] == "all-successes"
    assert run_config["resolved"]["skip_interventions_after_wild_failure"] is True
    assert run_config["providers_meta"] == {
        "names": ["reprover", "deepseek"],
        "multi_provider": True,
    }
    assert len(provider_calls) == 2
    assert provider_calls[0]["provider_name"] == "reprover"
    assert provider_calls[1]["provider_name"] == "deepseek"
    assert provider_calls[0]["expansion_policy"] == "all-successes"
    assert provider_calls[1]["expansion_policy"] == "all-successes"
    assert provider_calls[0]["skip_interventions_after_wild_failure"] is True
    assert provider_calls[1]["skip_interventions_after_wild_failure"] is True
    assert provider_calls[1]["deepseek_backend"] == "transformers"
