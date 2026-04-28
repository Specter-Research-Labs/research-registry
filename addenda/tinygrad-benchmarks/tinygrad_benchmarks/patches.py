from __future__ import annotations

from typing import Any


def patch_metrics(patch: str) -> dict[str, Any]:
    touched_paths: list[str] = []
    added_lines: list[str] = []
    removed_lines: list[str] = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                raw_path = parts[3]
                if raw_path.startswith("b/"):
                    touched_paths.append(raw_path[2:])
                else:
                    touched_paths.append(raw_path)
            continue
        if line.startswith("+++ ") or line.startswith("--- ") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added_lines.append(_normalize_patch_line(line[1:]))
            continue
        if line.startswith("-"):
            removed_lines.append(_normalize_patch_line(line[1:]))
    normalized_paths = sorted({path for path in touched_paths if path})
    normalized_added = sorted({line for line in added_lines if line})
    normalized_removed = sorted({line for line in removed_lines if line})
    return {
        "touched_paths": normalized_paths,
        "added_line_count": len(added_lines),
        "removed_line_count": len(removed_lines),
        "patch_line_count": len(added_lines) + len(removed_lines),
        "normalized_added_lines": normalized_added,
        "normalized_removed_lines": normalized_removed,
        "normalized_changed_lines": sorted(
            {f"+:{line}" for line in normalized_added}
            | {f"-:{line}" for line in normalized_removed}
        ),
    }


def jaccard_similarity(left: set[str], right: set[str]) -> float | None:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return None
    return len(left & right) / len(union)


def _normalize_patch_line(value: str) -> str:
    return " ".join(value.strip().split())
