from __future__ import annotations

import importlib.util
import gzip
import json
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "analysis" / "lab_server.py"
_SPEC = importlib.util.spec_from_file_location("wonton_lab_server_test", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_LAB_SERVER = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _LAB_SERVER
_SPEC.loader.exec_module(_LAB_SERVER)

LabApp = _LAB_SERVER.LabApp
LabContext = _LAB_SERVER.LabContext
_intervention_behavior_counts = _LAB_SERVER._intervention_behavior_counts
_variant_index = _LAB_SERVER._variant_index


def _context(root: Path) -> LabContext:
    return LabContext(
        logs_dir=root / "logs",
        artifacts_dir=root / "artifacts",
        state_dir=root / "state",
        static_dir=root / "static",
        fonts_dir=root / "fonts",
        lake_db_path=root / "artifacts" / "lake.duckdb",
        lake_exports_dir=root / "artifacts" / "exports",
        lake_jobs_dir=root / "artifacts" / "jobs",
        notebook_html=root / "notebooks" / "deep_analysis.html",
        presets_dir=root / "presets",
    )


def _write_summary(run_dir: Path, theorem: str, *, wild_solved: bool, recovered: bool) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    theorem_dir = run_dir / theorem
    theorem_dir.mkdir()
    (theorem_dir / "wild_type_graph.json").write_text(
        json.dumps(
            {
                "nodes": [{"id": "root", "depth": 0, "goal_sig": theorem, "is_terminal": wild_solved}],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    payload = {
        "run_id": run_dir.name,
        "theorems": [
            {
                "name": theorem,
                "wild_type": {"solved": wild_solved, "iterations": 2},
                "interventions": [
                    {
                        "name": "block_intro",
                        "solved": recovered,
                        "baseline_solved": True,
                        "hash_mismatch": recovered,
                        "ged_search_graph": {"normalized": 0.5},
                    }
                ],
            }
        ],
    }
    with gzip.open(run_dir / "summary.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)


def test_variant_index_groups_files(tmp_path: Path) -> None:
    theorem_dir = tmp_path / "run" / "example_thm"
    theorem_dir.mkdir(parents=True)
    for name in [
        "wild_type_graph.json",
        "wild_type_history.json",
        "wild_type_mcts_trace.jsonl",
        "wild_type_metrics.json",
        "block_exact_graph.json",
        "block_exact_comparison.json",
        "ged_matrix.json",
        "basin_analysis.json",
    ]:
        (theorem_dir / name).write_text("{}", encoding="utf-8")

    index = _variant_index(theorem_dir)

    assert index["variants"] == ["wild_type", "block_exact"]
    assert index["variant_files"]["wild_type"]["graph"] == "wild_type_graph.json"
    assert index["variant_files"]["wild_type"]["mcts_trace"] == "wild_type_mcts_trace.jsonl"
    assert index["variant_files"]["block_exact"]["comparison"] == "block_exact_comparison.json"
    assert index["extra_files"]["ged_matrix"] == "ged_matrix.json"
    assert index["extra_files"]["basin_analysis"] == "basin_analysis.json"


def test_intervention_behavior_counts_tracks_outcomes() -> None:
    payload = _intervention_behavior_counts(
        [
            {
                "interventions": [
                    {"solved": True, "baseline_solved": False},
                    {"solved": True, "baseline_solved": True},
                    {"solved": False, "baseline_solved": True},
                    {"solved": False, "baseline_solved": False, "is_control": True},
                ]
            }
        ]
    )

    assert payload["counts"] == {
        "total": 4,
        "controls": 1,
        "rescued": 1,
        "preserved": 1,
        "degraded": 1,
        "inert": 1,
        "solved": 2,
        "failed": 2,
    }
    assert payload["rates"]["rescued"] == 0.25
    assert payload["rates"]["degraded"] == 0.25


def test_build_lean_run_command_adds_selected_flags(tmp_path: Path) -> None:
    app = LabApp(_context(tmp_path))

    argv = app._build_lean_command(
        {
            "mode": "dev",
            "corpus": "easy",
            "provider": "reprover",
            "limit": 5,
            "sample": 3,
            "seed": 11,
            "workers": 2,
            "theorem": "logic_chain",
            "run_id": "custom-run",
            "with_interventions": True,
            "trace_mcts": False,
            "analysis": True,
        },
        basin=False,
    )

    assert argv[:6] == ["uv", "run", "python", "wonton.py", "lean", "run"]
    assert "--agent" in argv
    assert "--plain" in argv
    assert "--with-interventions" in argv
    assert "--no-trace-mcts" in argv
    assert "--analysis" in argv
    assert argv[argv.index("--provider") + 1] == "reprover"
    assert argv[argv.index("--run-id") + 1] == "custom-run"


def test_build_lean_basin_command_requires_seeds_and_blind(tmp_path: Path) -> None:
    app = LabApp(_context(tmp_path))

    argv = app._build_lean_command(
        {
            "seeds": 6,
            "mode": "dev",
            "blind": True,
            "trace_mcts": True,
        },
        basin=True,
    )

    assert argv[:6] == ["uv", "run", "python", "wonton.py", "lean", "basin"]
    assert "--seeds" in argv
    assert argv[argv.index("--seeds") + 1] == "6"
    assert "--blind" in argv
    assert "--trace-mcts" in argv


def test_build_causal_contrast_command_uses_experiment_module(tmp_path: Path) -> None:
    app = LabApp(_context(tmp_path))

    argv = app._build_causal_contrast_command(
        {
            "providers": "heuristic",
            "corpus": "easy",
            "budget": "quick",
            "limit": 2,
            "seed": 17,
            "workers": 1,
            "run_id": "contrast-smoke",
            "mcts_agents": 3,
            "mcts_expansion_policy": "first-success",
            "mcts_inflight": 8,
            "mcts_virtual_loss": 1,
            "mcts_block_fraction": 0.3,
            "mcts_block_duration": 4,
            "mcts_block_seed": 19,
            "mcts_reroute_max": 3,
            "with_interventions": True,
            "trace_mcts": True,
            "no_sync": True,
        }
    )

    assert argv[:5] == ["uv", "run", "python", "-m", "experiments.causal_contrast.run"]
    assert "--providers" in argv
    assert argv[argv.index("--providers") + 1] == "heuristic"
    assert "--mcts-agents" in argv
    assert argv[argv.index("--mcts-agents") + 1] == "3"
    assert "--mcts-expansion-policy" in argv
    assert argv[argv.index("--mcts-expansion-policy") + 1] == "first-success"
    assert "--mcts-block-fraction" in argv
    assert argv[argv.index("--mcts-block-fraction") + 1] == "0.3"
    assert "--mcts-reroute-max" in argv
    assert argv[argv.index("--mcts-reroute-max") + 1] == "3"
    assert "--with-interventions" in argv
    assert "--trace-mcts" in argv
    assert "--no-sync" in argv

    full_corpus_argv = app._build_causal_contrast_command({"limit": ""})
    assert "--limit" not in full_corpus_argv


def test_lab_discovers_paired_contrast_summary(tmp_path: Path) -> None:
    from experiments.causal_contrast.summary import build_paired_contrast_summary

    logs_dir = tmp_path / "logs"
    root = logs_dir / "2026-06-02-contrast"
    central = root / "provider=heuristic" / "mcts=centralized"
    distributed = root / "provider=heuristic" / "mcts=distributed"
    _write_summary(central, "and_intro", wild_solved=True, recovered=False)
    _write_summary(distributed, "and_intro", wild_solved=True, recovered=True)
    payload = build_paired_contrast_summary(
        root_dir=root,
        logs_dir=logs_dir,
        run_id="2026-06-02-contrast",
        providers=["heuristic"],
        run_dirs={"heuristic": {"centralized": central, "distributed": distributed}},
        experiment={"corpus": "easy", "budget": "quick"},
    )
    assert payload["providers"][0]["delta"]["recovery_rate"] == 1.0

    context = _context(tmp_path)
    app = LabApp(
        LabContext(
            logs_dir=logs_dir,
            artifacts_dir=context.artifacts_dir,
            state_dir=context.state_dir,
            static_dir=context.static_dir,
            fonts_dir=context.fonts_dir,
            lake_db_path=context.lake_db_path,
            lake_exports_dir=context.lake_exports_dir,
            lake_jobs_dir=context.lake_jobs_dir,
            notebook_html=context.notebook_html,
            presets_dir=context.presets_dir,
        )
    )

    rows = app.list_contrasts()
    assert rows[0]["rel_dir"] == "2026-06-02-contrast"
    loaded = app.load_contrast("2026-06-02-contrast")
    assert loaded["theorem_pairs"][0]["common_variants"] == ["wild_type"]
