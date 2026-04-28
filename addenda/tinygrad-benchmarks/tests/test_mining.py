from __future__ import annotations

import subprocess
from pathlib import Path

from tinygrad_benchmarks import mining
from tinygrad_benchmarks.mining import mine_history_candidates


def test_mine_history_candidates_accepts_small_source_plus_test_fix(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], cwd=repo)
    _git(["config", "user.name", "Test User"], cwd=repo)
    _git(["config", "user.email", "test@example.com"], cwd=repo)
    (repo / "tinygrad").mkdir()
    (repo / "tests").mkdir()
    (repo / "tinygrad" / "demo.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    (repo / "tests" / "test_demo.py").write_text(
        "from tinygrad.demo import VALUE\ndef test_value():\n    assert VALUE == 'old'\n",
        encoding="utf-8",
    )
    _git(["add", "tinygrad/demo.py", "tests/test_demo.py"], cwd=repo)
    _git(["commit", "-m", "Base"], cwd=repo)
    parent_commit = _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()
    (repo / "tinygrad" / "demo.py").write_text("VALUE = 'new'\n", encoding="utf-8")
    (repo / "tests" / "test_demo.py").write_text(
        "from tinygrad.demo import VALUE\ndef test_value():\n    assert VALUE == 'new'\n",
        encoding="utf-8",
    )
    _git(["add", "tinygrad/demo.py", "tests/test_demo.py"], cwd=repo)
    _git(["commit", "-m", "Fix demo value (#12)"], cwd=repo)
    gold_commit = _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()
    rows, manifest = mine_history_candidates(
        repo=repo,
        repo_remote="https://example.com/tinygrad.git",
        rev_range="HEAD",
        max_candidates=None,
        max_files=5,
        max_source_files=2,
        max_test_files=2,
        max_patch_lines=50,
        timeout_seconds=45,
        allow_no_tests=False,
    )
    assert manifest["candidate_count"] == 1
    row = rows[0]
    assert row["repo_commit"] == parent_commit
    assert row["gold_commit"] == gold_commit
    assert row["target_paths"] == ["tinygrad/demo.py"]
    assert row["acceptance_command"] == ["python", "-m", "pytest", "tests/test_demo.py"]
    assert row["source_refs"] == ["history:mined"]
    assert row["task_statement"] == "Fix `tinygrad/demo.py` so `tests/test_demo.py` passes."
    assert row["gold_patch"]
    assert row["metadata"]["quality_score"] >= 50
    assert row["metadata"]["review_priority"] == "high"
    assert row["metadata"]["task_statement_style"] == "synthetic_path_test_v1"
    assert manifest["accepted_candidate_count"] == 1


def test_mine_history_candidates_ranks_tested_fix_above_untested_fix(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], cwd=repo)
    _git(["config", "user.name", "Test User"], cwd=repo)
    _git(["config", "user.email", "test@example.com"], cwd=repo)
    (repo / "tinygrad").mkdir()
    (repo / "tests").mkdir()
    (repo / "tinygrad" / "demo.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    (repo / "tests" / "test_demo.py").write_text(
        "from tinygrad.demo import VALUE\ndef test_value():\n    assert VALUE == 'old'\n",
        encoding="utf-8",
    )
    _git(["add", "tinygrad/demo.py", "tests/test_demo.py"], cwd=repo)
    _git(["commit", "-m", "Base"], cwd=repo)
    (repo / "tinygrad" / "demo.py").write_text("VALUE = 'mid'\n", encoding="utf-8")
    _git(["add", "tinygrad/demo.py"], cwd=repo)
    _git(["commit", "-m", "Change demo without tests"], cwd=repo)
    (repo / "tinygrad" / "demo.py").write_text("VALUE = 'new'\n", encoding="utf-8")
    (repo / "tests" / "test_demo.py").write_text(
        "from tinygrad.demo import VALUE\ndef test_value():\n    assert VALUE == 'new'\n",
        encoding="utf-8",
    )
    _git(["add", "tinygrad/demo.py", "tests/test_demo.py"], cwd=repo)
    _git(["commit", "-m", "Fix demo with tests (#55)"], cwd=repo)
    rows, manifest = mine_history_candidates(
        repo=repo,
        repo_remote="https://example.com/tinygrad.git",
        rev_range="HEAD",
        max_candidates=1,
        max_files=5,
        max_source_files=2,
        max_test_files=2,
        max_patch_lines=50,
        timeout_seconds=45,
        allow_no_tests=True,
    )
    assert manifest["accepted_candidate_count"] == 2
    assert len(rows) == 1
    assert rows[0]["source_refs"] == ["history:mined"]
    assert rows[0]["metadata"]["changed_test_paths"] == ["tests/test_demo.py"]


def test_mine_history_candidates_rejects_unsuitable_test_suites(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], cwd=repo)
    _git(["config", "user.name", "Test User"], cwd=repo)
    _git(["config", "user.email", "test@example.com"], cwd=repo)
    (repo / "tinygrad").mkdir()
    (repo / "test").mkdir()
    (repo / "test" / "external").mkdir(parents=True)
    (repo / "tinygrad" / "demo.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    (repo / "test" / "external" / "external_test_demo.py").write_text(
        "def test_demo():\n    assert True\n",
        encoding="utf-8",
    )
    _git(["add", "tinygrad/demo.py", "test/external/external_test_demo.py"], cwd=repo)
    _git(["commit", "-m", "Base"], cwd=repo)
    (repo / "tinygrad" / "demo.py").write_text("VALUE = 'new'\n", encoding="utf-8")
    (repo / "test" / "external" / "external_test_demo.py").write_text(
        "def test_demo():\n    assert False\n",
        encoding="utf-8",
    )
    _git(["add", "tinygrad/demo.py", "test/external/external_test_demo.py"], cwd=repo)
    _git(["commit", "-m", "Fix demo with external test"], cwd=repo)
    rows, manifest = mine_history_candidates(
        repo=repo,
        repo_remote="https://example.com/tinygrad.git",
        rev_range="HEAD",
        max_candidates=None,
        max_files=5,
        max_source_files=2,
        max_test_files=2,
        max_patch_lines=50,
        timeout_seconds=45,
        allow_no_tests=False,
    )
    assert rows == []
    assert manifest["filter_counts"]["no_benchmark_tests"] == 1


def test_mine_history_candidates_skips_git_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], cwd=repo)
    _git(["config", "user.name", "Test User"], cwd=repo)
    _git(["config", "user.email", "test@example.com"], cwd=repo)
    (repo / "tinygrad").mkdir()
    (repo / "tests").mkdir()
    (repo / "tinygrad" / "demo.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    (repo / "tests" / "test_demo.py").write_text(
        "from tinygrad.demo import VALUE\ndef test_value():\n    assert VALUE == 'old'\n",
        encoding="utf-8",
    )
    _git(["add", "tinygrad/demo.py", "tests/test_demo.py"], cwd=repo)
    _git(["commit", "-m", "Base"], cwd=repo)
    (repo / "tinygrad" / "demo.py").write_text("VALUE = 'new'\n", encoding="utf-8")
    (repo / "tests" / "test_demo.py").write_text(
        "from tinygrad.demo import VALUE\ndef test_value():\n    assert VALUE == 'new'\n",
        encoding="utf-8",
    )
    _git(["add", "tinygrad/demo.py", "tests/test_demo.py"], cwd=repo)
    _git(["commit", "-m", "Fix demo value (#12)"], cwd=repo)
    commits = _git(["rev-list", "--reverse", "HEAD"], cwd=repo).stdout.splitlines()
    commit_to_fail = commits[-1]
    original = mining._candidate_from_commit

    def flaky_candidate_from_commit(*args, **kwargs):
        if kwargs["commit"] == commit_to_fail:
            raise subprocess.CalledProcessError(
                returncode=128,
                cmd=["git", "diff", "--numstat"],
                stderr="synthetic failure",
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(mining, "_candidate_from_commit", flaky_candidate_from_commit)
    rows, manifest = mine_history_candidates(
        repo=repo,
        repo_remote="https://example.com/tinygrad.git",
        rev_range="HEAD",
        max_candidates=None,
        max_files=5,
        max_source_files=2,
        max_test_files=2,
        max_patch_lines=50,
        timeout_seconds=45,
        allow_no_tests=False,
    )
    assert rows == []
    assert manifest["filter_counts"]["git_error"] == 1
    assert manifest["error_examples"][0]["commit"] == commit_to_fail
    assert "git diff --numstat" in manifest["error_examples"][0]["command"]


def _git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
