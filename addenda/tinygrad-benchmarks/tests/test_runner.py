from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tinygrad_benchmarks.data import curate_rows, curate_submissions
from tinygrad_benchmarks.runner import run_submissions


def test_run_submissions_applies_patch_and_hides_git_history(tmp_path: Path) -> None:
    repo_path, base_commit, patch = _make_repo(tmp_path)
    rows = curate_rows(
        [
            {
                "repo_remote": "https://example.com/tinygrad.git",
                "repo_commit": base_commit,
                "task_statement": "Update the message payload",
                "source_refs": ["history:mined"],
                "target_paths": ["message.txt"],
                "acceptance_command": [sys.executable, "check.py"],
                "timeout_seconds": 5,
            }
        ]
    )
    submissions = curate_submissions([{"item_id": rows[0].item_id, "patch": patch}])
    attempts, summary, manifest = run_submissions(
        rows=rows,
        submissions=submissions,
        out_dir=tmp_path / "artifacts",
        runtime_dir=tmp_path / "runtime",
        index_path=_write_stub(tmp_path / "index.jsonl"),
        submissions_path=_write_stub(tmp_path / "submissions.jsonl"),
        repo_map={"https://example.com/tinygrad.git": str(repo_path)},
    )
    assert attempts[0]["success"] is True
    assert attempts[0]["workspace_has_git_metadata"] is False
    assert attempts[0]["patch_touched_paths"] == ["message.txt"]
    assert not Path(attempts[0]["workspace"], ".git").exists()
    assert summary["success_count"] == 1
    assert Path(manifest["summary_path"]).is_file()


def test_run_submissions_reports_patch_failure(tmp_path: Path) -> None:
    repo_path, base_commit, _patch = _make_repo(tmp_path)
    rows = curate_rows(
        [
            {
                "repo_remote": "https://example.com/tinygrad.git",
                "repo_commit": base_commit,
                "task_statement": "Update the message payload",
                "source_refs": ["history:mined"],
                "target_paths": ["message.txt"],
                "acceptance_command": [sys.executable, "check.py"],
                "timeout_seconds": 5,
            }
        ]
    )
    submissions = curate_submissions(
        [{"item_id": rows[0].item_id, "patch": "--- a/missing.txt\n+++ b/missing.txt\n"}]
    )
    attempts, summary, _manifest = run_submissions(
        rows=rows,
        submissions=submissions,
        out_dir=tmp_path / "artifacts",
        runtime_dir=tmp_path / "runtime",
        index_path=_write_stub(tmp_path / "index.jsonl"),
        submissions_path=_write_stub(tmp_path / "submissions.jsonl"),
        repo_map={"https://example.com/tinygrad.git": str(repo_path)},
    )
    assert attempts[0]["success"] is False
    assert attempts[0]["error_kind"] == "patch_check_failed"
    assert summary["apply_failure_count"] == 1


def _make_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo_path = tmp_path / "upstream"
    repo_path.mkdir()
    _git(["init"], cwd=repo_path)
    _git(["config", "user.name", "Test User"], cwd=repo_path)
    _git(["config", "user.email", "test@example.com"], cwd=repo_path)
    (repo_path / "message.txt").write_text("old\n", encoding="utf-8")
    (repo_path / "check.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "sys.exit(0 if Path('message.txt').read_text(encoding='utf-8') == 'new\\n' else 1)\n",
        encoding="utf-8",
    )
    _git(["add", "message.txt", "check.py"], cwd=repo_path)
    _git(["commit", "-m", "initial"], cwd=repo_path)
    base_commit = _git(["rev-parse", "HEAD"], cwd=repo_path).stdout.strip()
    (repo_path / "message.txt").write_text("new\n", encoding="utf-8")
    patch = _git(["diff", "--", "message.txt"], cwd=repo_path).stdout
    _git(["checkout", "--", "message.txt"], cwd=repo_path)
    return repo_path, base_commit, patch


def _git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _write_stub(path: Path) -> Path:
    path.write_text("{}\n", encoding="utf-8")
    return path
