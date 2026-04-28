from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from tinygrad_benchmarks import SCHEMA_VERSION
from tinygrad_benchmarks.compare import compare_attempts_to_gold, write_compare_outputs
from tinygrad_benchmarks.data import (
    build_index_manifest,
    build_split_manifest,
    curate_private_task_records,
    curate_rows,
    file_sha256,
    load_private_rows,
    load_rows,
    load_submissions,
    rows_sha256,
    split_rows,
    write_json,
    write_jsonl,
)
from tinygrad_benchmarks.mining import mine_history_candidates
from tinygrad_benchmarks.paths import resolve_artifact_root, resolve_runtime_root
from tinygrad_benchmarks.prompts import build_prompt_manifest, build_prompt_record
from tinygrad_benchmarks.runner import run_submissions, write_run_manifest
from tinygrad_benchmarks.scoring import load_attempts, summarize_attempts, write_summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tinygrad-benchmarks",
        description="History-mined harness for pinned tinygrad patch benchmark tasks.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    mine_parser = subparsers.add_parser(
        "mine-history",
        help="Mine candidate benchmark tasks from git history.",
    )
    mine_parser.add_argument(
        "--repo", required=True, type=Path, help="Local git repository to mine."
    )
    mine_parser.add_argument("--out", required=True, type=Path, help="Output JSONL seed rows.")
    mine_parser.add_argument(
        "--manifest-out",
        type=Path,
        default=None,
        help="Optional manifest path. Defaults to <out>.manifest.json.",
    )
    mine_parser.add_argument(
        "--repo-remote",
        default=None,
        help=(
            "Logical repo_remote value to store in mined rows. Defaults to "
            "origin URL or local path."
        ),
    )
    mine_parser.add_argument("--rev-range", default="HEAD", help="Git revision range to mine.")
    mine_parser.add_argument(
        "--max-candidates", type=int, default=None, help="Maximum accepted rows."
    )
    mine_parser.add_argument(
        "--max-files", type=int, default=8, help="Reject commits above this file count."
    )
    mine_parser.add_argument(
        "--max-source-files",
        type=int,
        default=3,
        help="Reject commits above this non-test source file count.",
    )
    mine_parser.add_argument(
        "--max-test-files",
        type=int,
        default=3,
        help="Reject commits above this changed test file count.",
    )
    mine_parser.add_argument(
        "--max-patch-lines",
        type=int,
        default=200,
        help="Reject commits above this total added+deleted line count.",
    )
    mine_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Default acceptance timeout to assign to mined rows.",
    )
    mine_parser.add_argument(
        "--allow-no-tests",
        action="store_true",
        help="Allow candidates without changed test files and fall back to full pytest.",
    )
    mine_parser.add_argument(
        "--include-source-prefix",
        action="append",
        default=[],
        help=(
            "Only treat paths under this repository-relative prefix as target source files. "
            "Repeat to allow multiple prefixes."
        ),
    )
    mine_parser.add_argument(
        "--include-test-prefix",
        action="append",
        default=[],
        help=(
            "Only treat paths under this repository-relative prefix as benchmark tests. "
            "Repeat to allow multiple prefixes."
        ),
    )
    mine_parser.add_argument(
        "--exclude-path-prefix",
        action="append",
        default=[],
        help=(
            "Reject commits that touch paths under this repository-relative prefix. "
            "Repeat to exclude multiple prefixes."
        ),
    )
    mine_parser.add_argument(
        "--progress-every",
        type=int,
        default=50,
        help="Emit progress to stderr every N scanned commits. Use 0 to disable.",
    )
    mine_parser.set_defaults(func=_cmd_mine_history)

    curate_parser = subparsers.add_parser("curate", help="Normalize task rows into index.jsonl.")
    curate_parser.add_argument(
        "--input", required=True, type=Path, help="Input JSON or JSONL task rows."
    )
    curate_parser.add_argument(
        "--out", required=True, type=Path, help="Output JSONL benchmark index."
    )
    curate_parser.add_argument(
        "--manifest-out",
        type=Path,
        default=None,
        help="Optional manifest path. Defaults to <out>.manifest.json.",
    )
    curate_parser.add_argument(
        "--private-out",
        type=Path,
        default=None,
        help="Optional maintainer-only JSON file for historical solution provenance.",
    )
    curate_parser.set_defaults(func=_cmd_curate)

    split_parser = subparsers.add_parser(
        "freeze-split",
        help="Create deterministic public and heldout splits.",
    )
    split_parser.add_argument(
        "--index", required=True, type=Path, help="Curated JSONL benchmark index."
    )
    split_parser.add_argument(
        "--out-dir", required=True, type=Path, help="Directory for split artifacts."
    )
    split_parser.add_argument("--seed", type=int, default=7, help="Selection seed.")
    split_parser.add_argument(
        "--heldout-fraction",
        type=float,
        default=0.2,
        help="Heldout fraction in [0, 1].",
    )
    split_parser.set_defaults(func=_cmd_freeze_split)

    prompt_parser = subparsers.add_parser(
        "export-prompts",
        help="Render model-visible prompt packets from a curated index.",
    )
    prompt_parser.add_argument(
        "--index", required=True, type=Path, help="Curated JSONL benchmark index."
    )
    prompt_parser.add_argument(
        "--out", required=True, type=Path, help="Output JSONL prompt packets."
    )
    prompt_parser.add_argument(
        "--manifest-out",
        type=Path,
        default=None,
        help="Optional manifest path. Defaults to <out>.manifest.json.",
    )
    prompt_parser.add_argument("--lane", default=None, help="Optional lane filter.")
    prompt_parser.set_defaults(func=_cmd_export_prompts)

    run_parser = subparsers.add_parser(
        "run",
        help="Evaluate candidate patches against the benchmark rows.",
    )
    run_parser.add_argument(
        "--index", required=True, type=Path, help="Index or frozen split JSONL."
    )
    run_parser.add_argument(
        "--submissions",
        required=True,
        type=Path,
        help="Submission JSON or JSONL file.",
    )
    run_parser.add_argument(
        "--repo-map",
        type=Path,
        default=None,
        help="Optional JSON object mapping repo_remote values to local repo paths.",
    )
    run_parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Run artifact directory. Defaults under SPECTER_ARTIFACT_ROOT or local artifacts/.",
    )
    run_parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=None,
        help=(
            "Scratch directory for sealed workspaces. Defaults under "
            "SPECTER_RUNTIME_ROOT or local tmp/."
        ),
    )
    run_parser.add_argument("--lane", default=None, help="Optional lane filter.")
    run_parser.set_defaults(func=_cmd_run)

    score_parser = subparsers.add_parser(
        "score",
        help="Recompute summary.json from attempts.jsonl.",
    )
    score_parser.add_argument("--attempts", required=True, type=Path, help="Attempt records JSONL.")
    score_parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional summary path. Defaults to <attempts dir>/summary.json.",
    )
    score_parser.set_defaults(func=_cmd_score)

    compare_parser = subparsers.add_parser(
        "compare-gold",
        help="Compare run attempts against a maintainer-only gold ledger.",
    )
    compare_parser.add_argument(
        "--attempts", required=True, type=Path, help="Attempt records JSONL."
    )
    compare_parser.add_argument(
        "--private",
        required=True,
        type=Path,
        help="Maintainer-only private task ledger or seed rows.",
    )
    compare_parser.add_argument(
        "--out-dir", required=True, type=Path, help="Directory for compare outputs."
    )
    compare_parser.set_defaults(func=_cmd_compare_gold)

    return parser


def _cmd_mine_history(args: argparse.Namespace) -> int:
    rows, manifest = mine_history_candidates(
        repo=args.repo,
        repo_remote=args.repo_remote,
        rev_range=args.rev_range,
        max_candidates=args.max_candidates,
        max_files=args.max_files,
        max_source_files=args.max_source_files,
        max_test_files=args.max_test_files,
        max_patch_lines=args.max_patch_lines,
        timeout_seconds=args.timeout_seconds,
        allow_no_tests=args.allow_no_tests,
        include_source_prefixes=tuple(args.include_source_prefix),
        include_test_prefixes=tuple(args.include_test_prefix),
        exclude_path_prefixes=tuple(args.exclude_path_prefix),
        progress_every=None if args.progress_every == 0 else args.progress_every,
    )
    out_path = args.out
    manifest_path = args.manifest_out or out_path.with_name(f"{out_path.stem}.manifest.json")
    write_jsonl(out_path, rows)
    write_json(manifest_path, manifest)
    return 0


def _cmd_curate(args: argparse.Namespace) -> int:
    raw_rows = _load_records(args.input)
    rows = curate_rows(raw_rows)
    out_path = args.out
    manifest_path = args.manifest_out or out_path.with_name(f"{out_path.stem}.manifest.json")
    write_jsonl(out_path, [row.to_record() for row in rows])
    manifest = build_index_manifest(
        rows,
        source_path=args.input,
        source_sha256=file_sha256(args.input),
    )
    write_json(manifest_path, manifest)
    if args.private_out is not None:
        private_rows = curate_private_task_records(raw_rows)
        write_json(args.private_out, {"schema_version": SCHEMA_VERSION, "rows": private_rows})
    return 0


def _cmd_freeze_split(args: argparse.Namespace) -> int:
    rows = load_rows(args.index)
    public_dev, heldout_test = split_rows(
        rows,
        seed=args.seed,
        heldout_fraction=args.heldout_fraction,
    )
    out_dir = args.out_dir
    write_jsonl(out_dir / "public_dev.jsonl", [row.to_record() for row in public_dev])
    write_jsonl(out_dir / "heldout_test.jsonl", [row.to_record() for row in heldout_test])
    manifest = build_split_manifest(
        all_rows=rows,
        public_dev=public_dev,
        heldout_test=heldout_test,
        seed=args.seed,
        heldout_fraction=args.heldout_fraction,
        index_path=args.index,
        index_sha256=rows_sha256(rows),
    )
    write_json(out_dir / "split_manifest.json", manifest)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    rows = load_rows(args.index)
    submissions = load_submissions(args.submissions)
    repo_map = _load_repo_map(args.repo_map) if args.repo_map is not None else None
    out_dir = args.out_dir or _default_run_dir()
    runtime_dir = args.runtime_dir or _default_runtime_dir(out_dir.name)
    attempts, summary, manifest = run_submissions(
        rows=rows,
        submissions=submissions,
        out_dir=out_dir,
        runtime_dir=runtime_dir,
        index_path=args.index,
        submissions_path=args.submissions,
        repo_map=repo_map,
        lane=args.lane,
    )
    manifest.update(
        {
            "generated_at": _utc_now(),
            "attempt_count": len(attempts),
            "success_count": summary["success_count"],
            "summary_sha256": file_sha256(out_dir / "summary.json"),
        }
    )
    write_run_manifest(out_dir / "run_manifest.json", manifest)
    return 0


def _cmd_export_prompts(args: argparse.Namespace) -> int:
    rows = load_rows(args.index)
    if args.lane is not None:
        rows = [row for row in rows if row.lane == args.lane]
    out_path = args.out
    manifest_path = args.manifest_out or out_path.with_name(f"{out_path.stem}.manifest.json")
    write_jsonl(out_path, [build_prompt_record(row) for row in rows])
    write_json(manifest_path, build_prompt_manifest(rows, index_path=args.index))
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    attempts = load_attempts(args.attempts)
    summary = summarize_attempts(attempts)
    out_path = args.out or (args.attempts.parent / "summary.json")
    write_summary(out_path, summary)
    return 0


def _cmd_compare_gold(args: argparse.Namespace) -> int:
    attempts = load_attempts(args.attempts)
    private_rows = load_private_rows(args.private)
    report_rows, summary = compare_attempts_to_gold(attempts, private_rows)
    write_compare_outputs(out_dir=args.out_dir, report_rows=report_rows, summary=summary)
    return 0


def _load_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise ValueError(f"{path} JSONL rows must be objects.")
            records.append(dict(value))
        return records
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return [dict(item) for item in value]
    if isinstance(value, dict) and isinstance(value.get("rows"), list):
        return [dict(item) for item in value["rows"]]
    raise ValueError(f"{path} must contain a top-level list, a rows object, or JSONL.")


def _load_repo_map(path: Path) -> dict[str, str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    mapping: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{path} includes an invalid repo_remote key.")
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{path} includes an invalid repo path for {key!r}.")
        mapping[key.strip()] = item.strip()
    return mapping


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_run_dir() -> Path:
    root = Path(__file__).resolve().parents[1]
    fallback = root / "artifacts"
    artifact_root = resolve_artifact_root(fallback)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return artifact_root / "runs" / f"tinygrad-run-{stamp}"


def _default_runtime_dir(run_name: str) -> Path:
    root = Path(__file__).resolve().parents[1]
    fallback = root / "tmp"
    runtime_root = resolve_runtime_root(fallback)
    return runtime_root / "runs" / run_name
