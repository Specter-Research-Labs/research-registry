# ruff: noqa: I001
from __future__ import annotations

import argparse
import json
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from shared import (
    corpus_candidates,
    import_wonton_symbol,
    iter_jsonl_objects,
    iter_variant_prefixes,
    load_json_object,
    resolve_repo_root,
    resolve_single_provider_run,
    trace_path_for_prefix,
    write_json_object,
)

SYSTEM_PROMPT = """/- You are proving a theorem in Lean 4.
You are given the following information:
- The file contents up to the current tactic, inside [CTX]...[/CTX]
- The current proof state, inside [STATE]...[/STATE]

Your task is to generate the next tactic in the proof.
Put the next tactic inside [TAC]...[/TAC]
-/
"""

DEFAULT_IMPORTS = "import Mathlib\nopen BigOperators Real Nat Topology"


@dataclass(frozen=True)
class BuildStats:
    rows_written: int
    run_counts: dict[str, int]
    theorem_counts: dict[str, int]
    variant_counts: dict[str, int]
    unloadable_runs: dict[str, list[str]]
    examples_skipped_missing_statement: int
    examples_skipped_bad_shape: int


def _split_csv(value: str | None) -> set[str]:
    if value is None:
        return set()
    values = [v.strip() for v in value.split(",")]
    return {v for v in values if v}


def _float_or_none(x: Any) -> float | None:
    if isinstance(x, (int, float)):
        return float(x)
    return None


def _build_ctx(theorem_statement: str | None) -> str:
    if theorem_statement is None:
        return DEFAULT_IMPORTS
    header = theorem_statement.replace("sorry", "").rstrip()
    return f"{DEFAULT_IMPORTS}\n\n{header}"


def _build_prompt(theorem_statement: str | None, goal_type: str) -> str:
    ctx = _build_ctx(theorem_statement)
    state = f"⊢ {goal_type}"
    return f"{SYSTEM_PROMPT}[CTX]\n{ctx}\n[/CTX]\n[STATE]\n{state}\n[/STATE]\n[TAC]\n"


def build_dataset(
    *,
    repo_root: Path,
    run_dirs: list[Path],
    out_path: Path,
    provider: str | None,
    variants: set[str],
    label_policy: str,
    max_rows: int | None,
    dedupe: bool,
    skip_unloadable_runs: bool,
) -> BuildStats:
    committed_tactic_by_mvar = import_wonton_symbol(
        repo_root, "analysis.learning_common", "committed_tactic_by_mvar"
    )
    load_corpus = import_wonton_symbol(repo_root, "orchestrator.lean", "load_corpus")

    theorem_statements_by_corpus: dict[str, dict[str, str | None]] = {}
    run_counts: dict[str, int] = defaultdict(int)
    unloadable_runs: dict[str, list[str]] = {}
    theorem_counts: dict[str, int] = defaultdict(int)
    variant_counts: dict[str, int] = defaultdict(int)
    skipped_missing_statement = 0
    skipped_bad_shape = 0
    rows_written = 0
    seen_keys: set[str] = set()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as out:
        for run_dir in run_dirs:
            single_run_dir = resolve_single_provider_run(run_dir, provider)
            run_config = load_json_object(single_run_dir / "run_config.json")
            theorem_statements: dict[str, str | None] | None = None
            corpus_for_loading = ""
            load_error: Exception | None = None
            for candidate in corpus_candidates(run_config):
                theorem_statements = theorem_statements_by_corpus.get(candidate)
                if theorem_statements is not None:
                    corpus_for_loading = candidate
                    break
                try:
                    theorems, _, _ = load_corpus(candidate)
                except Exception as exc:  # pragma: no cover - dependent on external corpus state
                    load_error = exc
                    continue
                theorem_statements = {t.name: t.statement for t in theorems}
                theorem_statements_by_corpus[candidate] = theorem_statements
                corpus_for_loading = candidate
                break
            if theorem_statements is None:
                attempted = corpus_candidates(run_config)
                if skip_unloadable_runs:
                    unloadable_runs[str(single_run_dir / "run_config.json")] = attempted
                    continue
                raise ValueError(
                    "Could not load corpus for "
                    f"{single_run_dir / 'run_config.json'}; tried {attempted}"
                ) from load_error

            run_id = run_config.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                run_id = str(single_run_dir)

            theorem_dirs = sorted(p for p in single_run_dir.iterdir() if p.is_dir())
            for theorem_dir in theorem_dirs:
                theorem = theorem_dir.name
                statement = theorem_statements.get(theorem)
                if statement is None:
                    skipped_missing_statement += 1
                    continue

                for prefix in iter_variant_prefixes(theorem_dir):
                    if variants and prefix not in variants:
                        continue
                    trace_path = trace_path_for_prefix(theorem_dir, prefix)
                    tree_path = theorem_dir / f"{prefix}_mcts_tree.json"
                    if not tree_path.exists():
                        continue

                    tree = load_json_object(tree_path)
                    committed_by_mvar = committed_tactic_by_mvar(tree)

                    for record in iter_jsonl_objects(trace_path):
                        if record.get("event") != "iteration":
                            continue
                        node = record.get("node")
                        if not isinstance(node, dict):
                            skipped_bad_shape += 1
                            continue
                        node_mvar_id = node.get("mvar_id")
                        goal_type = node.get("goal_type")
                        if not isinstance(node_mvar_id, str) or not isinstance(goal_type, str):
                            skipped_bad_shape += 1
                            continue

                        tactic_scores: dict[str, float] = {}
                        tactics = record.get("tactics")
                        if isinstance(tactics, list):
                            for item in tactics:
                                if not isinstance(item, dict):
                                    continue
                                tactic = item.get("tactic")
                                score = item.get("score")
                                if isinstance(tactic, str) and isinstance(score, (int, float)):
                                    tactic_scores[tactic] = float(score)

                        attempts = record.get("attempts")
                        if not isinstance(attempts, list):
                            continue

                        for attempt in attempts:
                            if not isinstance(attempt, dict):
                                continue
                            tactic = attempt.get("tactic")
                            outcome = attempt.get("outcome")
                            if not isinstance(tactic, str) or not isinstance(outcome, str):
                                skipped_bad_shape += 1
                                continue

                            committed = committed_by_mvar.get(node_mvar_id) == tactic
                            is_success = outcome == "success"
                            if label_policy == "committed_success":
                                if not (committed and is_success):
                                    continue
                            elif label_policy == "any_success":
                                if not is_success:
                                    continue
                            else:
                                raise ValueError(f"Unknown label_policy: {label_policy}")

                            key = (
                                f"{run_id}|{theorem}|{prefix}|{record.get('iteration')}|"
                                f"{node_mvar_id}|{tactic}|{outcome}|{int(committed)}"
                            )
                            if dedupe:
                                key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
                                if key_hash in seen_keys:
                                    continue
                                seen_keys.add(key_hash)

                            prompt = _build_prompt(statement, goal_type)
                            completion = f"{tactic}\n[/TAC]"
                            provider_score = tactic_scores.get(tactic)
                            weight = provider_score if provider_score is not None else 1.0
                            row = {
                                "schema_version": 1,
                                "text": prompt + completion,
                                "prompt": prompt,
                                "completion": completion,
                                "run_id": run_id,
                                "provider": run_config.get("provider"),
                                "corpus": run_config.get("corpus"),
                                "corpus_for_loading": corpus_for_loading,
                                "theorem": theorem,
                                "variant": prefix,
                                "iteration": record.get("iteration"),
                                "node_mvar_id": node_mvar_id,
                                "goal_type": goal_type,
                                "tactic": tactic,
                                "outcome": outcome,
                                "committed": committed,
                                "provider_score": _float_or_none(provider_score),
                                "weight": float(weight),
                                "state_mode": "goal_type_only",
                                "context_mode": "theorem_header",
                            }
                            out.write(json.dumps(row) + "\n")
                            rows_written += 1
                            run_counts[run_id] += 1
                            theorem_counts[theorem] += 1
                            variant_counts[prefix] += 1

                            if max_rows is not None and rows_written >= max_rows:
                                return BuildStats(
                                    rows_written=rows_written,
                                    run_counts=dict(run_counts),
                                    theorem_counts=dict(theorem_counts),
                                    variant_counts=dict(variant_counts),
                                    unloadable_runs=unloadable_runs,
                                    examples_skipped_missing_statement=skipped_missing_statement,
                                    examples_skipped_bad_shape=skipped_bad_shape,
                                )

    return BuildStats(
        rows_written=rows_written,
        run_counts=dict(run_counts),
        theorem_counts=dict(theorem_counts),
        variant_counts=dict(variant_counts),
        unloadable_runs=unloadable_runs,
        examples_skipped_missing_statement=skipped_missing_statement,
        examples_skipped_bad_shape=skipped_bad_shape,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build miniCTX-style tactic SFT JSONL from wonton-soup run logs. "
            "V1 uses goal_type-only STATE because full hypotheses are not present "
            "in current exports."
        )
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        action="append",
        help="Run directory; repeat for multiple runs",
    )
    parser.add_argument("--out", required=True, help="Output JSONL path")
    parser.add_argument("--provider", default=None, help="Provider name for multi-provider runs")
    parser.add_argument(
        "--variants",
        default="wild_type",
        help="Comma-separated variant prefixes (default: wild_type)",
    )
    parser.add_argument(
        "--label-policy",
        choices=["committed_success", "any_success"],
        default="committed_success",
        help="Label filter policy for SFT targets",
    )
    parser.add_argument("--max-rows", type=int, default=None, help="Optional max rows")
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Keep duplicate (node,tactic,outcome) rows",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repo root (auto-detected by default)",
    )
    parser.add_argument(
        "--skip-unloadable-runs",
        action="store_true",
        help="Skip runs whose corpus cannot be loaded from local environment",
    )
    args = parser.parse_args(argv)

    repo_root = resolve_repo_root(args.repo_root)
    run_dirs = [Path(path).expanduser().resolve() for path in args.run_dir]
    for run_dir in run_dirs:
        if not run_dir.is_dir():
            raise FileNotFoundError(f"run-dir is not a directory: {run_dir}")
    out_path = Path(args.out).expanduser().resolve()
    variants = _split_csv(args.variants)
    if not variants:
        raise ValueError("--variants resolved to empty set")

    stats = build_dataset(
        repo_root=repo_root,
        run_dirs=run_dirs,
        out_path=out_path,
        provider=args.provider,
        variants=variants,
        label_policy=args.label_policy,
        max_rows=args.max_rows,
        dedupe=not args.no_dedupe,
        skip_unloadable_runs=args.skip_unloadable_runs,
    )

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_dirs": [str(path) for path in run_dirs],
        "provider": args.provider,
        "variants": sorted(list(variants)),
        "label_policy": args.label_policy,
        "rows_written": stats.rows_written,
        "run_counts": stats.run_counts,
        "theorem_counts": stats.theorem_counts,
        "variant_counts": stats.variant_counts,
        "unloadable_runs": stats.unloadable_runs,
        "examples_skipped_missing_statement": stats.examples_skipped_missing_statement,
        "examples_skipped_bad_shape": stats.examples_skipped_bad_shape,
        "state_mode": "goal_type_only",
        "context_mode": "theorem_header",
    }
    manifest_path = out_path.with_suffix(out_path.suffix + ".manifest.json")
    write_json_object(manifest_path, manifest)

    print(f"Wrote dataset: {out_path}")
    print(f"Wrote manifest: {manifest_path}")
    print(f"Rows: {stats.rows_written}")
    print(f"Unloadable runs skipped: {len(stats.unloadable_runs)}")
