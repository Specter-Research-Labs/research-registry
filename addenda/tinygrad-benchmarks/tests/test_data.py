from __future__ import annotations

from tinygrad_benchmarks.data import curate_private_task_records, curate_rows, split_rows


def _row(seed: int) -> dict[str, object]:
    return {
        "repo_remote": "https://example.com/tinygrad.git",
        "repo_commit": f"{seed:040x}"[:40],
        "task_statement": f"Fix task {seed}",
        "source_refs": [f"issue:#{seed}"],
        "target_paths": [f"tinygrad/task_{seed}.py"],
        "acceptance_command": ["python", "-m", "pytest", f"tests/test_task_{seed}.py"],
        "timeout_seconds": 30,
        "metadata": {
            "quality_score": 72,
            "mined_from_commit": f"{seed:040x}"[:40],
            "commit_subject": f"Fix task {seed} in history",
        },
    }


def test_curate_rows_assigns_deterministic_identifiers() -> None:
    rows_a = curate_rows([_row(1)])
    rows_b = curate_rows([_row(1)])
    assert rows_a[0].item_id == rows_b[0].item_id
    assert rows_a[0].task_id == rows_b[0].task_id
    assert rows_a[0].lane == "cpu_correctness_v0"
    assert rows_a[0].source_refs == ("history:mined",)
    assert rows_a[0].metadata == {"quality_score": 72}


def test_split_rows_is_deterministic_and_nonempty() -> None:
    rows = curate_rows([_row(1), _row(2), _row(3), _row(4), _row(5)])
    public_dev_a, heldout_a = split_rows(rows, seed=7, heldout_fraction=0.4)
    public_dev_b, heldout_b = split_rows(rows, seed=7, heldout_fraction=0.4)
    assert [row.item_id for row in public_dev_a] == [row.item_id for row in public_dev_b]
    assert [row.item_id for row in heldout_a] == [row.item_id for row in heldout_b]
    assert public_dev_a
    assert heldout_a


def test_curate_private_task_records_extracts_gold_fields() -> None:
    record = _row(9)
    record["gold_commit"] = "f" * 40
    record["gold_patch"] = "diff --git a/x b/x\n"
    record["historical_solution_refs"] = ["commit:ffff"]
    private_rows = curate_private_task_records([record])
    assert private_rows[0]["gold_commit"] == "f" * 40
    assert private_rows[0]["gold_patch_sha256"]
    assert private_rows[0]["historical_solution_refs"] == ["commit:ffff"]
    assert private_rows[0]["private_source_refs"] == ["issue:#9"]
    assert private_rows[0]["private_metadata"]["commit_subject"] == "Fix task 9 in history"
