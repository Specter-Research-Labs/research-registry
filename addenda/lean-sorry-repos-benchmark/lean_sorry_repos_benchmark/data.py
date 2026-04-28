from __future__ import annotations

import hashlib
import json
import random
import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GOAL_MARKER = "⊢"


@dataclass(frozen=True)
class BenchmarkRow:
    item_id: str
    repo_remote: str
    repo_commit: str
    repo_lean_version: str | None
    location_path: str
    location_start_line: int
    location_start_column: int
    location_end_line: int
    location_end_column: int
    goal_sha256: str | None
    goal_text: str
    goal_bucket: str
    source_url: str
    raw: dict[str, Any]


def _is_core_easy_goal(goal_text: str) -> bool:
    stripped = goal_text.strip()
    if not stripped:
        return False
    if len(stripped) > 220:
        return False
    lines = [line for line in stripped.splitlines() if line.strip()]
    if len(lines) > 7:
        return False
    if GOAL_MARKER not in stripped:
        return False
    marker_line_idx = next((i for i, line in enumerate(lines) if GOAL_MARKER in line), None)
    if marker_line_idx is None:
        return False
    context_lines = lines[:marker_line_idx]
    if len(context_lines) > 4:
        return False
    allowed_non_ascii = {GOAL_MARKER}
    allowed_ascii = set(string.printable)
    for ch in stripped:
        if ch in allowed_non_ascii:
            continue
        if ch not in allowed_ascii:
            return False
    if "sorry" in stripped.lower() or "admit" in stripped.lower():
        return False
    return True


def _validate_location_path(*, line_no: int, location_path: str) -> None:
    prefix = f"line {line_no}: invalid location_path '{location_path}': "
    if Path(location_path).is_absolute():
        raise ValueError(
            prefix
            + "absolute paths are not allowed; "
            "use a repository-relative path like 'src/Foo.lean'"
        )
    if location_path.startswith("\\\\") or re.match(r"^[A-Za-z]:[\\\\/]", location_path):
        raise ValueError(
            prefix
            + "absolute paths are not allowed; "
            "use a repository-relative path like 'src/Foo.lean'"
        )
    segments = location_path.replace("\\", "/").split("/")
    if any(segment == "" for segment in segments):
        raise ValueError(
            prefix
            + "empty path segments are not allowed; "
            "use a normalized repository-relative path like 'src/Foo.lean'"
        )
    if any(segment == ".." for segment in segments):
        raise ValueError(
            prefix
            + "parent traversal ('..') is not allowed; "
            "use a path rooted inside the repository"
        )


def load_rows(index_path: Path) -> list[BenchmarkRow]:
    rows: list[BenchmarkRow] = []
    with index_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            obj = json.loads(text)
            if not isinstance(obj, dict):
                raise ValueError(f"line {line_no}: expected JSON object")
            item_id = obj.get("item_id")
            repo_remote = obj.get("repo_remote")
            repo_commit = obj.get("repo_commit")
            repo_lean_version = obj.get("repo_lean_version")
            location_path = obj.get("location_path")
            location_start_line = obj.get("location_start_line")
            location_start_column = obj.get("location_start_column")
            location_end_line = obj.get("location_end_line")
            location_end_column = obj.get("location_end_column")
            goal_text = obj.get("goal_text")
            source_url = obj.get("source_url")
            goal_sha256 = obj.get("goal_sha256")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"line {line_no}: invalid item_id")
            if not isinstance(repo_remote, str) or not repo_remote:
                raise ValueError(f"line {line_no}: invalid repo_remote")
            if not isinstance(repo_commit, str) or not repo_commit:
                raise ValueError(f"line {line_no}: invalid repo_commit")
            if repo_lean_version is not None and not isinstance(repo_lean_version, str):
                raise ValueError(f"line {line_no}: invalid repo_lean_version")
            if not isinstance(location_path, str) or not location_path:
                raise ValueError(f"line {line_no}: invalid location_path")
            _validate_location_path(line_no=line_no, location_path=location_path)
            if not isinstance(location_start_line, int) or location_start_line <= 0:
                raise ValueError(f"line {line_no}: invalid location_start_line")
            if not isinstance(location_start_column, int) or location_start_column < 0:
                raise ValueError(f"line {line_no}: invalid location_start_column")
            if not isinstance(location_end_line, int) or location_end_line <= 0:
                raise ValueError(f"line {line_no}: invalid location_end_line")
            if not isinstance(location_end_column, int) or location_end_column < 0:
                raise ValueError(f"line {line_no}: invalid location_end_column")
            if not isinstance(source_url, str) or not source_url:
                raise ValueError(f"line {line_no}: invalid source_url")
            if not isinstance(goal_text, str) or not goal_text:
                raise ValueError(
                    f"line {line_no}: missing goal_text; rebuild dataset with --include-goal-text"
                )
            if goal_sha256 is not None and not isinstance(goal_sha256, str):
                raise ValueError(f"line {line_no}: invalid goal_sha256")
            rows.append(
                BenchmarkRow(
                    item_id=item_id,
                    repo_remote=repo_remote,
                    repo_commit=repo_commit,
                    repo_lean_version=repo_lean_version,
                    location_path=location_path,
                    location_start_line=location_start_line,
                    location_start_column=location_start_column,
                    location_end_line=location_end_line,
                    location_end_column=location_end_column,
                    goal_sha256=goal_sha256,
                    goal_text=goal_text,
                    goal_bucket="core_easy" if _is_core_easy_goal(goal_text) else "full",
                    source_url=source_url,
                    raw=obj,
                )
            )
    rows.sort(key=lambda row: row.item_id)
    return rows


def select_rows(
    rows: list[BenchmarkRow],
    *,
    split_policy: str,
    seed: int,
    repo_holdout_fraction: float,
    goal_slice: str,
    max_items: int | None,
) -> list[BenchmarkRow]:
    if split_policy not in {"all", "repo_holdout"}:
        raise ValueError(f"unknown split_policy: {split_policy}")
    if goal_slice not in {"all", "core_easy", "non_core_easy"}:
        raise ValueError(f"unknown goal_slice: {goal_slice}")
    selected = rows
    if goal_slice == "core_easy":
        selected = [row for row in selected if row.goal_bucket == "core_easy"]
    elif goal_slice == "non_core_easy":
        selected = [row for row in selected if row.goal_bucket != "core_easy"]
    if split_policy == "repo_holdout":
        if repo_holdout_fraction <= 0.0 or repo_holdout_fraction >= 1.0:
            raise ValueError("repo_holdout_fraction must be in (0,1)")

        def is_holdout(repo_remote: str) -> bool:
            digest = hashlib.sha256(f"{seed}:{repo_remote}".encode("utf-8")).hexdigest()
            score = int(digest[:8], 16) / 0xFFFFFFFF
            return score < repo_holdout_fraction

        selected = [row for row in selected if is_holdout(row.repo_remote)]

    if max_items is not None:
        rnd = random.Random(seed)
        selected = list(selected)
        rnd.shuffle(selected)
        selected = selected[:max_items]
    selected.sort(key=lambda row: row.item_id)
    return selected


def selected_rows_hash(rows: list[BenchmarkRow]) -> str:
    payload = "\n".join(row.item_id for row in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
