from __future__ import annotations

import json
from pathlib import Path

import pytest

from licenses.backfill import BackfillConfig, backfill_index_rows, load_index_rows


def test_backfill_resolves_missing_license_fields_and_caches_by_repo_slug() -> None:
    rows = [
        {
            "item_id": "a1",
            "repo_remote": "https://github.com/a/repo-a",
            "repo_slug": "a/repo-a",
            "repo_license_spdx": None,
            "repo_license_url": None,
            "repo_license_open": None,
        },
        {
            "item_id": "a2",
            "repo_remote": "https://github.com/a/repo-a",
            "repo_slug": None,
            "repo_license_spdx": None,
            "repo_license_url": None,
            "repo_license_open": None,
        },
        {
            "item_id": "b1",
            "repo_remote": "https://github.com/b/repo-b",
            "repo_slug": "b/repo-b",
            "repo_license_spdx": "Apache-2.0",
            "repo_license_url": "https://github.com/b/repo-b",
            "repo_license_open": True,
        },
    ]

    resolver_calls: list[str] = []

    def fake_resolver(slug: str) -> tuple[str | None, str | None, str | None]:
        resolver_calls.append(slug)
        if slug == "a/repo-a":
            return "MIT", "https://github.com/a/repo-a", None
        raise AssertionError(f"unexpected slug {slug}")

    rows_out, stats = backfill_index_rows(
        rows=rows,
        config=BackfillConfig(require_open_license=False, github_token=None),
        license_resolver=fake_resolver,
    )

    assert len(rows_out) == 3
    assert resolver_calls == ["a/repo-a"]
    assert stats.repos_queried == 1
    assert stats.repos_resolved == 1
    assert stats.rows_skipped_non_open_license == 0
    assert stats.by_license == {"Apache-2.0": 1, "MIT": 2}

    assert rows_out[0]["repo_license_spdx"] == "MIT"
    assert rows_out[0]["repo_license_open"] is True
    assert rows_out[1]["repo_slug"] == "a/repo-a"
    assert rows_out[1]["repo_license_spdx"] == "MIT"
    assert rows_out[1]["repo_license_open"] is True


def test_backfill_require_open_license_drops_non_open_rows() -> None:
    rows = [
        {
            "item_id": "a1",
            "repo_remote": "https://github.com/a/repo-a",
            "repo_slug": "a/repo-a",
            "repo_license_spdx": None,
            "repo_license_url": None,
            "repo_license_open": None,
        },
        {
            "item_id": "c1",
            "repo_remote": "https://github.com/c/repo-c",
            "repo_slug": "c/repo-c",
            "repo_license_spdx": None,
            "repo_license_url": None,
            "repo_license_open": None,
        },
    ]

    def fake_resolver(slug: str) -> tuple[str | None, str | None, str | None]:
        if slug == "a/repo-a":
            return "MIT", "https://github.com/a/repo-a", None
        if slug == "c/repo-c":
            return None, "https://github.com/c/repo-c", "license missing"
        raise AssertionError(f"unexpected slug {slug}")

    rows_out, stats = backfill_index_rows(
        rows=rows,
        config=BackfillConfig(require_open_license=True, github_token=None),
        license_resolver=fake_resolver,
    )

    assert [row["item_id"] for row in rows_out] == ["a1"]
    assert stats.rows_input == 2
    assert stats.rows_written == 1
    assert stats.rows_skipped_non_open_license == 1
    assert stats.repos_queried == 2
    assert stats.repos_resolved == 1
    assert stats.repos_with_errors == 1
    assert stats.by_license == {"MIT": 1}
    assert stats.license_lookup_errors == {"c/repo-c": "license missing"}


def test_load_index_rows_rejects_non_object_lines(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    index_path.write_text(json.dumps([]) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 1: expected JSON object"):
        load_index_rows(index_path)
