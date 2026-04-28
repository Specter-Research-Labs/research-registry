from __future__ import annotations

import json

from analysis.lake.score_k import compute_k_reference_from_variant
from prover.mcts import TACTIC_FAMILIES


def _write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_k_reference_records_bad_json_lines_in_trace(tmp_path) -> None:
    theorem_dir = tmp_path / "t1"
    theorem_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        theorem_dir / "wild_type_mcts_tree.json",
        {
            "root_mvar_id": "m1",
            "expansion_count": 2,
            "nodes": {
                "m1": {"goal_sig": "sigA", "children": {"intro h": ["m2"]}},
                "m2": {"goal_sig": "sigB", "children": {"exact hp": []}},
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

    (theorem_dir / "wild_type_mcts_trace.jsonl").write_text(
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

    base = {"attempts": [1 for _ in TACTIC_FAMILIES], "successes": [1 for _ in TACTIC_FAMILIES]}
    reference = {"alpha": 1.0, "global": base, "by_sig": {"sigA": base, "sigB": base}}
    goal_cache = {"mvar_to_sig": {"m1": "sigA", "m2": "sigB"}, "entries": {}}

    result = compute_k_reference_from_variant(
        theorem_dir=theorem_dir,
        variant="wild_type",
        goal_cache=goal_cache,
        reference=reference,
    )
    assert result["valid"] is True
    assert any(str(n).startswith("trace_bad_json_lines:") for n in result.get("validity_notes", []))

