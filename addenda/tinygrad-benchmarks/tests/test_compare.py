from __future__ import annotations

from tinygrad_benchmarks.compare import compare_attempts_to_gold


def test_compare_attempts_to_gold_detects_exact_match() -> None:
    attempts = [
        {
            "item_id": "item-1",
            "task_id": "task-1",
            "candidate_id": "cand-1",
            "success": True,
            "error_kind": "none",
            "patch_sha256": "abc",
            "patch_touched_paths": ["tinygrad/demo.py"],
            "normalized_changed_lines": ["+:VALUE = 'new'"],
        },
        {
            "item_id": "item-2",
            "task_id": "task-2",
            "candidate_id": "cand-2",
            "success": False,
            "error_kind": "acceptance_failed",
            "patch_sha256": "def",
            "patch_touched_paths": ["tinygrad/other.py"],
            "normalized_changed_lines": ["+:OTHER = 2"],
        },
    ]
    private_rows = [
        {
            "item_id": "item-1",
            "task_id": "task-1",
            "gold_commit": "1" * 40,
            "gold_patch_sha256": "abc",
            "historical_solution_refs": ["commit:1111"],
        },
        {
            "item_id": "item-2",
            "task_id": "task-2",
            "gold_commit": "2" * 40,
            "gold_patch_sha256": "zzz",
        },
    ]
    report_rows, summary = compare_attempts_to_gold(attempts, private_rows)
    assert report_rows[0]["exact_gold_patch_match"] is True
    assert report_rows[0]["close_gold_match"] is True
    assert report_rows[0]["category"] == "success_exact_gold"
    assert report_rows[1]["category"] == "failure_nonexact"
    assert summary["item_exact_gold_match_count"] == 1
    assert summary["item_success_exact_gold_count"] == 1


def test_compare_attempts_to_gold_detects_close_match() -> None:
    attempts = [
        {
            "item_id": "item-1",
            "task_id": "task-1",
            "candidate_id": "cand-1",
            "success": True,
            "error_kind": "none",
            "patch_sha256": "abc",
            "patch_touched_paths": ["tinygrad/demo.py"],
            "normalized_changed_lines": ["+:VALUE = 'new'"],
        }
    ]
    private_rows = [
        {
            "item_id": "item-1",
            "task_id": "task-1",
            "gold_commit": "1" * 40,
            "gold_patch": (
                "diff --git a/tinygrad/demo.py b/tinygrad/demo.py\n"
                "--- a/tinygrad/demo.py\n"
                "+++ b/tinygrad/demo.py\n"
                "@@ -1 +1 @@\n"
                "-VALUE = 'old'\n"
                "+VALUE = 'new'\n"
            ),
        }
    ]
    report_rows, summary = compare_attempts_to_gold(attempts, private_rows)
    assert report_rows[0]["exact_gold_patch_match"] is False
    assert report_rows[0]["close_gold_match"] is True
    assert report_rows[0]["category"] == "success_close_gold"
    assert summary["attempt_close_gold_match_count"] == 1
