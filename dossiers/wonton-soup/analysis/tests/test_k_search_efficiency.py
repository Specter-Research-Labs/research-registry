from __future__ import annotations

import json

from analysis.postprocess_metrics import compute_k_search_efficiency_from_logs
from prover.goal_cache import GoalCache, GoalEntry, OccurrenceRecord
from prover.goal_signature import GoalSignatureConfig


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_k_search_efficiency_candidate_primary(tmp_path):
    theorem_dir = tmp_path / "thm"
    theorem_dir.mkdir()

    cache = GoalCache(GoalSignatureConfig(scheme="text"))
    cache.mvar_to_sig = {"m1": "sigA", "m2": "sigB"}
    cache.entries["sigA"] = GoalEntry(sig="sigA", type_expr=None, hyp_exprs=[])
    cache.entries["sigA"].occurrences["m1"] = OccurrenceRecord(
        mvar_id="m1",
        outcomes={
            2: [True],   # intro
            4: [False],  # cases
        },
    )
    cache.entries["sigB"] = GoalEntry(sig="sigB", type_expr=None, hyp_exprs=[])
    cache.entries["sigB"].occurrences["m2"] = OccurrenceRecord(
        mvar_id="m2",
        outcomes={
            5: [True],   # closer
            0: [False],  # simplify
        },
    )

    _write_json(
        theorem_dir / "wild_type_mcts_tree.json",
        {
            "root_mvar_id": "m1",
            "expansion_count": 2,
            "nodes": {
                "m1": {
                    "goal_sig": "sigA",
                    "children": {"intro h": ["m2"]},
                },
                "m2": {
                    "goal_sig": "sigB",
                    "children": {"exact hp": []},
                },
            },
        },
    )
    _write_json(
        theorem_dir / "wild_type_history.json",
        {
            "detour_metrics": {"total_attempts": 2},
            "solution_path": [
                {"mvar_id": "m1", "tactic": "intro h"},
                {"mvar_id": "m2", "tactic": "exact hp"},
            ],
            "iterations": [
                {
                    "iteration": 0,
                    "selected_path": ["m1"],
                    "attempts": [
                        {
                            "tactic": "intro h",
                            "outcome": "success",
                            "child_mvar_ids": ["m2"],
                        }
                    ],
                },
                {
                    "iteration": 1,
                    "selected_path": ["m1", "m2"],
                    "attempts": [
                        {
                            "tactic": "exact hp",
                            "outcome": "success",
                            "child_mvar_ids": [],
                        }
                    ],
                },
            ],
        },
    )

    trace_path = theorem_dir / "wild_type_mcts_trace.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event": "iteration",
                        "iteration": 0,
                        "node": {"mvar_id": "m1"},
                        "tactics": [
                            {"tactic": "intro h", "score": 1.0},
                            {"tactic": "cases h", "score": 0.9},
                        ],
                    }
                ),
                "{",
                json.dumps(
                    {
                        "event": "iteration",
                        "iteration": 1,
                        "node": {"mvar_id": "m2"},
                        "tactics": [
                            {"tactic": "exact hp", "score": 1.0},
                            {"tactic": "simp", "score": 0.5},
                        ],
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = compute_k_search_efficiency_from_logs(
        theorem_dir=theorem_dir,
        variant="wild_type",
        goal_cache=cache,
    )
    assert result["valid"] is True
    assert any(str(n).startswith("trace_bad_json_lines:") for n in result.get("validity_notes", []))
    assert result["primary"]["null_model"] == "blind_uniform_candidate"
    assert abs(result["variants"]["any_success"]["blind_uniform_candidate"]["K"] - 0.30103) < 1e-4
    assert (
        abs(result["variants"]["used_operator"]["blind_uniform_candidate"]["K"] - 0.477121)
        < 1e-4
    )


def test_k_search_efficiency_family_fallback_without_trace(tmp_path):
    theorem_dir = tmp_path / "thm"
    theorem_dir.mkdir()

    cache = GoalCache(GoalSignatureConfig(scheme="text"))
    cache.mvar_to_sig = {"m1": "sigA"}
    cache.entries["sigA"] = GoalEntry(sig="sigA", type_expr=None, hyp_exprs=[])
    cache.entries["sigA"].occurrences["m1"] = OccurrenceRecord(
        mvar_id="m1",
        outcomes={
            2: [True],  # intro
            4: [False],  # cases
        },
    )

    _write_json(
        theorem_dir / "wild_type_mcts_tree.json",
        {
            "root_mvar_id": "m1",
            "expansion_count": 1,
            "nodes": {
                "m1": {
                    "goal_sig": "sigA",
                    "children": {"intro h": []},
                },
            },
        },
    )
    _write_json(
        theorem_dir / "wild_type_history.json",
        {
            "detour_metrics": {"total_attempts": 1},
            "solution_path": [
                {"mvar_id": "m1", "tactic": "intro h"},
            ],
            "iterations": [
                {
                    "iteration": 0,
                    "selected_path": ["m1"],
                    "attempts": [
                        {
                            "tactic": "intro h",
                            "outcome": "success",
                            "child_mvar_ids": [],
                        }
                    ],
                },
            ],
        },
    )

    result = compute_k_search_efficiency_from_logs(
        theorem_dir=theorem_dir,
        variant="wild_type",
        goal_cache=cache,
    )
    assert result["valid"] is True
    assert result["primary"]["null_model"] == "blind_uniform_family"
