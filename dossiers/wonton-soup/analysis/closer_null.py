"""Closer null: whether one fixed closing tactic, at the root or after `intros`, proves a theorem.

A lesioned prover that recovers a theorem a lone closer already proves shows no
repertoire beyond that closer. Each attempt is previewed under the search
adapter's budgets and every closing sequence is kernel-checked, so the null is
judged by the same standard as the providers' checked rows.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from leantree.repl_adapter.interaction import LeanInteractionException, LeanProcessException

from analysis.lake.checked_outcomes import decode_name
from orchestrator.lean_inputs import EASY_TACTICS
from prover.adapters.lean import LeanAdapter, TacticWallTimeout
from prover.intervention import _runs_blocked_tactic

CLOSERS_MATCHED = (
    "norm_num",
    "linarith",
    "nlinarith",
    "positivity",
    "ring",
    "tauto",
    "aesop",
    "trivial",
    "assumption",
    "contradiction",
)
CLOSERS_OPEN_EXTRA = ("simp", "simp_all", "omega", "decide", "rfl")
CLOSERS = CLOSERS_MATCHED + CLOSERS_OPEN_EXTRA
PREFIXES: tuple[tuple[str, ...], ...] = ((), ("intros",))
# A wall guard bounds each tactic; this bounds the declaration check too, whose
# elaboration the REPL runs without a deadline.
ATTEMPT_TIMEOUT_S = 600.0
# Long-lived REPLs grow with every elaborated declaration, as in the replay verifier.
RESTART_EVERY = 200


def attempt_key(job: str, prefix: tuple[str, ...], closer: str) -> str:
    return "|".join((job, " ; ".join(prefix), closer))


async def run_attempt(
    adapter: LeanAdapter, statement: str, prefix: tuple[str, ...], closer: str
) -> dict[str, Any]:
    # Opening the statement declares it in the REPL, so every attempt rolls back
    # to let the next attempt on the same statement open it again.
    checkpoint = adapter.env.checkpoint()
    try:
        return await _attempt(adapter, statement, prefix, closer)
    finally:
        adapter.env.rollback_to(checkpoint)


async def _attempt(
    adapter: LeanAdapter, statement: str, prefix: tuple[str, ...], closer: str
) -> dict[str, Any]:
    try:
        roots = await adapter.initialize(statement)
    except LeanInteractionException as exc:
        return {"status": "statement_error", "error": str(exc)[:2000]}
    if len(roots) != 1:
        return {"status": "root_goals", "error": f"{len(roots)} root goals"}
    state = roots[0]
    path: list[dict[str, str]] = []
    for tactic in (*prefix, closer):
        goal = adapter.get_goal(state)
        if goal is None:
            raise LeanInteractionException(f"open state {state} has no goal")
        preview = await adapter.preview_tactic(state, tactic)
        is_closer = len(path) == len(prefix)
        if preview is None:
            return {"status": "rejected" if is_closer else "prefix_rejected"}
        path.append({"tactic": tactic, "goal": goal.type})
        if is_closer:
            if preview.child_mvar_ids:
                return {"status": "open_goals", "open_goals": len(preview.child_mvar_ids)}
            break
        if len(preview.child_mvar_ids) != 1:
            return {"status": "prefix_goals", "open_goals": len(preview.child_mvar_ids)}
        [state] = adapter.commit_tactic(preview)
    check, _ = await adapter.kernel_check(
        statement, path, library_name=None, blocked_premises=frozenset()
    )
    return {
        "status": check.status,
        "error": check.error,
        "tactics": list(check.tactics),
        "premises": list(check.premises),
    }


def recovers(
    attempts: Iterable[dict[str, Any]],
    theorem: str,
    blocked: frozenset[str],
    *,
    matched: bool,
    nonself: bool,
) -> bool:
    """Whether some checked closing sequence runs no tactic the lesion blocks.

    The matched arm also refuses the easy tactics, as `block_easy` does in the
    lesion runs; `nonself` refuses proofs that cite the theorem's own library name.
    """
    refused = blocked | EASY_TACTICS if matched else blocked
    name = decode_name(theorem)
    return any(
        a["status"] == "checked"
        and not (nonself and name in a["premises"])
        and not any(_runs_blocked_tactic(refused, t) for t in a["tactics"])
        for a in attempts
    )


async def _open(project: Path) -> LeanAdapter:
    adapter = await LeanAdapter.create(project)
    await adapter.__aenter__()
    return adapter


async def _close(adapter: LeanAdapter) -> None:
    # A crashed REPL can fail again while shutting down; the crash is already recorded.
    try:
        await adapter.__aexit__(None, None, None)
    except (LeanProcessException, ProcessLookupError, BrokenPipeError):
        pass


async def run_null(jobs_path: Path, out: Path, project: Path, shard: int, shards: int) -> Counter:
    """Run this shard's (job, prefix, closer) attempts not yet in `out`, one JSONL row each.

    Shards are separate processes because proof terms are parsed in Python on the
    event loop, so REPLs sharing one loop stall each other and distort the timings.
    """
    if not 0 <= shard < shards:
        raise ValueError(f"shard {shard} is outside 0..{shards - 1}")
    done: set[str] = set()
    if out.exists():
        done = {json.loads(line)["key"] for line in out.read_text().splitlines()}
    jobs = [json.loads(line) for line in jobs_path.read_text().splitlines()]
    pending = [
        (job, prefix, closer)
        for job in jobs[shard::shards]
        for prefix in PREFIXES
        for closer in CLOSERS
        if attempt_key(job["job"], prefix, closer) not in done
    ]
    counts: Counter = Counter()
    if not pending:
        return counts
    out.parent.mkdir(parents=True, exist_ok=True)
    adapter = await _open(project)
    served = 0
    try:
        with out.open("a") as f:
            for job, prefix, closer in pending:
                if served >= RESTART_EVERY:
                    await _close(adapter)
                    adapter = await _open(project)
                    served = 0
                row, restart = await _timed_attempt(adapter, job, prefix, closer)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                counts[row["status"]] += 1
                served += 1
                if restart:
                    await _close(adapter)
                    adapter = await _open(project)
                    served = 0
    finally:
        await _close(adapter)
    return counts


async def _timed_attempt(
    adapter: LeanAdapter, job: dict[str, str], prefix: tuple[str, ...], closer: str
) -> tuple[dict[str, Any], bool]:
    started = time.monotonic()
    restart = True
    statement = job["statement"].replace("{name}", f"wn_{job['job']}")
    try:
        row = await asyncio.wait_for(
            run_attempt(adapter, statement, prefix, closer), timeout=ATTEMPT_TIMEOUT_S
        )
        restart = False
    except TimeoutError:
        row = {"status": "timeout", "error": f"exceeded {ATTEMPT_TIMEOUT_S:.0f}s"}
    except TacticWallTimeout as exc:
        row = {"status": "wall_timeout", "error": str(exc)}
    except LeanProcessException as exc:
        row = {"status": "crashed", "error": str(exc)[:2000]}
    row = {
        "key": attempt_key(job["job"], prefix, closer),
        "job": job["job"],
        "theorem": job["theorem"],
        "prefix": list(prefix),
        "closer": closer,
        **row,
        "seconds": round(time.monotonic() - started, 3),
    }
    return row, restart
