from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tinygrad_benchmarks import SCHEMA_VERSION


def load_attempts(path: Path) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        value = json.loads(stripped)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no} must be a JSON object.")
        attempts.append(dict(value))
    return attempts


def summarize_attempts(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    error_kind_counts: dict[str, int] = {}
    lane_counts: dict[str, int] = {}
    success_count = 0
    timeout_count = 0
    apply_failure_count = 0
    acceptance_failure_count = 0
    item_successes: dict[str, bool] = {}
    for attempt in attempts:
        item_id = str(attempt["item_id"])
        lane = str(attempt["lane"])
        success = bool(attempt["success"])
        error_kind = str(attempt["error_kind"])
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
        error_kind_counts[error_kind] = error_kind_counts.get(error_kind, 0) + 1
        item_successes[item_id] = item_successes.get(item_id, False) or success
        if success:
            success_count += 1
        if error_kind == "acceptance_timeout":
            timeout_count += 1
            acceptance_failure_count += 1
        elif error_kind in {"patch_check_failed", "patch_apply_failed"}:
            apply_failure_count += 1
        elif error_kind == "acceptance_failed":
            acceptance_failure_count += 1
    attempt_count = len(attempts)
    item_count = len(item_successes)
    item_success_count = sum(1 for success in item_successes.values() if success)
    return {
        "schema_version": SCHEMA_VERSION,
        "attempt_count": attempt_count,
        "item_count": item_count,
        "success_count": success_count,
        "failed_count": attempt_count - success_count,
        "success_rate": _rate(success_count, attempt_count),
        "item_success_count": item_success_count,
        "item_success_rate": _rate(item_success_count, item_count),
        "timeout_count": timeout_count,
        "apply_failure_count": apply_failure_count,
        "acceptance_failure_count": acceptance_failure_count,
        "error_kind_counts": dict(sorted(error_kind_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
    }


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
