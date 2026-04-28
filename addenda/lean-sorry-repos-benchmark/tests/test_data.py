from __future__ import annotations

import json
from pathlib import Path

import pytest

from lean_sorry_repos_benchmark.data import BenchmarkRow, load_rows, select_rows


def _row(
    item_id: str,
    repo_remote: str,
    *,
    goal_bucket: str = "core_easy",
) -> BenchmarkRow:
    return BenchmarkRow(
        item_id=item_id,
        repo_remote=repo_remote,
        repo_commit="abc123",
        repo_lean_version="4.28.0",
        location_path="File.lean",
        location_start_line=1,
        location_start_column=1,
        location_end_line=1,
        location_end_column=6,
        goal_sha256=None,
        goal_text="x : Nat\n⊢ x = x",
        goal_bucket=goal_bucket,
        source_url=f"{repo_remote}/blob/abc/File.lean#L1",
        raw={},
    )


def _index_row(*, location_path: str) -> dict[str, object]:
    return {
        "item_id": "x",
        "repo_remote": "https://github.com/org/repo",
        "repo_commit": "abc123",
        "repo_lean_version": "4.28.0",
        "location_path": location_path,
        "location_start_line": 1,
        "location_start_column": 1,
        "location_end_line": 1,
        "location_end_column": 6,
        "goal_sha256": None,
        "goal_text": "x : Nat\n⊢ x = x",
        "source_url": "https://github.com/org/repo/blob/abc/Main.lean#L1",
    }


@pytest.mark.parametrize(
    ("location_path", "message"),
    [
        ("/tmp/Main.lean", "absolute paths are not allowed"),
        ("C:\\tmp\\Main.lean", "absolute paths are not allowed"),
        ("src/../Main.lean", "parent traversal"),
        ("src//Main.lean", "empty path segments"),
    ],
)
def test_load_rows_rejects_unsafe_location_path(
    tmp_path: Path,
    location_path: str,
    message: str,
) -> None:
    index_path = tmp_path / "index.jsonl"
    payload = json.dumps(_index_row(location_path=location_path)) + "\n"
    index_path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        load_rows(index_path)
    text = str(exc_info.value)
    assert "invalid location_path" in text
    assert message in text


def test_repo_holdout_selection_is_deterministic() -> None:
    rows = [
        _row("a", "https://github.com/org/repo-a"),
        _row("b", "https://github.com/org/repo-b"),
        _row("c", "https://github.com/org/repo-c"),
    ]
    one = select_rows(
        rows,
        split_policy="repo_holdout",
        seed=7,
        repo_holdout_fraction=0.5,
        goal_slice="all",
        max_items=None,
    )
    two = select_rows(
        rows,
        split_policy="repo_holdout",
        seed=7,
        repo_holdout_fraction=0.5,
        goal_slice="all",
        max_items=None,
    )
    assert [row.item_id for row in one] == [row.item_id for row in two]


def test_goal_slice_core_easy_filters_before_selection() -> None:
    rows = [
        _row("easy", "https://github.com/org/repo-a"),
        _row("hard", "https://github.com/org/repo-b", goal_bucket="full"),
    ]
    cases = [
        {"split_policy": "all", "seed": 0, "repo_holdout_fraction": 0.2},
        {"split_policy": "repo_holdout", "seed": 7, "repo_holdout_fraction": 0.999},
    ]
    for case in cases:
        selected = select_rows(rows, goal_slice="core_easy", max_items=None, **case)
        assert [row.item_id for row in selected] == ["easy"]
