from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from analysis.export_dashboard import export_run, list_runs


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(payload, f)


def _summary(run_id: str) -> dict[str, object]:
    return {"run_id": run_id, "theorems": [], "aggregates": {}}


def test_list_runs_discovers_nested_provider_runs(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    for provider in ["deepseek", "reprover"]:
        run_dir = logs_root / "capability-root" / "sample=25" / f"provider={provider}"
        _write_json(
            run_dir / "run_config.json",
            {
                "run_id": f"capability-root/sample=25/provider={provider}",
                "backend": "lean",
                "provider": provider,
                "mode": "dev",
            },
        )
        _write_json_gz(
            run_dir / "summary.json.gz",
            _summary(f"capability-root/sample=25/provider={provider}"),
        )

    runs = list_runs(logs_root)
    rels = sorted(run.relative_to(logs_root).as_posix() for run in runs)
    assert rels == [
        "capability-root/sample=25/provider=deepseek",
        "capability-root/sample=25/provider=reprover",
    ]


def test_list_runs_rejects_basin_only_runs(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"

    summary_run = logs_root / "p2-paired" / "provider=deepseek" / "control=centralized"
    _write_json(
        summary_run / "run_config.json",
        {
            "run_id": "p2-paired/provider=deepseek/control=centralized",
            "backend": "lean",
            "provider": "deepseek",
            "mode": "research",
        },
    )
    _write_json_gz(
        summary_run / "summary.json.gz",
        _summary("p2-paired/provider=deepseek/control=centralized"),
    )

    basin_run = logs_root / "p4-basin-deep" / "provider=deepseek" / "seeds=50"
    _write_json(
        basin_run / "run_config.json",
        {
            "run_id": "p4-basin-deep/provider=deepseek/seeds=50",
            "backend": "lean",
            "provider": "deepseek",
            "mode": "research",
            "basin_seeds": 50,
        },
    )
    _write_json(
        basin_run / "t1" / "basin_analysis.json",
        {
            "theorem_name": "t1",
            "seeds": [0],
            "seed_results": [],
            "solve_rate": 0.0,
            "unique_structures": 0,
            "dominant_structure_frequency": 0.0,
            "blind_solve_rate": 0.0,
        },
    )

    with pytest.raises(RuntimeError, match="p4-basin-deep/provider=deepseek/seeds=50"):
        list_runs(logs_root)


def test_export_run_can_skip_file_backed_details(tmp_path: Path) -> None:
    run_dir = tmp_path / "logs" / "lean-matrix" / "deepseek" / "distributed-no-basin"
    _write_json(
        run_dir / "run_config.json",
        {
            "run_id": "lean-matrix/deepseek/distributed-no-basin",
            "backend": "lean",
            "provider": "deepseek",
            "mode": "research",
            "corpus": "mathlib4-valid",
            "goal_sig_scheme": "ast",
            "trace_mcts": True,
        },
    )
    _write_json(
        run_dir / "run_status.json",
        {
            "status": "completed",
            "partial_results": False,
            "goal_id_scheme": "checkpoint",
            "capabilities": {
                "has_proof_term": True,
                "has_proof_term_pretty": True,
                "has_assembly_trace": True,
                "has_proof_term_metrics": True,
            },
        },
    )
    _write_json_gz(
        run_dir / "summary.json.gz",
        {
            "run_id": "lean-matrix/deepseek/distributed-no-basin",
            "theorems": [
                {
                    "name": "t1",
                    "wild_type": {
                        "solved": True,
                        "iterations": 4,
                        "metrics": {
                            "trajectory": {
                                "total_iterations": 4,
                                "max_depth_reached": 2,
                                "backtrack_count": 1,
                                "unique_goals_visited": 3,
                                "tactic_diversity": 2,
                            },
                            "detour": {"failure_ratio": 0.25},
                            "proof_term": {"node_count": 5, "depth": 2, "app_count": 1},
                        },
                    },
                    "interventions": [
                        {
                            "name": "swap_args",
                            "solved": False,
                            "baseline_solved": True,
                            "metrics": {
                                "trajectory": {
                                    "total_iterations": 6,
                                    "max_depth_reached": 3,
                                    "backtrack_count": 2,
                                }
                            },
                            "ged_search_graph": {"value": 2},
                            "ged_proof_graph": {"value": 1},
                            "ged_trace_graph": {"value": 3},
                        }
                    ],
                }
            ],
            "aggregates": {
                "theorem_count": 1,
                "crashed_count": 1,
                "wild_type_solve_rate": 1.0,
                "intervention_count": 1,
                "intervention_solve_rate": 0.0,
                "goal_type_tactic_matrix": {
                    "goal": {"tactic": {"success": 1, "failure": 0, "blocked": 0}}
                },
            },
            "crashed": [
                {
                    "name": "t0",
                    "error": (
                        "REPL returned error messages: "
                        "[{\"severity\":\"error\",\"data\":\"unknown constant Foo\"}]"
                    ),
                    "error_kind": "repl",
                    "error_summary": "unknown constant Foo",
                    "repl_messages": [
                        {"severity": "error", "data": "unknown constant Foo"}
                    ],
                }
            ],
        },
    )
    _write_json(
        run_dir / "t1" / "wild_type_history.json",
        {
            "iterations": [
                {
                    "selected_path": ["a", "b"],
                    "attempts": [{"tactic": "simp", "goal_type": "goal", "outcome": "success"}],
                }
            ]
        },
    )
    _write_json(
        run_dir / "t1" / "ged_matrix.json",
        {"variants": ["wild_type", "swap_args"], "ged_matrix": [[0, 1], [1, 0]]},
    )
    _write_json(
        run_dir / "providers_summary.json",
        {"providers": [{"provider": "deepseek", "theorem_total": 1, "wild_solved": 1}]},
    )

    out_dir = tmp_path / "out"
    entry = export_run(run_dir, out_dir, label=None, include_file_backed_details=False)
    assert entry["id"] == "lean-matrix__deepseek__distributed-no-basin"
    assert entry["label"] == (
        "lean-matrix/deepseek/distributed-no-basin | deepseek | "
        "mathlib4-valid | 1 thm | wild 100.0% | int 0.0%"
    )

    payload = json.loads(
        (out_dir / "data" / entry["id"] / "dashboard_v2.json").read_text(encoding="utf-8")
    )
    assert payload["theorem_count"] == 1
    assert payload["crashed"] == [
        {
            "name": "t0",
            "error": (
                "REPL returned error messages: "
                '[{"severity":"error","data":"unknown constant Foo"}]'
            ),
            "error_kind": "repl",
            "error_summary": "unknown constant Foo",
            "repl_messages": [{"severity": "error", "data": "unknown constant Foo"}],
        }
    ]
    assert payload["overview"]
    assert payload["interventions"]
    assert "trajectory_sample" not in payload
    assert "ged_sample" not in payload
    assert "theorem_details" not in payload
    assert "provider_deep_dive" not in payload
