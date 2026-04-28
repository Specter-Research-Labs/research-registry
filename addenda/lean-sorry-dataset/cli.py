from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from dataset.index import (
    BuildConfig,
    build_index_rows,
    extract_sorries,
    load_snapshot,
    write_jsonl,
    write_manifest,
)
from licenses.backfill import (
    BackfillConfig,
    backfill_index_rows,
    file_sha256,
    load_index_rows,
    write_backfill_manifest,
)


def _default_manifest_out(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".manifest.json")


def _github_token(env_name: str) -> str | None:
    value = os.environ.get(env_name)
    if value is None:
        return None
    return value.strip() or None


def _build_index_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "build-index",
        help="Build a deterministic benchmark index from a SorryDB-compatible snapshot.",
        description=(
            "Build a deterministic benchmark index from a SorryDB-compatible JSON snapshot "
            "(`sorry_database.json` or `deduplicated_sorries.json`)."
        ),
    )
    parser.add_argument(
        "--snapshot",
        required=True,
        help="Snapshot path or URL.",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output JSONL path for benchmark rows.",
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=None,
        help="Output manifest path (default: <out>.manifest.json).",
    )
    parser.add_argument(
        "--include-goal-text",
        action="store_true",
        help="Include raw goal text in output rows (default: only goal hash).",
    )
    parser.add_argument(
        "--resolve-github-license",
        action="store_true",
        help="Resolve GitHub repository license metadata via GitHub API.",
    )
    parser.add_argument(
        "--require-open-license",
        action="store_true",
        help="Drop rows whose repository license is not resolved to an open SPDX id.",
    )
    parser.add_argument(
        "--skip-invalid",
        action="store_true",
        help="Skip malformed rows instead of failing fast.",
    )
    parser.add_argument(
        "--github-token-env",
        default="GITHUB_TOKEN",
        help="Environment variable used for GitHub API token when resolving licenses.",
    )
    parser.set_defaults(run=_run_build_index)


def _license_backfill_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "license-backfill",
        help="Backfill GitHub license metadata in an existing benchmark index.",
        description=(
            "Backfill GitHub license metadata in an existing benchmark index "
            "without rebuilding from snapshot."
        ),
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
        "--github-token-env",
        default="GITHUB_TOKEN",
        help="Environment variable used for GitHub API token.",
    )
    parser.set_defaults(run=_run_license_backfill)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="lean-sorry-dataset")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _build_index_parser(subparsers)
    _license_backfill_parser(subparsers)
    args = parser.parse_args(argv)
    if (
        args.command == "build-index"
        and args.require_open_license
        and not args.resolve_github_license
    ):
        raise SystemExit("--require-open-license requires --resolve-github-license")
    return args


def _run_build_index(args: argparse.Namespace) -> int:
    manifest_out = args.manifest_out or _default_manifest_out(args.out)
    config = BuildConfig(
        include_goal_text=args.include_goal_text,
        resolve_github_license=args.resolve_github_license,
        require_open_license=args.require_open_license,
        strict=not args.skip_invalid,
        github_token=_github_token(args.github_token_env),
    )
    payload, raw_snapshot = load_snapshot(args.snapshot)
    sorries = extract_sorries(payload)
    rows, stats = build_index_rows(sorries=sorries, config=config)
    write_jsonl(args.out, rows)
    write_manifest(
        path=manifest_out,
        source_snapshot=args.snapshot,
        source_snapshot_sha256=hashlib.sha256(raw_snapshot).hexdigest(),
        config=config,
        stats=stats,
    )

    print(f"snapshot={args.snapshot}")
    print(f"rows={stats.rows_written}")
    print(f"invalid_rows={stats.rows_invalid}")
    print(f"skipped_non_open_license={stats.rows_skipped_non_open_license}")
    print(f"out={args.out}")
    print(f"manifest={manifest_out}")
    return 0


def _run_license_backfill(args: argparse.Namespace) -> int:
    manifest_out = args.manifest_out or _default_manifest_out(args.out)
    config = BackfillConfig(
        require_open_license=args.require_open_license,
        github_token=_github_token(args.github_token_env),
    )
    rows = load_index_rows(args.index)
    rows_out, stats = backfill_index_rows(rows=rows, config=config)
    write_jsonl(args.out, rows_out)
    write_backfill_manifest(
        path=manifest_out,
        source_index=args.index,
        source_index_sha256=file_sha256(args.index),
        config=config,
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


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
