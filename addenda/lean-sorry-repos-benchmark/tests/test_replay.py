from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from lean_sorry_repos_benchmark.data import BenchmarkRow
from lean_sorry_repos_benchmark.replay import (
    RepoReplayConfig,
    RepoReplayVerifier,
    load_repo_replay_profile_set,
    resolve_repo_replay_policy,
)


def _run(argv: list[str], *, cwd: Path) -> None:
    subprocess.run(argv, cwd=str(cwd), check=True, capture_output=True, text=True)


def _row(*, repo_remote: str, repo_commit: str, location_path: str = "Main.lean") -> BenchmarkRow:
    return BenchmarkRow(
        item_id="row1",
        repo_remote=repo_remote,
        repo_commit=repo_commit,
        repo_lean_version="4.28.0",
        location_path=location_path,
        location_start_line=2,
        location_start_column=3,
        location_end_line=2,
        location_end_column=8,
        goal_sha256=None,
        goal_text="x : Nat\n⊢ x = x",
        goal_bucket="core_easy",
        source_url="file://Main.lean",
        raw={},
    )


def _config(
    tmp_path: Path,
    *,
    timeout_seconds: float = 10.0,
    cold_start_timeout_seconds: float = 10.0,
    git_timeout_seconds: float = 20.0,
    prepare_cmd: str | None = None,
    prepare_timeout_seconds: float = 20.0,
) -> RepoReplayConfig:
    return RepoReplayConfig(
        cache_dir=tmp_path / "cache",
        lean_cmd="lean",
        timeout_seconds=timeout_seconds,
        cold_start_timeout_seconds=cold_start_timeout_seconds,
        git_timeout_seconds=git_timeout_seconds,
        prepare_cmd=prepare_cmd,
        prepare_timeout_seconds=prepare_timeout_seconds,
    )


def _verifier(tmp_path: Path) -> RepoReplayVerifier:
    return RepoReplayVerifier(_config(tmp_path))


def _profile_set(tmp_path: Path, profiles: list[dict[str, object]]):
    config_path = tmp_path / "profiles.json"
    config_path.write_text(
        json.dumps({"schema_version": 1, "profiles": profiles}),
        encoding="utf-8",
    )
    return load_repo_replay_profile_set(config_path)


def test_load_repo_replay_profile_set_and_resolve_policy(tmp_path: Path) -> None:
    profile_set = _profile_set(
        tmp_path,
        [
            {
                "id": "mathlib4",
                "match": {
                    "repo_remote_prefix": "https://github.com/leanprover-community/mathlib4",
                    "repo_lean_version_prefix": "4.2",
                },
                "overrides": {
                    "lean_cmd": "lake env lean",
                    "prepare_cmd": None,
                    "timeout_seconds": 180,
                    "cold_start_timeout_seconds": 300,
                },
            },
        ],
    )
    row = _row(
        repo_remote="https://github.com/leanprover-community/mathlib4",
        repo_commit="abc123",
    )
    base_config = _config(
        tmp_path,
        timeout_seconds=60.0,
        cold_start_timeout_seconds=120.0,
        git_timeout_seconds=180.0,
        prepare_cmd="lake build",
        prepare_timeout_seconds=900.0,
    )
    resolved = resolve_repo_replay_policy(
        row=row,
        base_config=base_config,
        profile_set=profile_set,
        strict=False,
    )
    assert resolved.profile_id == "mathlib4"
    assert resolved.config.lean_cmd == "lake env lean"
    assert resolved.config.prepare_cmd is None
    assert resolved.config.timeout_seconds == 180.0
    assert resolved.config.cold_start_timeout_seconds == 300.0
    assert resolved.config.cache_dir == base_config.cache_dir / "profile-mathlib4"


def test_resolve_repo_replay_policy_rejects_ambiguous_match(tmp_path: Path) -> None:
    profile_set = _profile_set(
        tmp_path,
        [
            {
                "id": "p1",
                "match": {"repo_remote_prefix": "https://example.com/"},
                "overrides": {"timeout_seconds": 30},
            },
            {
                "id": "p2",
                "match": {"repo_remote_prefix": "https://example.com/"},
                "overrides": {"timeout_seconds": 40},
            },
        ],
    )
    row = _row(repo_remote="https://example.com/repo.git", repo_commit="abc123")
    with pytest.raises(ValueError, match="multiple replay profiles matched"):
        resolve_repo_replay_policy(
            row=row,
            base_config=_config(tmp_path),
            profile_set=profile_set,
            strict=False,
        )


def test_resolve_repo_replay_policy_strict_unmatched(tmp_path: Path) -> None:
    profile_set = _profile_set(
        tmp_path,
        [
            {
                "id": "mathlib4",
                "match": {"repo_remote_prefix": "https://github.com/leanprover-community/mathlib4"},
                "overrides": {"timeout_seconds": 30},
            },
        ],
    )
    row = _row(repo_remote="https://example.com/repo.git", repo_commit="abc123")
    with pytest.raises(ValueError, match="no replay profile matched"):
        resolve_repo_replay_policy(
            row=row,
            base_config=_config(tmp_path),
            profile_set=profile_set,
            strict=True,
        )


def test_repo_replay_verifier_rejects_location_path_outside_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "Main.lean").write_text(
        "example (x : Nat) : x = x := by\n  sorry\n",
        encoding="utf-8",
    )
    row = _row(
        repo_remote="https://example.com/repo.git",
        repo_commit="abc123",
        location_path="../outside.lean",
    )
    verifier = _verifier(tmp_path)

    def fake_ensure_repo_at_commit(*, remote: str, commit: str) -> tuple[Path | None, str | None]:
        assert remote == row.repo_remote
        assert commit == row.repo_commit
        return repo_dir, None

    def fail_run(
        argv: list[str],
        *,
        cwd: Path | None,
        timeout_seconds: float,
    ) -> tuple[int | None, str | None]:
        raise AssertionError(f"lean should not run when containment guard fails: {argv}")

    monkeypatch.setattr(verifier, "_ensure_repo_at_commit", fake_ensure_repo_at_commit)
    monkeypatch.setattr(verifier, "_run", fail_run)

    result = verifier.verify(row=row, tactic="rfl")
    assert result.attempted is True
    assert result.success is False
    assert result.error is not None
    assert "escapes repository root" in result.error
    assert result.error_kind == "other"


def test_prepare_rows_caches_successful_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _row(repo_remote="https://example.com/repo.git", repo_commit="abc123")
    verifier = _verifier(tmp_path)
    verifier._repo_dir(row.repo_remote).mkdir(parents=True)
    run_calls: list[list[str]] = []

    def fake_run(
        argv: list[str],
        *,
        cwd: Path | None,
        timeout_seconds: float,
    ) -> tuple[int | None, str | None]:
        run_calls.append(argv)
        return 0, None

    monkeypatch.setattr(verifier, "_run", fake_run)

    assert verifier.prepare_rows([row, row]) == {}
    assert verifier.prepare_rows([row]) == {}
    assert len(run_calls) == 2
    assert run_calls[0][:2] == ["git", "fetch"]
    assert run_calls[1][:2] == ["git", "checkout"]


def test_prepare_rows_caches_setup_error_and_verify_surfaces_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _row(repo_remote="https://example.com/missing.git", repo_commit="deadbeef")
    verifier = _verifier(tmp_path)
    run_calls: list[list[str]] = []

    def fake_run(
        argv: list[str],
        *,
        cwd: Path | None,
        timeout_seconds: float,
    ) -> tuple[int | None, str | None]:
        run_calls.append(argv)
        return 1, "simulated failure"

    monkeypatch.setattr(verifier, "_run", fake_run)

    key = (row.repo_remote, row.repo_commit)
    first = verifier.prepare_rows([row])
    assert first[key] == "git clone failed: simulated failure"

    second = verifier.prepare_rows([row])
    assert "repository setup previously failed" in second[key]
    assert len(run_calls) == 1

    result = verifier.verify(row=row, tactic="rfl")
    assert result.success is False
    assert result.error is not None
    assert "repository setup previously failed" in result.error
    assert result.error_kind == "git_clone_failed"


@pytest.mark.skipif(shutil.which("lean") is None, reason="lean binary not available")
@pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available")
def test_repo_replay_verifier_local_repo(tmp_path: Path) -> None:
    src = tmp_path / "src-repo"
    src.mkdir()
    lean_file = src / "Main.lean"
    lean_file.write_text("example (x : Nat) : x = x := by\n  sorry\n", encoding="utf-8")
    _run(["git", "init"], cwd=src)
    _run(["git", "add", "Main.lean"], cwd=src)
    _run(
        [
            "git",
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "init",
        ],
        cwd=src,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(src),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    row = _row(repo_remote=str(src), repo_commit=commit, location_path="Main.lean")

    verifier = _verifier(tmp_path)

    ok = verifier.verify(row=row, tactic="rfl")
    assert ok.attempted is True
    assert ok.success is True
    assert ok.error is None
    assert ok.error_kind is None

    bad = verifier.verify(row=row, tactic="exact False")
    assert bad.attempted is True
    assert bad.success is False
    assert bad.error is not None
    assert bad.error_kind is not None

    assert "sorry" in lean_file.read_text(encoding="utf-8")
