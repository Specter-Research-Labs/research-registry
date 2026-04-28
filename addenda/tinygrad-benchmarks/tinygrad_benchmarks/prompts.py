from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, Sequence

from tinygrad_benchmarks import SCHEMA_VERSION
from tinygrad_benchmarks.data import BenchmarkRow, rows_sha256

PROMPT_VERSION = "prompt_v1"


def build_prompt_record(row: BenchmarkRow) -> dict[str, Any]:
    prompt_lines = [
        "You are working in a sealed local checkout of the repository at a fixed hidden commit.",
        row.task_statement,
        "",
        "Target paths:",
        *[f"- {path}" for path in row.target_paths],
        "",
        "Validation:",
        f"- Run `{shlex.join(row.acceptance_command)}` from `{row.acceptance_cwd}`.",
        "",
        (
            "Return a unified diff patch that fixes the task. "
            "Do not rely on git history or network access."
        ),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "item_id": row.item_id,
        "task_id": row.task_id,
        "lane": row.lane,
        "task_statement": row.task_statement,
        "target_paths": list(row.target_paths),
        "acceptance_command": list(row.acceptance_command),
        "acceptance_cwd": row.acceptance_cwd,
        "timeout_seconds": row.timeout_seconds,
        "required_capabilities": list(row.required_capabilities),
        "required_env": dict(row.required_env),
        "prompt": "\n".join(prompt_lines).strip(),
    }


def build_prompt_manifest(rows: Sequence[BenchmarkRow], *, index_path: Path) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "prompt_count": len(rows),
        "index_path": str(index_path),
        "index_sha256": rows_sha256(rows),
        "item_ids": [row.item_id for row in rows],
    }
