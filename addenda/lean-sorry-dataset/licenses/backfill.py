from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dataset.index import github_repo_slug, is_open_license, lookup_repo_license

LicenseResolver = Callable[[str], tuple[str | None, str | None, str | None]]


@dataclass(frozen=True)
class BackfillConfig:
    require_open_license: bool
    github_token: str | None


@dataclass(frozen=True)
class BackfillStats:
    rows_input: int
    rows_written: int
    rows_skipped_non_open_license: int
    repos_queried: int
    repos_resolved: int
    repos_with_errors: int
    by_license: dict[str, int]
    license_lookup_errors: dict[str, str]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_index_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            obj = json.loads(text)
            if not isinstance(obj, dict):
                raise ValueError(f"line {line_no}: expected JSON object")
            rows.append(obj)
    return rows


def write_rows_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_backfill_manifest(
    *,
    path: Path,
    source_index: Path,
    source_index_sha256: str,
    config: BackfillConfig,
    stats: BackfillStats,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "source": {
            "index_path": str(source_index),
            "index_sha256": source_index_sha256,
        },
        "config": {
            "require_open_license": config.require_open_license,
        },
        "stats": {
            "rows_input": stats.rows_input,
            "rows_written": stats.rows_written,
            "rows_skipped_non_open_license": stats.rows_skipped_non_open_license,
            "repos_queried": stats.repos_queried,
            "repos_resolved": stats.repos_resolved,
            "repos_with_errors": stats.repos_with_errors,
            "by_license": stats.by_license,
            "license_lookup_errors": stats.license_lookup_errors,
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def backfill_index_rows(
    *,
    rows: list[dict[str, Any]],
    config: BackfillConfig,
    license_resolver: LicenseResolver | None = None,
) -> tuple[list[dict[str, Any]], BackfillStats]:
    resolver = license_resolver
    if resolver is None:

        def _resolver(slug: str) -> tuple[str | None, str | None, str | None]:
            return lookup_repo_license(slug, github_token=config.github_token)

        resolver = _resolver

    license_cache: dict[str, tuple[str | None, str | None, str | None]] = {}
    license_lookup_errors: dict[str, str] = {}
    rows_out: list[dict[str, Any]] = []
    rows_skipped_non_open_license = 0

    for row in rows:
        out_row = dict(row)
        repo_slug_value = out_row.get("repo_slug")
        repo_slug: str | None
        if isinstance(repo_slug_value, str) and repo_slug_value:
            repo_slug = repo_slug_value
        else:
            repo_remote_value = out_row.get("repo_remote")
            repo_slug = (
                github_repo_slug(repo_remote_value) if isinstance(repo_remote_value, str) else None
            )
        out_row["repo_slug"] = repo_slug

        spdx_value = out_row.get("repo_license_spdx")
        repo_license_spdx = spdx_value if isinstance(spdx_value, str) and spdx_value else None

        url_value = out_row.get("repo_license_url")
        repo_license_url = url_value if isinstance(url_value, str) and url_value else None

        open_value = out_row.get("repo_license_open")
        if type(open_value) is bool:
            repo_license_open: bool | None = open_value
        else:
            repo_license_open = None

        should_resolve = (
            repo_slug is not None
            and (repo_license_spdx is None or repo_license_url is None or repo_license_open is None)
        )
        if should_resolve:
            repo_slug_key = repo_slug
            if repo_slug_key is None:
                raise RuntimeError("repo_slug must be set when should_resolve is true")
            if repo_slug_key not in license_cache:
                license_cache[repo_slug_key] = resolver(repo_slug_key)
            resolved_spdx, resolved_url, resolve_error = license_cache[repo_slug_key]
            if resolved_spdx is not None:
                repo_license_spdx = resolved_spdx
            if resolved_url is not None:
                repo_license_url = resolved_url
            if resolve_error is not None and repo_slug_key not in license_lookup_errors:
                license_lookup_errors[repo_slug_key] = resolve_error
            repo_license_open = is_open_license(repo_license_spdx)

        if config.require_open_license and repo_license_open is not True:
            rows_skipped_non_open_license += 1
            continue

        out_row["repo_license_spdx"] = repo_license_spdx
        out_row["repo_license_url"] = repo_license_url
        out_row["repo_license_open"] = repo_license_open
        rows_out.append(out_row)

    by_license: dict[str, int] = {}
    for row in rows_out:
        spdx = row.get("repo_license_spdx")
        key = spdx if isinstance(spdx, str) and spdx else "unresolved"
        by_license[key] = by_license.get(key, 0) + 1

    repos_resolved = sum(
        1
        for resolved_spdx, _, _ in license_cache.values()
        if resolved_spdx is not None and resolved_spdx != ""
    )
    stats = BackfillStats(
        rows_input=len(rows),
        rows_written=len(rows_out),
        rows_skipped_non_open_license=rows_skipped_non_open_license,
        repos_queried=len(license_cache),
        repos_resolved=repos_resolved,
        repos_with_errors=len(license_lookup_errors),
        by_license=dict(sorted(by_license.items())),
        license_lookup_errors=dict(sorted(license_lookup_errors.items())),
    )
    return rows_out, stats


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lean-sorry-license-backfill",
        description="Backfill GitHub license metadata in an existing benchmark index.",
    )
    parser.add_argument("--index", required=True, type=Path, help="Input index JSONL path.")
    parser.add_argument("--out", required=True, type=Path, help="Output index JSONL path.")
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=None,
        help="Output manifest path (default: <out>.manifest.json).",
    )
    parser.add_argument(
        "--require-open-license",
        action="store_true",
        help="Drop rows not resolved to open licenses after backfill.",
    )
    parser.add_argument(
        "--github-token",
        default=None,
        help="Optional GitHub API token for license lookups.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = load_index_rows(args.index)
    rows_out, stats = backfill_index_rows(
        rows=rows,
        config=BackfillConfig(
            require_open_license=args.require_open_license,
            github_token=args.github_token,
        ),
    )
    write_rows_jsonl(args.out, rows_out)
    manifest_out = args.manifest_out or args.out.with_suffix(args.out.suffix + ".manifest.json")
    write_backfill_manifest(
        path=manifest_out,
        source_index=args.index,
        source_index_sha256=file_sha256(args.index),
        config=BackfillConfig(
            require_open_license=args.require_open_license,
            github_token=args.github_token,
        ),
        stats=stats,
    )
    print(f"index={args.index}")
    print(f"rows_input={stats.rows_input}")
    print(f"rows_written={stats.rows_written}")
    print(f"rows_skipped_non_open_license={stats.rows_skipped_non_open_license}")
    print(f"repos_queried={stats.repos_queried}")
    print(f"repos_resolved={stats.repos_resolved}")
    print(f"repos_with_errors={stats.repos_with_errors}")
    print(f"out={args.out}")
    print(f"manifest={manifest_out}")
    return 0
