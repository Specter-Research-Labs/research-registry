import gzip
import json
from pathlib import Path

from analysis.export_learning_dataset import export_learning_dataset


def test_export_learning_dataset_smoke(tmp_path: Path) -> None:
    run_dir = tmp_path / "corpus-2000-01-01-000000"
    run_dir.mkdir(parents=True)
    run_config = {
        "run_id": "corpus-2000-01-01-000000",
        "provider": "heuristic",
        "provider_label": "heuristic",
    }
    (run_dir / "run_config.json").write_text(json.dumps(run_config))
    goal_cache = {
        "sig_scheme": "ast",
        "sig_stats": {"ast_missing": 0},
        "mvar_to_sig": {"cp1:root": "sig_root", "cp2:child": "sig_child"},
        "entries": {
            "sig_root": {
                "sig": "sig_root",
                "type_expr": None,
                "hyp_exprs": [],
                "occurrences": {},
            },
            "sig_child": {
                "sig": "sig_child",
                "type_expr": None,
                "hyp_exprs": [],
                "occurrences": {},
            },
        },
    }
    with gzip.open(run_dir / "goal_cache.json.gz", "wt") as f:
        json.dump(goal_cache, f)

    theorem_dir = run_dir / "theorem1"
    theorem_dir.mkdir()
    tree = {
        "root_mvar_id": "cp1:root",
        "expansion_count": 1,
        "nodes": {
            "cp1:root": {
                "mvar_id": "cp1:root",
                "goal_type": "P",
                "goal_sig": "sig_root",
                "goal_sig_strict": "strict_root",
                "visit_count": 1,
                "success_count": 0,
                "is_terminal": False,
                "is_dead": False,
                "depth": 0,
                "expansion_order": 1,
                "children": {"intro": ["cp2:child"]},
            },
            "cp2:child": {
                "mvar_id": "cp2:child",
                "goal_type": "Q",
                "goal_sig": "sig_child",
                "goal_sig_strict": "strict_child",
                "visit_count": 0,
                "success_count": 0,
                "is_terminal": False,
                "is_dead": False,
                "depth": 1,
                "expansion_order": 1,
                "children": {},
            },
        },
    }
    (theorem_dir / "wild_type_mcts_tree.json").write_text(json.dumps(tree))
    (theorem_dir / "wild_type_history.json").write_text(
        json.dumps({"solution_path": [{"mvar_id": "cp1:root", "tactic": "intro"}]})
    )
    trace_record = {
        "event": "iteration",
        "tier": 0,
        "budget": 10,
        "iteration": 0,
        "node": {
            "mvar_id": "cp1:root",
            "goal_type": "P",
            "goal_sig": "sig_root",
            "goal_sig_strict": "strict_root",
            "visit_count": 1,
            "success_count": 0,
            "is_terminal": False,
            "is_dead": False,
            "depth": 0,
        },
        "tactics": [{"tactic": "intro", "score": 0.9}],
        "attempts": [
            {
                "tactic": "intro",
                "outcome": "success",
                "child_mvar_ids": ["cp2:child"],
                "timestamp_ms": 1,
                "tactic_norm": "intro",
                "goal_sig": "sig_root",
                "goal_sig_strict": "strict_root",
                "goal_type": "P",
                "peg_id": None,
                "peg_kind": None,
                "block_reason": None,
                "provider_id": None,
            }
        ],
        "expanded": True,
        "terminal_reached": False,
        "backprop_success": True,
        "tree": {"nodes": 2, "expansions": 1, "max_depth": 1, "solved": False, "aborted": False},
        "selected_path": ["cp1:root"],
        "reason": "expanded",
    }
    (theorem_dir / "wild_type_mcts_trace.jsonl").write_text(json.dumps(trace_record) + "\n")
    # AppleDouble sidecar files can appear on mounted macOS volumes; they must be ignored.
    (theorem_dir / "._wild_type_mcts_trace.jsonl").write_bytes(b"\x00\x01\x02not-json")

    out_root = tmp_path / "out"
    results = export_learning_dataset(run_dir, out_root, overwrite=True)
    assert len(results) == 1
    dataset_path = results[0].dataset_path
    assert dataset_path.exists()

    with gzip.open(dataset_path, "rt") as f:
        line = f.readline().strip()
    row = json.loads(line)
    assert row["theorem"] == "theorem1"
    assert row["variant"] == "wild_type"
    assert row["tactic"] == "intro"
    assert row["committed"] is True
    assert row["variant_solved"] is True
    assert row["node_on_solution_path"] is True
