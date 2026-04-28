from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lean_sorry_repos_benchmark.data import BenchmarkRow
from lean_sorry_repos_benchmark.verification import VerificationResult, classify_verification_error

REPO_REPLAY_PROFILE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RepoReplayConfig:
    cache_dir: Path
    lean_cmd: str
    timeout_seconds: float
    cold_start_timeout_seconds: float
    git_timeout_seconds: float
    prepare_cmd: str | None
    prepare_timeout_seconds: float
    max_error_chars: int = 400


@dataclass(frozen=True)
class RepoReplayProfileOverrides:
    lean_cmd: str | None = None
    timeout_seconds: float | None = None
    cold_start_timeout_seconds: float | None = None
    git_timeout_seconds: float | None = None
    prepare_cmd: str | None = None
    prepare_cmd_set: bool = False
    prepare_timeout_seconds: float | None = None
    max_error_chars: int | None = None


@dataclass(frozen=True)
class RepoReplayProfile:
    profile_id: str
    repo_remote: str | None
    repo_remote_prefix: str | None
    repo_remote_regex: str | None
    repo_lean_version: str | None
    repo_lean_version_prefix: str | None
    repo_lean_version_regex: str | None
    overrides: RepoReplayProfileOverrides
    repo_remote_pattern: re.Pattern[str] | None = field(default=None, repr=False, compare=False)
    repo_lean_version_pattern: re.Pattern[str] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def matches(self, row: BenchmarkRow) -> bool:
        if self.repo_remote is not None and row.repo_remote != self.repo_remote:
            return False
        if self.repo_remote_prefix is not None and not row.repo_remote.startswith(
            self.repo_remote_prefix
        ):
            return False
        if self.repo_remote_pattern is not None and self.repo_remote_pattern.search(
            row.repo_remote
        ) is None:
            return False
        lean_version = row.repo_lean_version
        if self.repo_lean_version is not None and lean_version != self.repo_lean_version:
            return False
        if self.repo_lean_version_prefix is not None:
            if lean_version is None or not lean_version.startswith(self.repo_lean_version_prefix):
                return False
        if self.repo_lean_version_pattern is not None:
            if lean_version is None or self.repo_lean_version_pattern.search(lean_version) is None:
                return False
        return True


@dataclass(frozen=True)
class RepoReplayProfileSet:
    schema_version: int
    profiles: tuple[RepoReplayProfile, ...]


@dataclass(frozen=True)
class RepoReplayResolvedPolicy:
    profile_id: str | None
    config: RepoReplayConfig


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("repo replay profile config must be a JSON object")
    return payload


def _expect_non_empty_string(
    value: Any,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _expect_positive_float(value: Any, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field_name} must be a number > 0")
    parsed = float(value)
    if parsed <= 0.0:
        raise ValueError(f"{field_name} must be > 0")
    return parsed


def _expect_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer >= 1")
    if value < 1:
        raise ValueError(f"{field_name} must be >= 1")
    return value


def _compile_profile_regex(
    value: str | None,
    *,
    field_name: str,
) -> re.Pattern[str] | None:
    if value is None:
        return None
    try:
        return re.compile(value)
    except re.error as exc:
        raise ValueError(f"{field_name} is not a valid regular expression: {exc}") from exc


def _parse_profile_overrides(
    *,
    raw: Any,
    profile_id: str,
) -> RepoReplayProfileOverrides:
    if not isinstance(raw, dict):
        raise ValueError(f"profile {profile_id!r}: overrides must be an object")
    if not raw:
        raise ValueError(f"profile {profile_id!r}: overrides must not be empty")
    allowed = {
        "lean_cmd",
        "timeout_seconds",
        "cold_start_timeout_seconds",
        "git_timeout_seconds",
        "prepare_cmd",
        "prepare_timeout_seconds",
        "max_error_chars",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(
            f"profile {profile_id!r}: overrides includes unsupported keys: {', '.join(unknown)}"
        )

    lean_cmd = None
    if "lean_cmd" in raw:
        lean_cmd = _expect_non_empty_string(
            raw["lean_cmd"],
            field_name=f"profile {profile_id!r}.overrides.lean_cmd",
        )

    timeout_seconds = None
    if "timeout_seconds" in raw:
        timeout_seconds = _expect_positive_float(
            raw["timeout_seconds"],
            field_name=f"profile {profile_id!r}.overrides.timeout_seconds",
        )

    cold_start_timeout_seconds = None
    if "cold_start_timeout_seconds" in raw:
        cold_start_timeout_seconds = _expect_positive_float(
            raw["cold_start_timeout_seconds"],
            field_name=f"profile {profile_id!r}.overrides.cold_start_timeout_seconds",
        )

    git_timeout_seconds = None
    if "git_timeout_seconds" in raw:
        git_timeout_seconds = _expect_positive_float(
            raw["git_timeout_seconds"],
            field_name=f"profile {profile_id!r}.overrides.git_timeout_seconds",
        )

    prepare_cmd = None
    prepare_cmd_set = False
    if "prepare_cmd" in raw:
        prepare_cmd_set = True
        raw_prepare_cmd = raw["prepare_cmd"]
        if raw_prepare_cmd is None:
            prepare_cmd = None
        else:
            prepare_cmd = _expect_non_empty_string(
                raw_prepare_cmd,
                field_name=f"profile {profile_id!r}.overrides.prepare_cmd",
            )

    prepare_timeout_seconds = None
    if "prepare_timeout_seconds" in raw:
        prepare_timeout_seconds = _expect_positive_float(
            raw["prepare_timeout_seconds"],
            field_name=f"profile {profile_id!r}.overrides.prepare_timeout_seconds",
        )

    max_error_chars = None
    if "max_error_chars" in raw:
        max_error_chars = _expect_positive_int(
            raw["max_error_chars"],
            field_name=f"profile {profile_id!r}.overrides.max_error_chars",
        )

    if (
        timeout_seconds is not None
        and cold_start_timeout_seconds is not None
        and cold_start_timeout_seconds < timeout_seconds
    ):
        raise ValueError(
            f"profile {profile_id!r}: overrides.cold_start_timeout_seconds must be >= "
            "overrides.timeout_seconds when both are set"
        )

    return RepoReplayProfileOverrides(
        lean_cmd=lean_cmd,
        timeout_seconds=timeout_seconds,
        cold_start_timeout_seconds=cold_start_timeout_seconds,
        git_timeout_seconds=git_timeout_seconds,
        prepare_cmd=prepare_cmd,
        prepare_cmd_set=prepare_cmd_set,
        prepare_timeout_seconds=prepare_timeout_seconds,
        max_error_chars=max_error_chars,
    )


def _parse_profile_match(*, raw: Any, profile_id: str) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError(f"profile {profile_id!r}: match must be an object")
    if not raw:
        raise ValueError(f"profile {profile_id!r}: match must include at least one selector")
    allowed = {
        "repo_remote",
        "repo_remote_prefix",
        "repo_remote_regex",
        "repo_lean_version",
        "repo_lean_version_prefix",
        "repo_lean_version_regex",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(
            f"profile {profile_id!r}: match includes unsupported keys: {', '.join(unknown)}"
        )
    parsed: dict[str, str] = {}
    for key, value in raw.items():
        parsed[key] = _expect_non_empty_string(
            value,
            field_name=f"profile {profile_id!r}.match.{key}",
        )
    return parsed


def load_repo_replay_profile_set(path: Path) -> RepoReplayProfileSet:
    payload = _load_json_object(path)
    schema_version = payload.get("schema_version", REPO_REPLAY_PROFILE_SCHEMA_VERSION)
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise ValueError("schema_version must be an integer")
    if schema_version != REPO_REPLAY_PROFILE_SCHEMA_VERSION:
        raise ValueError(
            "unsupported profile schema_version="
            f"{schema_version}; expected {REPO_REPLAY_PROFILE_SCHEMA_VERSION}"
        )
    profiles_obj = payload.get("profiles")
    if not isinstance(profiles_obj, list) or not profiles_obj:
        raise ValueError("profiles must be a non-empty array")

    profiles: list[RepoReplayProfile] = []
    seen_ids: set[str] = set()
    for idx, profile_obj in enumerate(profiles_obj):
        if not isinstance(profile_obj, dict):
            raise ValueError(f"profiles[{idx}] must be an object")
        profile_id = _expect_non_empty_string(
            profile_obj.get("id"),
            field_name=f"profiles[{idx}].id",
        )
        if profile_id in seen_ids:
            raise ValueError(f"duplicate profile id: {profile_id}")
        seen_ids.add(profile_id)
        if "match" not in profile_obj:
            raise ValueError(f"profile {profile_id!r}: missing match object")
        if "overrides" not in profile_obj:
            raise ValueError(f"profile {profile_id!r}: missing overrides object")
        parsed_match = _parse_profile_match(raw=profile_obj["match"], profile_id=profile_id)
        repo_remote_regex = parsed_match.get("repo_remote_regex")
        repo_lean_version_regex = parsed_match.get("repo_lean_version_regex")
        profiles.append(
            RepoReplayProfile(
                profile_id=profile_id,
                repo_remote=parsed_match.get("repo_remote"),
                repo_remote_prefix=parsed_match.get("repo_remote_prefix"),
                repo_remote_regex=repo_remote_regex,
                repo_lean_version=parsed_match.get("repo_lean_version"),
                repo_lean_version_prefix=parsed_match.get("repo_lean_version_prefix"),
                repo_lean_version_regex=repo_lean_version_regex,
                overrides=_parse_profile_overrides(
                    raw=profile_obj["overrides"],
                    profile_id=profile_id,
                ),
                repo_remote_pattern=_compile_profile_regex(
                    repo_remote_regex,
                    field_name=f"profile {profile_id!r}.match.repo_remote_regex",
                ),
                repo_lean_version_pattern=_compile_profile_regex(
                    repo_lean_version_regex,
                    field_name=f"profile {profile_id!r}.match.repo_lean_version_regex",
                ),
            )
        )

    return RepoReplayProfileSet(
        schema_version=schema_version,
        profiles=tuple(profiles),
    )


def _profile_cache_dir(*, base_cache_dir: Path, profile_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in profile_id)
    safe = safe.strip("-") or "profile"
    return base_cache_dir / f"profile-{safe}"


def apply_repo_replay_profile(
    *,
    base_config: RepoReplayConfig,
    profile: RepoReplayProfile,
) -> RepoReplayConfig:
    overrides = profile.overrides
    timeout_seconds = (
        overrides.timeout_seconds
        if overrides.timeout_seconds is not None
        else base_config.timeout_seconds
    )
    cold_start_timeout_seconds = (
        overrides.cold_start_timeout_seconds
        if overrides.cold_start_timeout_seconds is not None
        else base_config.cold_start_timeout_seconds
    )
    if cold_start_timeout_seconds < timeout_seconds:
        raise ValueError(
            f"profile {profile.profile_id!r}: cold_start_timeout_seconds must be >= "
            "timeout_seconds after applying overrides"
        )
    prepare_cmd = base_config.prepare_cmd
    if overrides.prepare_cmd_set:
        prepare_cmd = overrides.prepare_cmd
    return RepoReplayConfig(
        cache_dir=_profile_cache_dir(
            base_cache_dir=base_config.cache_dir,
            profile_id=profile.profile_id,
        ),
        lean_cmd=overrides.lean_cmd if overrides.lean_cmd is not None else base_config.lean_cmd,
        timeout_seconds=timeout_seconds,
        cold_start_timeout_seconds=cold_start_timeout_seconds,
        git_timeout_seconds=(
            overrides.git_timeout_seconds
            if overrides.git_timeout_seconds is not None
            else base_config.git_timeout_seconds
        ),
        prepare_cmd=prepare_cmd,
        prepare_timeout_seconds=(
            overrides.prepare_timeout_seconds
            if overrides.prepare_timeout_seconds is not None
            else base_config.prepare_timeout_seconds
        ),
        max_error_chars=(
            overrides.max_error_chars
            if overrides.max_error_chars is not None
            else base_config.max_error_chars
        ),
    )


def resolve_repo_replay_policy(
    *,
    row: BenchmarkRow,
    base_config: RepoReplayConfig,
    profile_set: RepoReplayProfileSet | None,
    strict: bool,
) -> RepoReplayResolvedPolicy:
    if profile_set is None:
        return RepoReplayResolvedPolicy(profile_id=None, config=base_config)
    matched = [profile for profile in profile_set.profiles if profile.matches(row)]
    if len(matched) > 1:
        candidates = ", ".join(profile.profile_id for profile in matched)
        raise ValueError(
            f"row {row.item_id}: multiple replay profiles matched "
            f"{row.repo_remote}@{row.repo_commit}: {candidates}"
        )
    if not matched:
        if strict:
            lean_version = row.repo_lean_version or "unknown"
            raise ValueError(
                "row "
                f"{row.item_id}: no replay profile matched {row.repo_remote}@{row.repo_commit} "
                f"(lean={lean_version})"
            )
        return RepoReplayResolvedPolicy(profile_id=None, config=base_config)
    profile = matched[0]
    return RepoReplayResolvedPolicy(
        profile_id=profile.profile_id,
        config=apply_repo_replay_profile(base_config=base_config, profile=profile),
    )


def _trim_error(text: str, *, max_chars: int) -> str:
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 3] + "..."


def _line_col_to_index(text: str, line: int, column: int) -> int:
    if line <= 0 or column <= 0:
        raise ValueError("line/column must be >= 1")
    lines = text.splitlines(keepends=True)
    if line > len(lines):
        raise ValueError("line out of range")
    offset = 0
    for idx in range(line - 1):
        offset += len(lines[idx])
    current = lines[line - 1]
    current_no_nl = current[:-1] if current.endswith("\n") else current
    max_col = len(current_no_nl) + 1
    if column > max_col:
        raise ValueError("column out of range")
    return offset + (column - 1)


def _replace_span(
    text: str,
    *,
    start_line: int,
    start_column: int,
    end_line: int,
    end_column: int,
    replacement: str,
) -> str:
    start_idx = _line_col_to_index(text, start_line, start_column)
    end_idx = _line_col_to_index(text, end_line, end_column)
    if end_idx < start_idx:
        raise ValueError("invalid span: end before start")
    return text[:start_idx] + replacement + text[end_idx:]


class RepoReplayVerifier:
    def __init__(self, config: RepoReplayConfig) -> None:
        if config.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if config.cold_start_timeout_seconds < config.timeout_seconds:
            raise ValueError("cold_start_timeout_seconds must be >= timeout_seconds")
        if config.git_timeout_seconds <= 0:
            raise ValueError("git_timeout_seconds must be > 0")
        if config.prepare_timeout_seconds <= 0:
            raise ValueError("prepare_timeout_seconds must be > 0")
        if not config.lean_cmd.strip():
            raise ValueError("lean_cmd must be non-empty")
        self._config = config
        self._config.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lean_argv_template = shlex.split(config.lean_cmd)
        if not self._lean_argv_template:
            raise ValueError("lean_cmd must parse into argv")
        self._prepare_argv = (
            shlex.split(config.prepare_cmd) if config.prepare_cmd is not None else None
        )
        self._prepared: set[tuple[str, str]] = set()
        self._repo_ready: dict[tuple[str, str], Path] = {}
        self._repo_setup_errors: dict[tuple[str, str], str] = {}
        self._repo_verify_counts: dict[tuple[str, str], int] = {}
        self._repo_locks: dict[tuple[str, str], threading.Lock] = {}
        self._repo_locks_guard = threading.Lock()

    def _lock_for_repo(self, repo_key: tuple[str, str]) -> threading.Lock:
        with self._repo_locks_guard:
            lock = self._repo_locks.get(repo_key)
            if lock is None:
                lock = threading.Lock()
                self._repo_locks[repo_key] = lock
            return lock

    def _resolve_target_path(
        self,
        *,
        repo_dir: Path,
        location_path: str,
    ) -> tuple[Path | None, str | None, str | None]:
        repo_root = repo_dir.resolve()
        target = (repo_root / location_path).resolve(strict=False)
        try:
            relative = target.relative_to(repo_root).as_posix()
        except ValueError:
            return None, None, f"location_path escapes repository root: {location_path}"
        return target, relative, None

    def _repo_dir(self, remote: str) -> Path:
        digest = hashlib.sha256(remote.encode("utf-8")).hexdigest()[:16]
        stem = remote.rstrip("/").split("/")[-1].removesuffix(".git")
        safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in stem)
        return self._config.cache_dir / f"{safe_stem}-{digest}"

    def _run(
        self,
        argv: list[str],
        *,
        cwd: Path | None,
        timeout_seconds: float,
    ) -> tuple[int | None, str | None]:
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd) if cwd is not None else None,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            return None, str(exc)
        except subprocess.TimeoutExpired:
            return None, f"timeout after {timeout_seconds:.1f}s"
        if proc.returncode == 0:
            return 0, None
        combined = (proc.stdout + "\n" + proc.stderr).strip()
        if not combined:
            combined = f"command failed with code {proc.returncode}"
        return proc.returncode, _trim_error(combined, max_chars=self._config.max_error_chars)

    def _ensure_repo_at_commit(self, *, remote: str, commit: str) -> tuple[Path | None, str | None]:
        repo_key = (remote, commit)
        cached_error = self._repo_setup_errors.get(repo_key)
        if cached_error is not None:
            return None, f"repository setup previously failed: {cached_error}"
        cached_dir = self._repo_ready.get(repo_key)
        if cached_dir is not None and cached_dir.exists():
            return cached_dir, None

        repo_dir = self._repo_dir(remote)
        if not repo_dir.exists():
            code, error = self._run(
                ["git", "clone", "--filter=blob:none", remote, str(repo_dir)],
                cwd=None,
                timeout_seconds=self._config.git_timeout_seconds,
            )
            if code != 0:
                final = f"git clone failed: {error}"
                self._repo_setup_errors[repo_key] = final
                return None, final

        code, error = self._run(
            ["git", "fetch", "origin", commit, "--depth", "1"],
            cwd=repo_dir,
            timeout_seconds=self._config.git_timeout_seconds,
        )
        if code != 0:
            final = f"git fetch failed: {error}"
            self._repo_setup_errors[repo_key] = final
            return None, final

        code, error = self._run(
            ["git", "checkout", "--detach", commit],
            cwd=repo_dir,
            timeout_seconds=self._config.git_timeout_seconds,
        )
        if code != 0:
            final = f"git checkout failed: {error}"
            self._repo_setup_errors[repo_key] = final
            return None, final

        if self._prepare_argv is not None and repo_key not in self._prepared:
            code, error = self._run(
                list(self._prepare_argv),
                cwd=repo_dir,
                timeout_seconds=self._config.prepare_timeout_seconds,
            )
            if code != 0:
                final = f"prepare command failed: {error}"
                self._repo_setup_errors[repo_key] = final
                return None, final
            self._prepared.add(repo_key)
        self._repo_ready[repo_key] = repo_dir
        return repo_dir, None

    def prepare_rows(self, rows: Iterable[BenchmarkRow]) -> dict[tuple[str, str], str]:
        errors: dict[tuple[str, str], str] = {}
        seen: set[tuple[str, str]] = set()
        for row in rows:
            repo_key = (row.repo_remote, row.repo_commit)
            if repo_key in seen:
                continue
            seen.add(repo_key)
            with self._lock_for_repo(repo_key):
                _, error = self._ensure_repo_at_commit(
                    remote=row.repo_remote,
                    commit=row.repo_commit,
                )
            if error is not None:
                errors[repo_key] = error
        return errors

    def _lean_argv(self, relative_file: str) -> list[str]:
        if any("{file}" in token for token in self._lean_argv_template):
            return [token.replace("{file}", relative_file) for token in self._lean_argv_template]
        return [*self._lean_argv_template, relative_file]

    def verify(self, *, row: BenchmarkRow, tactic: str) -> VerificationResult:
        start = time.perf_counter()
        tactic_line = tactic.strip()
        if not tactic_line:
            error = "empty tactic"
            return VerificationResult(
                attempted=True,
                success=False,
                error=error,
                error_kind=classify_verification_error(error),
                exit_code=None,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        if "\n" in tactic_line:
            lines = [line.strip() for line in tactic_line.splitlines() if line.strip()]
            if not lines:
                error = "empty tactic"
                return VerificationResult(
                    attempted=True,
                    success=False,
                    error=error,
                    error_kind=classify_verification_error(error),
                    exit_code=None,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                )
            tactic_line = lines[0]
        repo_key = (row.repo_remote, row.repo_commit)
        with self._lock_for_repo(repo_key):
            repo_dir, repo_error = self._ensure_repo_at_commit(
                remote=row.repo_remote,
                commit=row.repo_commit,
            )
            if repo_dir is None:
                error = repo_error or "repo setup failed"
                return VerificationResult(
                    attempted=True,
                    success=False,
                    error=error,
                    error_kind=classify_verification_error(error),
                    exit_code=None,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                )

            target, relative_target, target_error = self._resolve_target_path(
                repo_dir=repo_dir,
                location_path=row.location_path,
            )
            if target is None:
                error = target_error or "invalid location_path"
                return VerificationResult(
                    attempted=True,
                    success=False,
                    error=error,
                    error_kind=classify_verification_error(error),
                    exit_code=None,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                )

            try:
                original = target.read_text(encoding="utf-8")
            except FileNotFoundError:
                error = f"target file missing: {row.location_path}"
                return VerificationResult(
                    attempted=True,
                    success=False,
                    error=error,
                    error_kind=classify_verification_error(error),
                    exit_code=None,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                )
            except UnicodeDecodeError:
                error = f"target file is not utf-8: {row.location_path}"
                return VerificationResult(
                    attempted=True,
                    success=False,
                    error=error,
                    error_kind=classify_verification_error(error),
                    exit_code=None,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                )

            try:
                start_column = row.location_start_column
                end_column = row.location_end_column
                # Some upstream snapshots encode columns as 0-based; normalize here.
                if start_column == 0 or end_column == 0:
                    start_column += 1
                    end_column += 1
                patched = _replace_span(
                    original,
                    start_line=row.location_start_line,
                    start_column=start_column,
                    end_line=row.location_end_line,
                    end_column=end_column,
                    replacement=tactic_line,
                )
            except ValueError as exc:
                error = f"invalid location span: {exc}"
                return VerificationResult(
                    attempted=True,
                    success=False,
                    error=error,
                    error_kind=classify_verification_error(error),
                    exit_code=None,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                )

            target.write_text(patched, encoding="utf-8")
            verify_count = self._repo_verify_counts.get(repo_key, 0)
            timeout_seconds = (
                self._config.cold_start_timeout_seconds
                if verify_count == 0
                else self._config.timeout_seconds
            )
            lean_target = relative_target or row.location_path
            try:
                code, error = self._run(
                    self._lean_argv(lean_target),
                    cwd=repo_dir,
                    timeout_seconds=timeout_seconds,
                )
            finally:
                target.write_text(original, encoding="utf-8")
            self._repo_verify_counts[repo_key] = verify_count + 1

        latency_ms = int((time.perf_counter() - start) * 1000)
        if code == 0:
            return VerificationResult(
                attempted=True,
                success=True,
                error=None,
                error_kind=None,
                exit_code=0,
                latency_ms=latency_ms,
            )
        final_error = error or f"lean command failed with code {code}"
        return VerificationResult(
            attempted=True,
            success=False,
            error=final_error,
            error_kind=classify_verification_error(final_error),
            exit_code=code,
            latency_ms=latency_ms,
        )
