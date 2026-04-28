# ruff: noqa: I001
from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared import (
    find_family_prior_model,
    load_json_object,
    read_run_id,
    resolve_repo_root,
    write_json_object,
)


@dataclass(frozen=True)
class RunOutcome:
    run_dir: Path
    run_id: str
    model_path: Path
    eval_path: Path
    eval_payload: dict[str, Any]


def _run(
    *,
    cmd: list[str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "Command failed with non-zero exit code.\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def _row_for_alpha(payload: dict[str, Any], alpha: float) -> dict[str, Any]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("eval payload missing rows")
    for row in rows:
        if not isinstance(row, dict):
            continue
        v = row.get("alpha")
        if isinstance(v, (int, float)) and float(v) == float(alpha):
            return row
    raise ValueError(f"eval payload missing alpha={alpha}")


def _score_row(row: dict[str, Any]) -> tuple[float, float]:
    top1 = row.get("top1_success")
    rank = row.get("mean_rank_first_success")
    if not isinstance(top1, (int, float)):
        top1 = float("-inf")
    if not isinstance(rank, (int, float)):
        rank = float("inf")
    return (float(top1), -float(rank))


def _best_nonzero_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return None
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        alpha = row.get("alpha")
        if isinstance(alpha, (int, float)) and float(alpha) > 0.0:
            candidates.append(row)
    if not candidates:
        return None
    return max(candidates, key=_score_row)


def _aggregate_by_alpha(outcomes: list[RunOutcome]) -> list[dict[str, Any]]:
    per_alpha: dict[float, dict[str, float]] = {}
    for outcome in outcomes:
        rows = outcome.eval_payload.get("rows", [])
        for row in rows:
            if not isinstance(row, dict):
                continue
            alpha = row.get("alpha")
            iters = row.get("iters")
            top1 = row.get("top1_success")
            mean_rank = row.get("mean_rank_first_success")
            if not isinstance(alpha, (int, float)):
                continue
            if not isinstance(iters, int) or iters <= 0:
                continue
            slot = per_alpha.setdefault(
                float(alpha),
                {
                    "iters_total": 0.0,
                    "top1_weighted_sum": 0.0,
                    "rank_weighted_sum": 0.0,
                    "rows_count": 0.0,
                },
            )
            slot["iters_total"] += float(iters)
            if isinstance(top1, (int, float)):
                slot["top1_weighted_sum"] += float(top1) * float(iters)
            if isinstance(mean_rank, (int, float)):
                slot["rank_weighted_sum"] += float(mean_rank) * float(iters)
            slot["rows_count"] += 1.0

    result: list[dict[str, Any]] = []
    for alpha, slot in sorted(per_alpha.items()):
        iters_total = slot["iters_total"]
        top1 = (
            round(slot["top1_weighted_sum"] / iters_total, 4) if iters_total > 0 else None
        )
        mean_rank = (
            round(slot["rank_weighted_sum"] / iters_total, 4) if iters_total > 0 else None
        )
        result.append(
            {
                "alpha": alpha,
                "iters_total": int(iters_total),
                "top1_success_weighted": top1,
                "mean_rank_first_success_weighted": mean_rank,
                "runs_count": int(slot["rows_count"]),
            }
        )
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Train + replay-evaluate family_prior over many runs and emit leaderboard JSON"
    )
    parser.add_argument(
        "--run-dir",
        action="append",
        default=[],
        help="Path to corpus run dir (repeatable)",
    )
    parser.add_argument(
        "--run-list",
        default=None,
        help="Optional text file with one run directory path per line",
    )
    parser.add_argument(
        "--out-root",
        required=True,
        help="Output root for trained models and eval artifacts",
    )
    parser.add_argument(
        "--alphas",
        default="0,0.1,0.25,0.5,0.75,1.0",
        help="Comma-separated alpha sweep",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root override")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing per-run eval JSON",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Optional explicit output JSON path "
            "(default: <out_root>/family_prior_batch_eval.json)"
        ),
    )
    args = parser.parse_args(argv)

    repo_root = resolve_repo_root(args.repo_root)
    out_root = Path(args.out_root).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    run_dirs: list[Path] = [Path(x).expanduser().resolve() for x in args.run_dir]
    if args.run_list:
        run_list_path = Path(args.run_list).expanduser().resolve()
        if not run_list_path.exists():
            raise FileNotFoundError(f"run list not found: {run_list_path}")
        for line in run_list_path.read_text().splitlines():
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            run_dirs.append(Path(entry).expanduser().resolve())
    run_dirs = sorted(set(run_dirs))
    if not run_dirs:
        raise ValueError("No run directories provided. Use --run-dir and/or --run-list.")

    outcomes: list[RunOutcome] = []
    for run_dir in run_dirs:
        if not run_dir.is_dir():
            raise FileNotFoundError(f"run_dir not found: {run_dir}")
        run_id = read_run_id(run_dir)

        train_cmd = [
            "uv",
            "--project",
            "dossiers/wonton-soup",
            "run",
            "python",
            "dossiers/wonton-soup/wonton.py",
            "train-family-prior",
            "--run-dir",
            str(run_dir),
            "--out-dir",
            str(out_root),
            "--overwrite",
        ]
        _run(cmd=train_cmd, cwd=repo_root)
        model_path = find_family_prior_model(out_root, run_id)

        eval_path = out_root / run_id / "family_prior_replay_eval.json"
        if eval_path.exists() and not args.overwrite:
            eval_payload = load_json_object(eval_path)
        else:
            eval_cmd = [
                "uv",
                "--project",
                "dossiers/wonton-soup",
                "run",
                "python",
                "addenda/lean-mcts-learning/eval/family_prior_replay.py",
                "--run-dir",
                str(run_dir),
                "--model",
                str(model_path),
                "--alphas",
                args.alphas,
                "--out",
                str(eval_path),
            ]
            _run(cmd=eval_cmd, cwd=repo_root)
            eval_payload = load_json_object(eval_path)

        outcomes.append(
            RunOutcome(
                run_dir=run_dir,
                run_id=run_id,
                model_path=model_path,
                eval_path=eval_path,
                eval_payload=eval_payload,
            )
        )

    per_run: list[dict[str, Any]] = []
    for outcome in outcomes:
        baseline = _row_for_alpha(outcome.eval_payload, 0.0)
        best_nonzero = _best_nonzero_row(outcome.eval_payload)
        row: dict[str, Any] = {
            "run_id": outcome.run_id,
            "run_dir": str(outcome.run_dir),
            "model_path": str(outcome.model_path),
            "eval_path": str(outcome.eval_path),
            "baseline_alpha0": {
                "top1_success": baseline.get("top1_success"),
                "mean_rank_first_success": baseline.get("mean_rank_first_success"),
                "pairwise_success_ahead": baseline.get("pairwise_success_ahead"),
                "iters": baseline.get("iters"),
            },
            "recommend_alpha": 0.0,
            "recommend_reason": "baseline_best_or_tied",
        }
        if isinstance(best_nonzero, dict):
            row["best_nonzero"] = {
                "alpha": best_nonzero.get("alpha"),
                "top1_success": best_nonzero.get("top1_success"),
                "mean_rank_first_success": best_nonzero.get("mean_rank_first_success"),
                "pairwise_success_ahead": best_nonzero.get("pairwise_success_ahead"),
            }
            b_top1 = baseline.get("top1_success")
            nz_top1 = best_nonzero.get("top1_success")
            b_rank = baseline.get("mean_rank_first_success")
            nz_rank = best_nonzero.get("mean_rank_first_success")
            if (
                isinstance(b_top1, (int, float))
                and isinstance(nz_top1, (int, float))
                and isinstance(b_rank, (int, float))
                and isinstance(nz_rank, (int, float))
                and (float(nz_top1) > float(b_top1))
                and (float(nz_rank) <= float(b_rank))
            ):
                row["recommend_alpha"] = float(best_nonzero["alpha"])
                row["recommend_reason"] = "improves_top1_and_not_worse_rank"
        per_run.append(row)

    aggregate = _aggregate_by_alpha(outcomes)
    payload = {
        "schema_version": 1,
        "repo_root": str(repo_root),
        "out_root": str(out_root),
        "run_count": len(outcomes),
        "alphas": args.alphas,
        "aggregate_by_alpha": aggregate,
        "per_run": per_run,
    }

    out_path = (
        Path(args.out).expanduser().resolve()
        if args.out
        else (out_root / "family_prior_batch_eval.json")
    )
    write_json_object(out_path, payload)
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
