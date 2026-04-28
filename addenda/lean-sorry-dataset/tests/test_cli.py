from __future__ import annotations

import json
from pathlib import Path

from cli import main
from dataset.index import BuildConfig, BuildStats


def test_build_index_subcommand_writes_rows_and_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out_path = tmp_path / "index.jsonl"

    monkeypatch.setattr("cli.load_snapshot", lambda _: ({}, b"snapshot-bytes"))
    monkeypatch.setattr("cli.extract_sorries", lambda _: [{"raw": True}])

    captured: dict[str, object] = {}

    def fake_build_index_rows(*, sorries: list[dict[str, object]], config: BuildConfig):
        captured["sorries"] = sorries
        captured["config"] = config
        return (
            [{"item_id": "row-1"}],
            BuildStats(
                source_sorries=1,
                rows_written=1,
                rows_invalid=0,
                rows_skipped_non_open_license=0,
                unique_repos=1,
                unique_item_ids=1,
                license_lookup_errors={},
                by_lean_version={"v4.24.0": 1},
                by_license={},
            ),
        )

    monkeypatch.setattr("cli.build_index_rows", fake_build_index_rows)

    exit_code = main(
        [
            "build-index",
            "--snapshot",
            "snapshot.json",
            "--out",
            str(out_path),
            "--include-goal-text",
        ]
    )

    assert exit_code == 0
    assert out_path.read_text(encoding="utf-8") == '{"item_id": "row-1"}\n'
    manifest = json.loads(out_path.with_suffix(".jsonl.manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_snapshot"] == "snapshot.json"
    assert manifest["stats"]["rows_written"] == 1
    assert captured["sorries"] == [{"raw": True}]
    assert captured["config"] == BuildConfig(
        include_goal_text=True,
        resolve_github_license=False,
        require_open_license=False,
        strict=True,
        github_token=None,
    )


def test_license_backfill_subcommand_writes_rows_and_manifest(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    out_path = tmp_path / "index.licensed.jsonl"
    index_path.write_text(
        json.dumps(
            {
                "item_id": "a1",
                "repo_remote": "https://github.com/a/repo-a",
                "repo_slug": "a/repo-a",
                "repo_license_spdx": "MIT",
                "repo_license_url": "https://github.com/a/repo-a",
                "repo_license_open": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "license-backfill",
            "--index",
            str(index_path),
            "--out",
            str(out_path),
        ]
    )

    assert exit_code == 0
    assert load_json_lines(out_path) == load_json_lines(index_path)
    manifest = json.loads(out_path.with_suffix(".jsonl.manifest.json").read_text(encoding="utf-8"))
    assert manifest["stats"] == {
        "rows_input": 1,
        "rows_written": 1,
        "rows_skipped_non_open_license": 0,
        "repos_queried": 0,
        "repos_resolved": 0,
        "repos_with_errors": 0,
        "by_license": {"MIT": 1},
        "license_lookup_errors": {},
    }


def load_json_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
