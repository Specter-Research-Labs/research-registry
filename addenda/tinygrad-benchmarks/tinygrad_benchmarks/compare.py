from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from tinygrad_benchmarks import SCHEMA_VERSION
from tinygrad_benchmarks.patches import jaccard_similarity, patch_metrics


def compare_attempts_to_gold(
    attempts: Sequence[dict[str, Any]],
    private_rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gold_by_item = {str(row["item_id"]): dict(row) for row in private_rows}
    report_rows: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    item_exact_match: dict[str, bool] = {}
    item_success: dict[str, bool] = {}
    for attempt in attempts:
        item_id = str(attempt["item_id"])
        gold_row = gold_by_item.get(item_id)
        gold_patch_sha256 = _gold_patch_sha256(gold_row) if gold_row is not None else None
        gold_metrics = _gold_patch_metrics(gold_row)
        exact_match = (
            gold_patch_sha256 is not None and attempt.get("patch_sha256") == gold_patch_sha256
        )
        attempt_paths = {str(path) for path in attempt.get("patch_touched_paths", [])}
        gold_paths = set(gold_metrics["touched_paths"])
        path_jaccard = jaccard_similarity(attempt_paths, gold_paths)
        attempt_changed_lines = {str(line) for line in attempt.get("normalized_changed_lines", [])}
        gold_changed_lines = set(gold_metrics["normalized_changed_lines"])
        line_jaccard = jaccard_similarity(attempt_changed_lines, gold_changed_lines)
        close_match = _is_close_gold_match(
            exact_match=exact_match,
            path_jaccard=path_jaccard,
            line_jaccard=line_jaccard,
        )
        success = bool(attempt["success"])
        category = _category_for_attempt(
            success=success,
            has_gold=gold_row is not None,
            exact_match=exact_match,
            close_match=close_match,
        )
        item_exact_match[item_id] = item_exact_match.get(item_id, False) or exact_match
        item_success[item_id] = item_success.get(item_id, False) or success
        category_counts[category] = category_counts.get(category, 0) + 1
        report_rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "item_id": item_id,
                "task_id": attempt.get("task_id"),
                "candidate_id": attempt.get("candidate_id"),
                "success": success,
                "error_kind": attempt.get("error_kind"),
                "patch_sha256": attempt.get("patch_sha256"),
                "gold_patch_sha256": gold_patch_sha256,
                "gold_commit": gold_row.get("gold_commit") if gold_row is not None else None,
                "exact_gold_patch_match": exact_match,
                "close_gold_match": close_match,
                "patch_path_jaccard": path_jaccard,
                "patch_line_jaccard": line_jaccard,
                "gold_touched_paths": gold_metrics["touched_paths"],
                "category": category,
                "historical_solution_refs": (
                    list(gold_row.get("historical_solution_refs", []))
                    if gold_row is not None
                    else []
                ),
            }
        )
    summary = {
        "schema_version": SCHEMA_VERSION,
        "attempt_count": len(attempts),
        "item_count": len({str(attempt["item_id"]) for attempt in attempts}),
        "gold_item_count": len(gold_by_item),
        "category_counts": dict(sorted(category_counts.items())),
        "item_exact_gold_match_count": sum(1 for matched in item_exact_match.values() if matched),
        "attempt_close_gold_match_count": sum(
            1 for row in report_rows if bool(row["close_gold_match"])
        ),
        "mean_patch_path_jaccard": _mean(
            [
                row["patch_path_jaccard"]
                for row in report_rows
                if row["patch_path_jaccard"] is not None
            ]
        ),
        "mean_patch_line_jaccard": _mean(
            [
                row["patch_line_jaccard"]
                for row in report_rows
                if row["patch_line_jaccard"] is not None
            ]
        ),
        "item_success_count": sum(1 for matched in item_success.values() if matched),
        "item_success_exact_gold_count": sum(
            1
            for item_id, matched in item_exact_match.items()
            if matched and item_success.get(item_id, False)
        ),
    }
    return report_rows, summary


def write_compare_outputs(
    *,
    out_dir: Path,
    report_rows: Sequence[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "compare_report.jsonl"
    summary_path = out_dir / "compare_summary.json"
    lines = [json.dumps(row, sort_keys=True, separators=(",", ":")) for row in report_rows]
    report_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _gold_patch_sha256(row: dict[str, Any] | None) -> str | None:
    if row is None:
        return None
    value = row.get("gold_patch_sha256")
    if isinstance(value, str) and value.strip():
        return value.strip()
    patch = row.get("gold_patch")
    if isinstance(patch, str) and patch.strip():
        return hashlib.sha256(patch.encode("utf-8")).hexdigest()
    return None


def _gold_patch_metrics(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {
            "touched_paths": [],
            "normalized_changed_lines": [],
        }
    patch = row.get("gold_patch")
    if isinstance(patch, str) and patch.strip():
        return patch_metrics(patch)
    return {
        "touched_paths": [],
        "normalized_changed_lines": [],
    }


def _is_close_gold_match(
    *,
    exact_match: bool,
    path_jaccard: float | None,
    line_jaccard: float | None,
) -> bool:
    if exact_match:
        return True
    if path_jaccard is None or line_jaccard is None:
        return False
    return path_jaccard >= 0.5 and line_jaccard >= 0.3


def _category_for_attempt(
    *,
    success: bool,
    has_gold: bool,
    exact_match: bool,
    close_match: bool,
) -> str:
    if not has_gold:
        return "no_gold_record"
    if success and exact_match:
        return "success_exact_gold"
    if success and close_match:
        return "success_close_gold"
    if success:
        return "success_nonexact"
    if exact_match:
        return "failure_exact_gold"
    if close_match:
        return "failure_close_gold"
    return "failure_nonexact"


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)
