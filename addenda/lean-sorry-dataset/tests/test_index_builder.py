from __future__ import annotations

from dataset.index import BuildConfig, build_index_rows


def _row(
    *,
    remote: str,
    branch: str,
    commit: str,
    lean_version: str,
    path: str,
    start_line: int,
    start_column: int,
    end_line: int,
    end_column: int,
    goal: str,
) -> dict:
    return {
        "repo": {
            "remote": remote,
            "branch": branch,
            "commit": commit,
            "lean_version": lean_version,
        },
        "location": {
            "path": path,
            "start_line": start_line,
            "start_column": start_column,
            "end_line": end_line,
            "end_column": end_column,
        },
        "debug_info": {
            "goal": goal,
            "url": f"{remote}/blob/{commit}/{path}#L{start_line}",
        },
        "metadata": {
            "blame_email_hash": "h1",
            "blame_date": "2025-01-01T00:00:00+00:00",
            "inclusion_date": "2025-01-02T00:00:00+00:00",
        },
    }


def test_build_index_rows_is_deterministic() -> None:
    sorries = [
        _row(
            remote="https://github.com/b/repo-b",
            branch="main",
            commit="c2",
            lean_version="v4.24.0",
            path="B.lean",
            start_line=4,
            start_column=2,
            end_line=4,
            end_column=7,
            goal="goal-b",
        ),
        _row(
            remote="https://github.com/a/repo-a",
            branch="main",
            commit="c1",
            lean_version="v4.23.0",
            path="A.lean",
            start_line=3,
            start_column=1,
            end_line=3,
            end_column=6,
            goal="goal-a",
        ),
    ]

    config = BuildConfig(
        include_goal_text=False,
        resolve_github_license=False,
        require_open_license=False,
        strict=True,
        github_token=None,
    )
    rows_a, stats_a = build_index_rows(sorries=sorries, config=config)
    rows_b, stats_b = build_index_rows(sorries=sorries, config=config)

    assert rows_a == rows_b
    assert stats_a == stats_b
    assert rows_a[0]["repo_remote"] == "https://github.com/a/repo-a"
    assert rows_a[0]["goal_text"] is None
    assert rows_a[0]["goal_sha256"] is not None


def test_build_index_rows_requires_open_license_when_configured() -> None:
    sorries = [
        _row(
            remote="https://github.com/a/open-repo",
            branch="main",
            commit="c1",
            lean_version="v4.23.0",
            path="A.lean",
            start_line=3,
            start_column=1,
            end_line=3,
            end_column=6,
            goal="goal-a",
        ),
        _row(
            remote="https://github.com/a/unknown-repo",
            branch="main",
            commit="c2",
            lean_version="v4.23.0",
            path="B.lean",
            start_line=4,
            start_column=2,
            end_line=4,
            end_column=7,
            goal="goal-b",
        ),
    ]

    def fake_resolver(slug: str) -> tuple[str | None, str | None, str | None]:
        if slug == "a/open-repo":
            return "MIT", "https://github.com/a/open-repo", None
        return None, "https://github.com/a/unknown-repo", "license missing"

    config = BuildConfig(
        include_goal_text=False,
        resolve_github_license=True,
        require_open_license=True,
        strict=True,
        github_token=None,
    )
    rows, stats = build_index_rows(
        sorries=sorries,
        config=config,
        license_resolver=fake_resolver,
    )
    assert len(rows) == 1
    assert rows[0]["repo_slug"] == "a/open-repo"
    assert stats.rows_skipped_non_open_license == 1
    assert stats.by_license == {"MIT": 1}

