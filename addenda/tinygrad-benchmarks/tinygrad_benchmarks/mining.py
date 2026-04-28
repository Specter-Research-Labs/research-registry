from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from tinygrad_benchmarks import SCHEMA_VERSION

_ISSUE_REF_PATTERN = re.compile(r"#\d+")
_SKIP_SUBJECT_PREFIXES = (
    "merge ",
    "revert ",
    "release ",
    "bump ",
    "chore(deps",
    "deps:",
)
_DOC_SUFFIXES = {
    ".md",
    ".rst",
    ".txt",
    ".adoc",
}
_DOC_PARTS = {"docs", "doc"}
_META_PARTS = {".github", ".gitlab", "vendor", "third_party", "dist", "build"}
_UNSUITABLE_TEST_PARTS = {"amd", "external", "models", "speed", "web"}
_HISTORY_MINED_REF = "history:mined"
_GIT_ENV_OVERRIDES = {
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_PAGER": "cat",
    "GIT_TERMINAL_PROMPT": "0",
}


def mine_history_candidates(
    *,
    repo: Path,
    repo_remote: str | None,
    rev_range: str,
    max_candidates: int | None,
    max_files: int,
    max_source_files: int,
    max_test_files: int,
    max_patch_lines: int,
    timeout_seconds: int,
    allow_no_tests: bool,
    include_source_prefixes: Sequence[str] = (),
    include_test_prefixes: Sequence[str] = (),
    exclude_path_prefixes: Sequence[str] = (),
    progress_every: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    resolved_repo = repo.resolve()
    _git(
        resolved_repo,
        ["rev-parse", "--git-dir"],
    )
    logical_remote = (
        repo_remote
        or _git_optional(
            resolved_repo,
            ["config", "--get", "remote.origin.url"],
        )
        or str(resolved_repo)
    )
    source_prefixes = _normalize_prefixes(include_source_prefixes)
    test_prefixes = _normalize_prefixes(include_test_prefixes)
    excluded_prefixes = _normalize_prefixes(exclude_path_prefixes)
    commits = _git_lines(resolved_repo, ["rev-list", "--reverse", rev_range])
    filter_counts: dict[str, int] = {}
    accepted_candidates: list[dict[str, Any]] = []
    error_examples: list[dict[str, str]] = []
    for index, commit in enumerate(commits, start=1):
        try:
            candidate, reason = _candidate_from_commit(
                repo=resolved_repo,
                repo_remote=logical_remote,
                commit=commit,
                max_files=max_files,
                max_source_files=max_source_files,
                max_test_files=max_test_files,
                max_patch_lines=max_patch_lines,
                timeout_seconds=timeout_seconds,
                allow_no_tests=allow_no_tests,
                include_source_prefixes=source_prefixes,
                include_test_prefixes=test_prefixes,
                exclude_path_prefixes=excluded_prefixes,
            )
        except subprocess.CalledProcessError as error:
            candidate = None
            reason = "git_error"
            if len(error_examples) < 10:
                error_examples.append(
                    {
                        "commit": commit,
                        "command": " ".join(str(part) for part in error.cmd),
                        "stderr": (error.stderr or "").strip(),
                    }
                )
        filter_counts[reason] = filter_counts.get(reason, 0) + 1
        if candidate is not None:
            accepted_candidates.append(candidate)
        if progress_every is not None and progress_every > 0:
            if index % progress_every == 0 or index == len(commits):
                print(
                    (
                        f"[mine-history] scanned {index}/{len(commits)} commits, "
                        f"accepted {len(accepted_candidates)}"
                    ),
                    file=sys.stderr,
                )
    candidates = sorted(
        accepted_candidates,
        key=lambda candidate: (
            -int(candidate["metadata"]["quality_score"]),
            int(candidate["metadata"]["patch_line_count"]),
            int(candidate["metadata"]["changed_file_count"]),
            str(candidate["metadata"]["mined_from_commit"]),
        ),
    )
    if max_candidates is not None:
        candidates = candidates[:max_candidates]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "repo": str(resolved_repo),
        "repo_remote": logical_remote,
        "rev_range": rev_range,
        "scanned_commit_count": len(commits),
        "accepted_candidate_count": len(accepted_candidates),
        "candidate_count": len(candidates),
        "filter_counts": dict(sorted(filter_counts.items())),
        "config": {
            "max_candidates": max_candidates,
            "max_files": max_files,
            "max_source_files": max_source_files,
            "max_test_files": max_test_files,
            "max_patch_lines": max_patch_lines,
            "timeout_seconds": timeout_seconds,
            "allow_no_tests": allow_no_tests,
            "include_source_prefixes": list(source_prefixes),
            "include_test_prefixes": list(test_prefixes),
            "exclude_path_prefixes": list(excluded_prefixes),
            "progress_every": progress_every,
        },
        "error_examples": error_examples,
        "quality_score_range": _quality_score_range(candidates),
    }
    return candidates, manifest


def _candidate_from_commit(
    *,
    repo: Path,
    repo_remote: str,
    commit: str,
    max_files: int,
    max_source_files: int,
    max_test_files: int,
    max_patch_lines: int,
    timeout_seconds: int,
    allow_no_tests: bool,
    include_source_prefixes: tuple[str, ...],
    include_test_prefixes: tuple[str, ...],
    exclude_path_prefixes: tuple[str, ...],
) -> tuple[dict[str, Any] | None, str]:
    parent_line = _git_text(repo, ["rev-list", "--parents", "-n", "1", commit]).strip()
    parents = parent_line.split()
    if len(parents) != 2:
        return None, "not_single_parent"
    parent_commit = parents[1]
    subject, body, author_date = _git_commit_message(repo, commit)
    subject_lower = subject.casefold()
    if subject_lower.startswith(_SKIP_SUBJECT_PREFIXES):
        return None, "skip_subject"
    numstat_entries = _numstat_entries(repo, parent_commit, commit)
    if not numstat_entries:
        return None, "empty_diff"
    if any(entry["binary"] for entry in numstat_entries):
        return None, "binary_diff"
    if len(numstat_entries) > max_files:
        return None, "too_many_files"
    total_patch_lines = sum(entry["additions"] + entry["deletions"] for entry in numstat_entries)
    if total_patch_lines > max_patch_lines:
        return None, "patch_too_large"
    if any(
        _matches_prefixes(str(entry["path"]), exclude_path_prefixes)
        for entry in numstat_entries
    ):
        return None, "excluded_path_prefix"
    target_paths = [
        str(entry["path"])
        for entry in numstat_entries
        if _is_source_path(
            entry["path"],
            include_source_prefixes=include_source_prefixes,
            exclude_path_prefixes=exclude_path_prefixes,
        )
    ]
    changed_test_paths = [
        str(entry["path"])
        for entry in numstat_entries
        if _is_test_path(
            entry["path"],
            include_test_prefixes=include_test_prefixes,
            exclude_path_prefixes=exclude_path_prefixes,
        )
    ]
    benchmark_test_paths = [
        path for path in changed_test_paths if _is_benchmark_test_path(path)
    ]
    ignored_paths = [
        str(entry["path"])
        for entry in numstat_entries
        if not _is_source_path(
            entry["path"],
            include_source_prefixes=include_source_prefixes,
            exclude_path_prefixes=exclude_path_prefixes,
        )
        and not _is_test_path(
            entry["path"],
            include_test_prefixes=include_test_prefixes,
            exclude_path_prefixes=exclude_path_prefixes,
        )
    ]
    if not target_paths:
        return None, "no_target_paths"
    if len(target_paths) > max_source_files:
        return None, "too_many_source_files"
    if len(changed_test_paths) > max_test_files:
        return None, "too_many_test_files"
    if changed_test_paths and not benchmark_test_paths:
        return None, "no_benchmark_tests"
    if not allow_no_tests and not benchmark_test_paths:
        return None, "no_changed_tests"
    patch = _git_patch(repo, parent_commit, commit)
    issue_refs = _extract_issue_refs(subject, body)
    source_refs = [_HISTORY_MINED_REF]
    quality = _quality_metrics(
        subject=subject,
        issue_refs=issue_refs,
        target_paths=target_paths,
        changed_test_paths=benchmark_test_paths,
        ignored_paths=ignored_paths,
        total_patch_lines=total_patch_lines,
        changed_file_count=len(numstat_entries),
    )
    candidate = {
        "repo_remote": repo_remote,
        "repo_commit": parent_commit,
        "task_statement": _synthesized_task_statement(
            target_paths=target_paths,
            changed_test_paths=benchmark_test_paths,
        ),
        "source_refs": source_refs,
        "target_paths": sorted(target_paths),
        "acceptance_command": _acceptance_command(benchmark_test_paths),
        "timeout_seconds": timeout_seconds,
        "metadata": {
            "mined_from_commit": commit,
            "commit_subject": subject,
            "commit_author_date": author_date,
            "changed_test_paths": sorted(benchmark_test_paths),
            "task_statement_style": "synthetic_path_test_v1",
            "ignored_paths": sorted(ignored_paths),
            "source_file_count": len(target_paths),
            "test_file_count": len(benchmark_test_paths),
            "changed_file_count": len(numstat_entries),
            "patch_line_count": total_patch_lines,
            "quality_score": quality["score"],
            "quality_components": quality["components"],
            "review_priority": quality["review_priority"],
            "leakage_flags": quality["leakage_flags"],
        },
        "gold_commit": commit,
        "gold_patch": patch,
        "historical_solution_refs": [f"commit:{commit}"],
        "resolution_source_refs": [
            f"commit:{commit}",
            *[f"issue:{issue_ref}" for issue_ref in issue_refs],
            *source_refs,
        ],
        "maintainer_notes": "history-mined candidate; review for leakage before publication",
    }
    return candidate, "accepted"


def _git_commit_message(repo: Path, commit: str) -> tuple[str, str, str]:
    payload = _git_text(
        repo,
        ["show", "-s", "--format=%s%x00%b%x00%aI", commit],
    )
    subject, body, author_date = payload.split("\x00")
    return subject.strip(), body.strip(), author_date.strip()


def _numstat_entries(repo: Path, parent_commit: str, commit: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in _git_lines(
        repo,
        ["diff", "--no-ext-diff", "--no-renames", "--numstat", parent_commit, commit],
    ):
        parts = line.split("\t", maxsplit=2)
        if len(parts) != 3:
            continue
        additions_raw, deletions_raw, raw_path = parts
        path = _normalize_diff_path(raw_path)
        binary = additions_raw == "-" or deletions_raw == "-"
        additions = 0 if binary else int(additions_raw)
        deletions = 0 if binary else int(deletions_raw)
        entries.append(
            {
                "path": path,
                "binary": binary,
                "additions": additions,
                "deletions": deletions,
            }
        )
    return entries


def _git_patch(repo: Path, parent_commit: str, commit: str) -> str:
    return _git_text(repo, ["diff", "--no-ext-diff", "--no-renames", parent_commit, commit])


def _acceptance_command(changed_test_paths: list[str]) -> list[str]:
    if changed_test_paths:
        return ["python", "-m", "pytest", *sorted(changed_test_paths)]
    return ["python", "-m", "pytest"]


def _extract_issue_refs(subject: str, body: str) -> list[str]:
    refs = sorted(set(_ISSUE_REF_PATTERN.findall(f"{subject}\n{body}")))
    return refs


def _normalize_diff_path(raw_path: str) -> str:
    if "=>" not in raw_path:
        return raw_path.strip()
    if "{" in raw_path and "}" in raw_path:
        prefix, rest = raw_path.split("{", maxsplit=1)
        inner, suffix = rest.split("}", maxsplit=1)
        _old, new = inner.split("=>", maxsplit=1)
        return f"{prefix}{new.strip()}{suffix}".replace("//", "/").strip()
    return raw_path.split("=>", maxsplit=1)[1].strip()


def _is_test_path(
    path: str,
    *,
    include_test_prefixes: tuple[str, ...] = (),
    exclude_path_prefixes: tuple[str, ...] = (),
) -> bool:
    if _matches_prefixes(path, exclude_path_prefixes):
        return False
    if include_test_prefixes and not _matches_prefixes(path, include_test_prefixes):
        return False
    value = Path(path)
    parts = {part.casefold() for part in value.parts}
    stem = value.stem.casefold()
    name = value.name.casefold()
    return (
        "test" in parts or "tests" in parts or stem.startswith("test_") or name.endswith("_test.py")
    )


def _is_benchmark_test_path(path: str) -> bool:
    value = Path(path)
    parts = tuple(part.casefold() for part in value.parts)
    if not parts:
        return False
    if parts[0] == "tests":
        return True
    if parts[0] != "test":
        return False
    if any(part in _UNSUITABLE_TEST_PARTS for part in parts[1:]):
        return False
    return not value.name.casefold().startswith("external_")


def _is_doc_or_meta_path(path: str) -> bool:
    value = Path(path)
    parts = {part.casefold() for part in value.parts}
    suffix = value.suffix.casefold()
    return suffix in _DOC_SUFFIXES or bool(parts & _DOC_PARTS) or bool(parts & _META_PARTS)


def _is_source_path(
    path: str,
    *,
    include_source_prefixes: tuple[str, ...] = (),
    exclude_path_prefixes: tuple[str, ...] = (),
) -> bool:
    if _matches_prefixes(path, exclude_path_prefixes):
        return False
    if include_source_prefixes and not _matches_prefixes(path, include_source_prefixes):
        return False
    return not _is_test_path(path) and not _is_doc_or_meta_path(path)


def _normalize_prefixes(prefixes: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for prefix in prefixes:
        value = prefix.strip().replace("\\", "/").lstrip("./")
        if not value:
            continue
        normalized.append(value.rstrip("/"))
    return tuple(dict.fromkeys(normalized))


def _matches_prefixes(path: str, prefixes: tuple[str, ...]) -> bool:
    if not prefixes:
        return False
    normalized_path = path.replace("\\", "/").lstrip("./")
    for prefix in prefixes:
        if normalized_path == prefix or normalized_path.startswith(f"{prefix}/"):
            return True
    return False


def _synthesized_task_statement(*, target_paths: list[str], changed_test_paths: list[str]) -> str:
    target_summary = _summarize_paths(target_paths)
    if changed_test_paths:
        test_summary = _summarize_paths(changed_test_paths)
        verb = "Fix" if len(target_paths) == 1 else "Update"
        return f"{verb} `{target_summary}` so `{test_summary}` passes."
    if len(target_paths) == 1:
        return f"Fix behavior in `{target_summary}` without regressing the pinned test suite."
    return f"Update `{target_summary}` without regressing the pinned test suite."


def _summarize_paths(paths: list[str], *, max_items: int = 2) -> str:
    ordered = sorted(paths)
    if not ordered:
        return "the targeted files"
    if len(ordered) <= max_items:
        return " and ".join(ordered)
    head = ", ".join(ordered[:max_items])
    remaining = len(ordered) - max_items
    suffix = "file" if remaining == 1 else "files"
    return f"{head}, and {remaining} more {suffix}"


def _quality_metrics(
    *,
    subject: str,
    issue_refs: list[str],
    target_paths: list[str],
    changed_test_paths: list[str],
    ignored_paths: list[str],
    total_patch_lines: int,
    changed_file_count: int,
) -> dict[str, Any]:
    score = 0
    components: dict[str, int] = {}
    leakage_flags: list[str] = []
    components["has_issue_ref"] = 12 if issue_refs else 0
    score += components["has_issue_ref"]
    components["has_benchmark_tests"] = 28 if changed_test_paths else -20
    score += components["has_benchmark_tests"]
    components["source_file_count"] = max(0, 18 - ((len(target_paths) - 1) * 6))
    score += components["source_file_count"]
    components["test_file_count"] = max(0, 10 - (max(len(changed_test_paths), 1) - 1) * 3)
    score += components["test_file_count"]
    components["patch_size"] = _patch_size_score(total_patch_lines)
    score += components["patch_size"]
    components["changed_file_count"] = max(0, 12 - max(changed_file_count - 1, 0) * 3)
    score += components["changed_file_count"]
    components["ignored_path_noise"] = -min(len(ignored_paths) * 4, 12)
    score += components["ignored_path_noise"]
    subject_lower = subject.casefold()
    if "wip" in subject_lower or "tmp" in subject_lower:
        leakage_flags.append("subject_unstable")
        score -= 12
    if "fix " in subject_lower and " by " in subject_lower:
        leakage_flags.append("subject_describes_solution")
        score -= 10
    if "rename" in subject_lower or "format" in subject_lower:
        leakage_flags.append("subject_mechanical")
        score -= 8
    review_priority = "high" if score >= 60 else "medium" if score >= 35 else "low"
    return {
        "score": score,
        "components": dict(sorted(components.items())),
        "review_priority": review_priority,
        "leakage_flags": sorted(leakage_flags),
    }


def _patch_size_score(total_patch_lines: int) -> int:
    if total_patch_lines <= 20:
        return 20
    if total_patch_lines <= 50:
        return 14
    if total_patch_lines <= 100:
        return 8
    if total_patch_lines <= 160:
        return 4
    return 0


def _quality_score_range(candidates: list[dict[str, Any]]) -> dict[str, int] | None:
    if not candidates:
        return None
    scores = [int(candidate["metadata"]["quality_score"]) for candidate in candidates]
    return {
        "min": min(scores),
        "max": max(scores),
    }


def _git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        env={**dict(os.environ), **_GIT_ENV_OVERRIDES},
        capture_output=True,
        text=True,
        check=True,
    )


def _git_text(repo: Path, args: list[str]) -> str:
    return _git(repo, args).stdout


def _git_lines(repo: Path, args: list[str]) -> list[str]:
    return [line for line in _git_text(repo, args).splitlines() if line.strip()]


def _git_optional(repo: Path, args: list[str]) -> str | None:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        env={**dict(os.environ), **_GIT_ENV_OVERRIDES},
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None
