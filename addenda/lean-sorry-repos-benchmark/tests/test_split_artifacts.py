from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from lean_sorry_repos_benchmark.cli import main
from lean_sorry_repos_benchmark.data import load_rows
from lean_sorry_repos_benchmark.split_artifacts import (
    SplitConfig,
    build_checksum_manifest,
    build_contamination_report,
    build_split_manifest,
    generate_frozen_split,
)


def _row(
    *,
    item_id: str,
    repo_remote: str,
    goal_text: str,
    goal_sha256: str | None,
    repo_license_open: bool | None = None,
    location_path: str = "File.lean",
    location_start_line: int = 1,
    location_start_column: int = 1,
    location_end_line: int = 1,
    location_end_column: int = 6,
) -> dict[str, Any]:
    row = {
        "item_id": item_id,
        "repo_remote": repo_remote,
        "repo_commit": "abc123",
        "repo_lean_version": "4.28.0",
        "location_path": location_path,
        "location_start_line": location_start_line,
        "location_start_column": location_start_column,
        "location_end_line": location_end_line,
        "location_end_column": location_end_column,
        "goal_sha256": goal_sha256,
        "goal_text": goal_text,
        "source_url": f"{repo_remote}/blob/abc123/File.lean#L1",
    }
    if repo_license_open is not None:
        row["repo_license_open"] = repo_license_open
    return row


def _write_index(index_path: Path, rows: list[dict[str, Any]]) -> None:
    with index_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _split_args(index_path: Path, out_dir: Path, *extra: str) -> list[str]:
    return ["split-artifacts", "--index", str(index_path), "--out-dir", str(out_dir), *extra]


def _run_split(index_path: Path, out_dir: Path, *extra: str) -> int:
    return main(_split_args(index_path, out_dir, *extra))


def _contaminated_rows() -> list[dict[str, Any]]:
    return [
        _row(
            item_id="dev-anchor",
            repo_remote="https://github.com/org/repo-c",
            goal_text="x : Nat\n⊢ x = x",
            goal_sha256="sha-anchor",
        ),
        _row(
            item_id="test-exact",
            repo_remote="https://github.com/org/repo-a",
            goal_text="n : Nat\n⊢ Nat.succ n = Nat.succ n",
            goal_sha256="sha-anchor",
        ),
        _row(
            item_id="test-near",
            repo_remote="https://github.com/org/repo-b",
            goal_text="x : Nat\n⊢ x = x",
            goal_sha256=None,
        ),
        _row(
            item_id="test-clean",
            repo_remote="https://github.com/org/repo-e",
            goal_text="P Q : Prop\n⊢ P → Q → P",
            goal_sha256="sha-clean",
        ),
    ]


def test_frozen_split_cli_outputs_are_deterministic(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    _write_index(
        index_path,
        [
            _row(
                item_id="dev-1",
                repo_remote="https://github.com/org/repo-c",
                goal_text="a b : Nat\n⊢ a + b = b + a",
                goal_sha256="s1",
            ),
            _row(
                item_id="dev-2",
                repo_remote="https://github.com/org/repo-d",
                goal_text="P : Prop\n⊢ P → P",
                goal_sha256="s2",
            ),
            _row(
                item_id="test-1",
                repo_remote="https://github.com/org/repo-a",
                goal_text="x : Int\n⊢ x = x",
                goal_sha256="s3",
            ),
            _row(
                item_id="test-2",
                repo_remote="https://github.com/org/repo-b",
                goal_text="n : Nat\n⊢ n + 0 = n",
                goal_sha256="s4",
            ),
        ],
    )

    out_a = tmp_path / "out-a"
    out_b = tmp_path / "out-b"
    argv = [
        "--seed",
        "7",
        "--repo-holdout-fraction",
        "0.5",
        "--near-dup-jaccard-threshold",
        "0.9",
        "--max-leak-fraction",
        "1.0",
    ]
    assert _run_split(index_path, out_a, *argv) == 0
    assert _run_split(index_path, out_b, *argv) == 0

    for rel in (
        "public_dev.jsonl",
        "heldout_test.jsonl",
        "heldout_test_commitments.json",
        "split_manifest.json",
        "contamination_report.json",
        "artifact_checksums.json",
    ):
        assert (out_a / rel).read_text(encoding="utf-8") == (out_b / rel).read_text(
            encoding="utf-8"
        )


def test_generate_frozen_split_detects_and_drops_contamination(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    _write_index(index_path, _contaminated_rows())
    rows = load_rows(index_path)
    config = SplitConfig(
        seed=7,
        repo_holdout_fraction=0.5,
        near_dup_jaccard_threshold=0.9,
        max_leak_fraction=1.0,
    )
    split = generate_frozen_split(rows, config=config)

    assert [row.item_id for row in split.public_dev] == ["dev-anchor"]
    assert split.heldout_test_before_drop_count == 3
    assert split.dropped_test_item_ids == ["test-exact", "test-near"]
    assert [row.item_id for row in split.heldout_test] == ["test-clean"]
    assert split.leak_fraction == pytest.approx(2 / 3)
    assert len(split.exact_overlaps) == 1
    assert split.exact_overlaps[0].test_item_id == "test-exact"
    assert len(split.near_duplicate_overlaps) == 1
    assert split.near_duplicate_overlaps[0].test_item_id == "test-near"
    assert len(split.char_ngram_overlaps) >= 1

    report = build_contamination_report(
        index_path=index_path,
        source_sha256="source-sha",
        config=config,
        split=split,
    )
    assert report["fractions"] == {
        "leak_fraction": pytest.approx(2 / 3),
        "residual_leak_fraction": 0.0,
    }
    assert report["dropped_test_item_ids"] == ["test-exact", "test-near"]


def test_frozen_split_cli_fails_when_leak_fraction_exceeds_threshold(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir = tmp_path / "out"
    _write_index(index_path, _contaminated_rows())

    with pytest.raises(SystemExit, match="Leak fraction exceeds threshold"):
        main(
            _split_args(
                index_path,
                out_dir,
                "--seed",
                "7",
                "--repo-holdout-fraction",
                "0.5",
                "--near-dup-jaccard-threshold",
                "0.9",
                "--max-leak-fraction",
                "0.1",
            )
        )

    report = _read_json(out_dir / "contamination_report.json")
    assert report["fractions"]["leak_fraction"] > 0.1
    assert (out_dir / "heldout_test.jsonl").exists()


def test_open_only_license_policy_filters_non_open_rows(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir = tmp_path / "out-open"
    _write_index(
        index_path,
        [
            _row(
                item_id="dev-open",
                repo_remote="https://github.com/org/repo-c",
                goal_text="x : Nat\n⊢ x = x",
                goal_sha256="sha-dev-open",
                repo_license_open=True,
            ),
            _row(
                item_id="dev-closed",
                repo_remote="https://github.com/org/repo-d",
                goal_text="x : Nat\n⊢ x = x",
                goal_sha256="sha-dev-closed",
                repo_license_open=False,
            ),
            _row(
                item_id="test-open",
                repo_remote="https://github.com/org/repo-a",
                goal_text="P : Prop\n⊢ P → P",
                goal_sha256="sha-test-open",
                repo_license_open=True,
            ),
            _row(
                item_id="test-unknown",
                repo_remote="https://github.com/org/repo-b",
                goal_text="Q : Prop\n⊢ Q → Q",
                goal_sha256="sha-test-unknown",
            ),
        ],
    )

    assert _run_split(
        index_path,
        out_dir,
        "--seed",
        "7",
        "--repo-holdout-fraction",
        "0.5",
        "--near-dup-jaccard-threshold",
        "1.0",
        "--char-ngram-jaccard-threshold",
        "1.0",
        "--max-leak-fraction",
        "1.0",
        "--license-policy",
        "open_only",
    ) == 0

    assert [row["item_id"] for row in _read_jsonl(out_dir / "public_dev.jsonl")] == [
        "dev-open"
    ]
    assert [row["item_id"] for row in _read_jsonl(out_dir / "heldout_test.jsonl")] == [
        "test-open"
    ]

    manifest = _read_json(out_dir / "split_manifest.json")
    report = _read_json(out_dir / "contamination_report.json")
    assert manifest["config"]["license_policy"] == "open_only"
    assert report["config"]["license_policy"] == "open_only"
    assert manifest["license_counts"] == {
        "policy": "open_only",
        "input_total_rows": 4,
        "input_open_rows": 2,
        "input_non_open_or_unknown_rows": 2,
        "selected_rows_after_policy": 2,
        "excluded_by_policy_rows": 2,
        "selected_open_rows": 2,
        "selected_non_open_or_unknown_rows": 0,
        "public_dev_open_rows": 1,
        "heldout_test_open_rows_before_drop": 1,
        "heldout_test_open_rows_after_drop": 1,
    }


def test_public_release_omits_heldout_content_and_writes_commitments(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    out_dir = tmp_path / "out-public"
    _write_index(
        index_path,
        [
            _row(
                item_id="dev-open",
                repo_remote="https://github.com/org/repo-c",
                goal_text="x : Nat\n⊢ x = x",
                goal_sha256="sha-dev-open",
                repo_license_open=True,
            ),
            _row(
                item_id="test-open",
                repo_remote="https://github.com/org/repo-a",
                goal_text="P : Prop\n⊢ P → P",
                goal_sha256="sha-test-open",
                repo_license_open=True,
            ),
        ],
    )

    assert _run_split(
        index_path,
        out_dir,
        "--seed",
        "7",
        "--repo-holdout-fraction",
        "0.5",
        "--near-dup-jaccard-threshold",
        "1.0",
        "--char-ngram-jaccard-threshold",
        "1.0",
        "--max-leak-fraction",
        "1.0",
        "--release-visibility",
        "public",
    ) == 0

    assert (out_dir / "public_dev.jsonl").exists()
    assert not (out_dir / "heldout_test.jsonl").exists()

    commitments = _read_json(out_dir / "heldout_test_commitments.json")
    assert commitments["heldout_test_rows_after_drop"] == 1
    assert len(commitments["row_sha256"]) == 1

    manifest = _read_json(out_dir / "split_manifest.json")
    assert manifest["release"] == {
        "visibility": "public",
        "includes_heldout_test_content": False,
    }
    assert "heldout_test" not in manifest["row_hashes"]
    assert manifest["counts"]["heldout_test_commitment_count"] == 1

    checksums = _read_json(out_dir / "artifact_checksums.json")
    checksum_files = cast(list[dict[str, object]], checksums["files"])
    checksum_paths = {str(entry["path"]) for entry in checksum_files}
    assert checksum_paths == {
        "contamination_report.json",
        "heldout_test_commitments.json",
        "public_dev.jsonl",
        "split_manifest.json",
    }


def test_char_ngram_signal_detects_additional_contamination(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    _write_index(
        index_path,
        [
            _row(
                item_id="dev-anchor",
                repo_remote="https://github.com/org/repo-c",
                goal_text="a b c d e f g h i j\n⊢ alpha beta gamma",
                goal_sha256=None,
            ),
            _row(
                item_id="test-char",
                repo_remote="https://github.com/org/repo-a",
                goal_text="a b c d e f g h i j\n⊢ alpha beta gamma delta epsilon",
                goal_sha256=None,
            ),
            _row(
                item_id="test-clean",
                repo_remote="https://github.com/org/repo-b",
                goal_text="R S : Prop\n⊢ R → S → R",
                goal_sha256=None,
            ),
        ],
    )
    rows = load_rows(index_path)
    config = SplitConfig(
        seed=7,
        repo_holdout_fraction=0.5,
        near_dup_jaccard_threshold=1.0,
        char_ngram_jaccard_threshold=0.6,
        max_leak_fraction=1.0,
    )
    split = generate_frozen_split(rows, config=config)

    assert [row.item_id for row in split.public_dev] == ["dev-anchor"]
    assert split.dropped_test_item_ids == ["test-char"]
    assert [row.item_id for row in split.heldout_test] == ["test-clean"]
    assert len(split.near_duplicate_overlaps) == 0
    assert len(split.char_ngram_overlaps) == 1
    assert split.char_ngram_overlaps[0].test_item_id == "test-char"

    report = build_contamination_report(
        index_path=index_path,
        source_sha256="source-sha",
        config=config,
        split=split,
    )
    counts = cast(dict[str, object], report["counts"])
    assert counts["char_ngram_pairs"] == 1
    assert counts["near_duplicate_pairs"] == 0


def test_checksum_manifest_uses_sha256_for_generated_files(tmp_path: Path) -> None:
    a_path = tmp_path / "a.txt"
    b_path = tmp_path / "b.txt"
    a_path.write_text("alpha\n", encoding="utf-8")
    b_path.write_text("beta\n", encoding="utf-8")

    manifest = build_checksum_manifest(root_dir=tmp_path, files=[b_path, a_path, a_path])
    assert manifest["schema_version"] == 1
    assert manifest["algorithm"] == "sha256"
    files = cast(list[dict[str, object]], manifest["files"])
    assert [str(entry["path"]) for entry in files] == ["a.txt", "b.txt"]
    assert files[0]["sha256"] == hashlib.sha256(b"alpha\n").hexdigest()
    assert files[1]["sha256"] == hashlib.sha256(b"beta\n").hexdigest()


def test_build_split_manifest_public_hides_heldout_row_hashes(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    _write_index(
        index_path,
        [
            _row(
                item_id="dev-1",
                repo_remote="https://github.com/org/repo-c",
                goal_text="x : Nat\n⊢ x = x",
                goal_sha256="d1",
                repo_license_open=True,
            ),
            _row(
                item_id="test-1",
                repo_remote="https://github.com/org/repo-a",
                goal_text="P : Prop\n⊢ P → P",
                goal_sha256="t1",
                repo_license_open=True,
            ),
        ],
    )
    rows = load_rows(index_path)
    config = SplitConfig(
        seed=7,
        repo_holdout_fraction=0.5,
        near_dup_jaccard_threshold=1.0,
        max_leak_fraction=1.0,
    )
    split = generate_frozen_split(rows, config=config)
    manifest = build_split_manifest(
        index_path=index_path,
        source_sha256="source-sha",
        config=config,
        split=split,
        release_visibility="public",
    )
    row_hashes = cast(dict[str, object], manifest["row_hashes"])
    assert set(row_hashes) == {"public_dev"}
