"""Re-check a finished Lean run's tree-solved proofs in the kernel, offline.

Every variant whose search tree closed is replayed through
`LeanAdapter.kernel_check`, the same check a run applies to its own proofs. The
verdicts are written as `kernel_verdicts.parquet` in each provider run dir, in
the shape `wonton.py lake ingest-verdicts` reads, so archived runs that predate
the in-run check can join the checked comparison views.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from analysis.lake.db import run_key_for_run_dir
from analysis.lake.verdicts import VERDICT_COLUMNS
from analysis.logs import ProviderRun, iter_provider_runs, read_json, read_json_gz
from corpus.lean.theorems import Theorem
from orchestrator.lean_inputs import load_corpus
from orchestrator.lean_runner import make_unique_name
from prover.adapters.lean import LeanAdapter
from prover.dependencies import KernelCheck

VERDICTS_NAME = "kernel_verdicts.parquet"


@dataclass(frozen=True)
class VariantTarget:
    theorem: Theorem
    variant: str
    blocked_premises: frozenset[str]
    solution_path: list[dict[str, Any]]


@dataclass(frozen=True)
class ProviderVerdicts:
    provider_run: ProviderRun
    verdicts_path: Path
    checks: list[tuple[VariantTarget, KernelCheck]]


def _load_theorems(run_config: dict[str, Any]) -> dict[str, Theorem]:
    theorems, corpus_meta, _ = load_corpus(run_config["corpus_spec"])
    recorded = run_config["corpus_meta"].get("items_sha256")
    if recorded is not None and recorded != corpus_meta["items_sha256"]:
        raise ValueError(
            f"corpus {run_config['corpus_spec']!r} items changed since the run: "
            f"run recorded {recorded}, now {corpus_meta['items_sha256']}"
        )
    return {theorem.name: theorem for theorem in theorems}


def _resolve_lean_project(run_config: dict[str, Any], override: Path | None) -> Path:
    if override is not None:
        project = override.resolve()
    else:
        project_value = run_config["resolved"]["project_path"]
        if not isinstance(project_value, str) or not project_value.strip():
            raise ValueError(
                "run_config.json missing resolved.project_path; pass --lean-project explicitly"
            )
        project = Path(project_value).expanduser().resolve()
    if not project.exists():
        raise FileNotFoundError(f"Lean project not found: {project}")
    return project


def _tree_closed(entry: dict[str, Any]) -> bool:
    # Same rule as the lake's theorem_variant_verdict view: runs that record
    # tree_solved checked their own proofs; archived runs' `solved` means the
    # search tree closed.
    if "tree_solved" in entry:
        return entry["tree_solved"] is True
    return entry["solved"] is True


def _solution_path(theorem_dir: Path, variant: str) -> list[dict[str, Any]]:
    history_path = theorem_dir / f"{variant}_history.json"
    solution_path = read_json(history_path)["solution_path"]
    if not isinstance(solution_path, list) or not solution_path:
        raise ValueError(f"{history_path} has no solution_path for a closed search tree")
    return solution_path


def _targets(
    run_dir: Path,
    summary: dict[str, Any],
    theorems: dict[str, Theorem],
    *,
    theorem_names: set[str] | None,
    limit: int | None,
) -> list[VariantTarget]:
    entries = summary["theorems"]
    present = {entry["name"] for entry in entries}
    if theorem_names is not None and theorem_names - present:
        missing = ", ".join(sorted(theorem_names - present))
        raise ValueError(f"Requested theorem(s) not found in summary: {missing}")

    targets: list[VariantTarget] = []
    selected = 0
    for entry in entries:
        name = entry["name"]
        if theorem_names is not None and name not in theorem_names:
            continue
        if limit is not None and selected >= limit:
            break
        variants = [("wild_type", entry["wild_type"], frozenset[str]())]
        variants.extend(
            (item["name"], item, frozenset(item.get("blocked_premises", ())))
            for item in entry["interventions"]
        )
        closed = [(variant, blocked) for variant, row, blocked in variants if _tree_closed(row)]
        if not closed:
            continue
        selected += 1
        theorem_dir = run_dir / name
        targets.extend(
            VariantTarget(
                theorem=theorems[name],
                variant=variant,
                blocked_premises=blocked,
                solution_path=_solution_path(theorem_dir, variant),
            )
            for variant, blocked in closed
        )
    return targets


async def _check_targets(
    lean_project: Path, targets: list[VariantTarget]
) -> list[tuple[VariantTarget, KernelCheck]]:
    results: list[tuple[VariantTarget, KernelCheck]] = []
    async with await LeanAdapter.create(lean_project) as adapter:
        for target in targets:
            check, _ = await adapter.kernel_check(
                make_unique_name(target.theorem, "verify"),
                target.solution_path,
                library_name=target.theorem.library_name,
                blocked_premises=target.blocked_premises,
            )
            results.append((target, check))
    return results


def _write_verdicts(
    path: Path, run_key: str, checks: list[tuple[VariantTarget, KernelCheck]]
) -> None:
    conn = duckdb.connect()
    try:
        conn.execute(
            "CREATE TABLE v (run_key VARCHAR, theorem VARCHAR, variant VARCHAR, status VARCHAR, "
            "replay_status VARCHAR, replay_error VARCHAR, premises VARCHAR[])"
        )
        conn.executemany(
            "INSERT INTO v VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_key,
                    target.theorem.name,
                    target.variant,
                    check.status,
                    check.status,
                    check.error,
                    list(check.premises),
                )
                for target, check in checks
            ],
        )
        tmp = path.with_suffix(".parquet.tmp")
        conn.execute(
            f"COPY (SELECT {', '.join(VERDICT_COLUMNS)} FROM v ORDER BY theorem, variant) "
            "TO ? (FORMAT parquet)",
            [str(tmp)],
        )
        tmp.replace(path)
    finally:
        conn.close()


def verify_provider_run_local(
    provider_run: ProviderRun,
    *,
    theorem_names: list[str] | None,
    limit: int | None,
    lean_project: Path | None,
) -> ProviderVerdicts:
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    run_dir = provider_run.run_dir.resolve()
    run_config = read_json(run_dir / "run_config.json")
    backend = run_config["backend"]
    if backend != "lean":
        raise ValueError(f"verify-run-local supports only backend=lean (got {backend!r})")
    project = _resolve_lean_project(run_config, lean_project)
    targets = _targets(
        run_dir,
        read_json_gz(run_dir / "summary.json.gz"),
        _load_theorems(run_config),
        theorem_names=set(theorem_names) if theorem_names else None,
        limit=limit,
    )
    checks = asyncio.run(_check_targets(project, targets))
    verdicts_path = run_dir / VERDICTS_NAME
    _write_verdicts(verdicts_path, run_key_for_run_dir(run_dir), checks)
    return ProviderVerdicts(provider_run=provider_run, verdicts_path=verdicts_path, checks=checks)


def verify_run_local(
    run_dir: Path,
    *,
    theorem_names: list[str] | None,
    limit: int | None,
    lean_project: Path | None,
) -> list[ProviderVerdicts]:
    return [
        verify_provider_run_local(
            provider_run,
            theorem_names=theorem_names,
            limit=limit,
            lean_project=lean_project,
        )
        for provider_run in iter_provider_runs(run_dir)
    ]
