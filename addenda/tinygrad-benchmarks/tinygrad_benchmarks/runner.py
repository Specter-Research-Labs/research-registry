from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from tinygrad_benchmarks import SCHEMA_VERSION
from tinygrad_benchmarks.data import BenchmarkRow, SubmissionRow, file_sha256
from tinygrad_benchmarks.patches import patch_metrics
from tinygrad_benchmarks.scoring import summarize_attempts, write_summary

_GIT_ENV_OVERRIDES = {
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_PAGER": "cat",
    "GIT_TERMINAL_PROMPT": "0",
}


def collect_host_metadata() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "cpu_count": os.cpu_count(),
        "network_expected_disabled": True,
    }


def run_submissions(
    *,
    rows: Sequence[BenchmarkRow],
    submissions: Sequence[SubmissionRow],
    out_dir: Path,
    runtime_dir: Path,
    index_path: Path,
    submissions_path: Path,
    repo_map: Mapping[str, str] | None = None,
    lane: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    selected_rows = {row.item_id: row for row in rows if lane is None or row.lane == lane}
    if not selected_rows:
        raise ValueError("no benchmark rows matched the requested lane")
    out_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    attempts: list[dict[str, Any]] = []
    host_metadata = collect_host_metadata()
    repo_cache: dict[str, Path] = {}
    for submission in submissions:
        row = selected_rows.get(submission.item_id)
        if row is None:
            raise ValueError(
                f"submission references unknown or filtered item_id: {submission.item_id}"
            )
        repo_source = repo_cache.get(row.repo_remote)
        if repo_source is None:
            repo_source = _resolve_repo_source(row.repo_remote, repo_map)
            repo_cache[row.repo_remote] = repo_source
        attempts.append(
            _run_single_attempt(
                row=row,
                submission=submission,
                repo_source=repo_source,
                runtime_dir=runtime_dir,
            )
        )
    attempts_path = out_dir / "attempts.jsonl"
    _write_attempts(attempts_path, attempts)
    summary = summarize_attempts(attempts)
    summary_path = out_dir / "summary.json"
    write_summary(summary_path, summary)
    host_path = out_dir / "host.json"
    host_path.write_text(
        json.dumps(host_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "index_path": str(index_path),
        "index_sha256": file_sha256(index_path),
        "submissions_path": str(submissions_path),
        "submissions_sha256": file_sha256(submissions_path),
        "lane": lane,
        "attempt_count": len(attempts),
        "artifact_dir": str(out_dir),
        "runtime_dir": str(runtime_dir),
        "attempts_path": str(attempts_path),
        "summary_path": str(summary_path),
        "host_path": str(host_path),
        "repo_map_keys": sorted(repo_cache.keys()),
    }
    return attempts, summary, manifest


def write_run_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _resolve_repo_source(repo_remote: str, repo_map: Mapping[str, str] | None) -> Path:
    mapped = repo_map.get(repo_remote) if repo_map is not None else None
    if mapped is not None:
        candidate = Path(mapped).expanduser().resolve()
        if not candidate.exists():
            raise ValueError(f"mapped repo source does not exist: {candidate}")
        return candidate
    candidate = Path(repo_remote).expanduser()
    if candidate.exists():
        return candidate.resolve()
    raise ValueError(
        "repo_remote must be a local repository path or resolved via --repo-map; "
        f"got {repo_remote!r}"
    )


def _run_single_attempt(
    *,
    row: BenchmarkRow,
    submission: SubmissionRow,
    repo_source: Path,
    runtime_dir: Path,
) -> dict[str, Any]:
    workspace = runtime_dir / f"{row.item_id}-{_safe_name(submission.candidate_id)}"
    patch_path = runtime_dir / f"{row.item_id}-{_safe_name(submission.candidate_id)}.patch"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(submission.patch, encoding="utf-8")
    metrics = patch_metrics(submission.patch)
    base_record = {
        "schema_version": SCHEMA_VERSION,
        "item_id": row.item_id,
        "task_id": row.task_id,
        "candidate_id": submission.candidate_id,
        "lane": row.lane,
        "repo_remote": row.repo_remote,
        "repo_commit": row.repo_commit,
        "repo_source": str(repo_source),
        "task_statement": row.task_statement,
        "target_paths": list(row.target_paths),
        "acceptance_command": list(row.acceptance_command),
        "acceptance_cwd": row.acceptance_cwd,
        "timeout_seconds": row.timeout_seconds,
        "required_capabilities": list(row.required_capabilities),
        "required_env": dict(row.required_env),
        "submission_metadata": dict(submission.metadata),
        "task_metadata": dict(row.metadata),
        "patch_sha256": file_sha256(patch_path),
        "patch_touched_paths": metrics["touched_paths"],
        "patch_added_line_count": metrics["added_line_count"],
        "patch_removed_line_count": metrics["removed_line_count"],
        "patch_line_count": metrics["patch_line_count"],
        "normalized_changed_lines": metrics["normalized_changed_lines"],
        "workspace": str(workspace),
        "workspace_has_git_metadata": False,
    }
    materialize = _materialize_commit_tree(
        repo_source=repo_source, commit=row.repo_commit, workspace=workspace
    )
    if materialize["exit_code"] != 0:
        return {
            **base_record,
            "success": False,
            "error_kind": "repo_checkout_failed",
            "error_detail": "failed to materialize commit tree",
            "apply_exit_code": None,
            "acceptance_exit_code": None,
            "acceptance_timed_out": False,
            "acceptance_duration_ms": None,
            "stdout": materialize["stdout"],
            "stderr": materialize["stderr"],
        }
    patch_check = _run_command(
        ["patch", "-p1", "--dry-run", "-d", str(workspace), "-i", str(patch_path)],
        cwd=runtime_dir,
    )
    if patch_check["exit_code"] != 0:
        return {
            **base_record,
            "success": False,
            "error_kind": "patch_check_failed",
            "error_detail": "patch --dry-run failed",
            "apply_exit_code": patch_check["exit_code"],
            "acceptance_exit_code": None,
            "acceptance_timed_out": False,
            "acceptance_duration_ms": None,
            "stdout": patch_check["stdout"],
            "stderr": patch_check["stderr"],
        }
    patch_apply = _run_command(
        ["patch", "-p1", "-d", str(workspace), "-i", str(patch_path)],
        cwd=runtime_dir,
    )
    if patch_apply["exit_code"] != 0:
        return {
            **base_record,
            "success": False,
            "error_kind": "patch_apply_failed",
            "error_detail": "patch apply failed",
            "apply_exit_code": patch_apply["exit_code"],
            "acceptance_exit_code": None,
            "acceptance_timed_out": False,
            "acceptance_duration_ms": None,
            "stdout": patch_apply["stdout"],
            "stderr": patch_apply["stderr"],
        }
    env = os.environ.copy()
    env.update(row.required_env)
    env["TGBENCH_NO_GIT"] = "1"
    env["TGBENCH_EXPECT_NO_NETWORK"] = "1"
    acceptance = _run_command(
        row.acceptance_command,
        cwd=workspace / row.acceptance_cwd,
        env=env,
        timeout_seconds=row.timeout_seconds,
    )
    if acceptance["timed_out"]:
        return {
            **base_record,
            "success": False,
            "error_kind": "acceptance_timeout",
            "error_detail": "acceptance command timed out",
            "apply_exit_code": patch_apply["exit_code"],
            "acceptance_exit_code": None,
            "acceptance_timed_out": True,
            "acceptance_duration_ms": acceptance["duration_ms"],
            "stdout": acceptance["stdout"],
            "stderr": acceptance["stderr"],
        }
    success = acceptance["exit_code"] == 0
    return {
        **base_record,
        "success": success,
        "error_kind": "none" if success else "acceptance_failed",
        "error_detail": None if success else "acceptance command failed",
        "apply_exit_code": patch_apply["exit_code"],
        "acceptance_exit_code": acceptance["exit_code"],
        "acceptance_timed_out": False,
        "acceptance_duration_ms": acceptance["duration_ms"],
        "stdout": acceptance["stdout"],
        "stderr": acceptance["stderr"],
    }


def _materialize_commit_tree(
    *,
    repo_source: Path,
    commit: str,
    workspace: Path,
) -> dict[str, Any]:
    archive_path = workspace.parent / f"{workspace.name}.tar"
    if archive_path.exists():
        archive_path.unlink()
    result = _run_command(
        ["git", "archive", "--format=tar", "--output", str(archive_path), commit],
        cwd=repo_source,
        env={**dict(os.environ), **_GIT_ENV_OVERRIDES},
    )
    if result["exit_code"] != 0:
        return result
    try:
        with tarfile.open(archive_path) as archive:
            archive.extractall(workspace, filter="data")
    finally:
        if archive_path.exists():
            archive_path.unlink()
    return result


def _run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        return {
            "exit_code": completed.returncode,
            "timed_out": False,
            "duration_ms": duration_ms,
            "stdout": _truncate_output(completed.stdout),
            "stderr": _truncate_output(completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return {
            "exit_code": None,
            "timed_out": True,
            "duration_ms": duration_ms,
            "stdout": _truncate_output(stdout),
            "stderr": _truncate_output(stderr),
        }


def _truncate_output(value: str, *, max_chars: int = 4000) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 15] + "\n...[truncated]\n"


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)


def _write_attempts(path: Path, attempts: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(attempt, sort_keys=True, separators=(",", ":")) for attempt in attempts]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
