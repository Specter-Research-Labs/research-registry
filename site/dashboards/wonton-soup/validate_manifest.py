#!/usr/bin/env python3
"""Validate Wonton Soup parquet dashboard manifest and referenced files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

TABLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TABLE_FILE_RE = re.compile(r"^[a-z][a-z0-9_]*\.parquet$")


def validate_manifest(root: Path) -> dict[str, Any]:
    manifest_path = (root / "dashboard_manifest.json").resolve()
    if not manifest_path.exists():
        raise RuntimeError(f"Manifest not found: {manifest_path}")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object in {manifest_path}")

    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, int):
        raise RuntimeError("Manifest field `schema_version` must be an integer")

    compiled_at = payload.get("compiled_at")
    if compiled_at is not None and not isinstance(compiled_at, str):
        raise RuntimeError("Manifest field `compiled_at` must be a string when present")

    tables = payload.get("tables")
    if not isinstance(tables, list) or not tables:
        raise RuntimeError("Manifest field `tables` must be a non-empty list")

    seen_names: set[str] = set()
    for idx, entry in enumerate(tables):
        if not isinstance(entry, dict):
            raise RuntimeError(f"`tables[{idx}]` must be an object")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise RuntimeError(f"`tables[{idx}].name` must be a non-empty string")
        if not TABLE_NAME_RE.match(name):
            raise RuntimeError(
                f"`tables[{idx}].name` = {name!r} is not a safe SQL identifier"
            )
        if name in seen_names:
            raise RuntimeError(f"Duplicate table name: {name}")
        seen_names.add(name)
        file = entry.get("file")
        if not isinstance(file, str) or not file:
            raise RuntimeError(f"`tables[{idx}].file` must be a non-empty string")
        if not TABLE_FILE_RE.match(file):
            raise RuntimeError(
                f"`tables[{idx}].file` = {file!r} is not a safe parquet filename"
            )
        file_path = (root / file).resolve()
        if not file_path.exists():
            raise RuntimeError(f"Parquet file missing for table {name}: {file_path}")

    return {
        "manifest_path": str(manifest_path),
        "table_count": len(tables),
        "schema_version": schema_version,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Wonton Soup dashboard manifest")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parent),
        help="Dashboard data root directory (default: this file's directory)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    report = validate_manifest(root)
    print(
        f"manifest-ok path={report['manifest_path']} "
        f"tables={report['table_count']} schema={report['schema_version']}"
    )


if __name__ == "__main__":
    main()
