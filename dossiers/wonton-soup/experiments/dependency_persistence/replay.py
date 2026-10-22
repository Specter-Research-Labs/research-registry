#!/usr/bin/env python3
"""Replay archived solution paths and record each proof's premise dependencies.

Input is JSONL with `job`, `statement` (a theorem ending in a `sorry` line, with
`{name}` in place of the declaration name) and `steps` (`tactic`, `goal`).
Each job is replayed goal by goal in the REPL, then the applied tactics are
elaborated as one declaration whose dependencies are read from Lean. Output is
one JSONL row per job; rerunning skips jobs already in the output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    raise SystemExit(
        "Run from dossiers/wonton-soup with "
        "`uv run python -m experiments.dependency_persistence.replay ...`."
    )

from leantree.repl_adapter.interaction import LeanProcessException

from prover.adapters.lean import LeanAdapter
from prover.dependencies import check_proof


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


async def replay_job(adapter: LeanAdapter, job: dict[str, Any]) -> dict[str, Any]:
    statement = job["statement"].replace("{name}", f"wd_{job['job']}")
    replay = await adapter.replay_solution_path(
        statement, job["steps"], extract_proof_term=False
    )
    if not replay.success:
        return {"status": "replay_failed", "error": replay.error, "tactics": replay.applied_tactics}
    check = await check_proof(adapter.env, statement, replay.applied_tactics)
    return {
        "status": "checked" if check.ok else "check_failed",
        "error": check.error,
        "tactics": replay.applied_tactics,
        "dependencies": [d.row() for d in check.dependencies],
    }


async def _worker(
    project: Path,
    queue: asyncio.Queue,
    out,
    job_timeout: float,
    restart_every: int,
    counts: Counter,
) -> None:
    adapter = await _open(project)
    served = 0
    try:
        while True:
            try:
                job = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if served >= restart_every:
                await _close(adapter)
                adapter = await _open(project)
                served = 0
            started = time.monotonic()
            restart = False
            try:
                row = await asyncio.wait_for(replay_job(adapter, job), timeout=job_timeout)
            except TimeoutError:
                row = {"status": "timeout", "error": f"exceeded {job_timeout:.0f}s"}
                restart = True
            except LeanProcessException as exc:
                row = {"status": "crashed", "error": str(exc)[:2000]}
                restart = True
            row = {"job": job["job"], **row, "seconds": round(time.monotonic() - started, 3)}
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            counts[row["status"]] += 1
            served += 1
            if restart:
                await _close(adapter)
                adapter = await _open(project)
                served = 0
    finally:
        await _close(adapter)


async def run(args: argparse.Namespace) -> Counter:
    done: set[str] = set()
    if args.out.exists():
        done = {json.loads(line)["job"] for line in args.out.read_text().splitlines()}
    jobs = [json.loads(line) for line in args.jobs.read_text().splitlines()]
    pending = [job for job in jobs if job["job"] not in done]
    if args.limit is not None:
        pending = pending[: args.limit]
    queue: asyncio.Queue = asyncio.Queue()
    for job in pending:
        queue.put_nowait(job)
    counts: Counter = Counter()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a") as out:
        await asyncio.gather(
            *(
                _worker(
                    args.lean_project, queue, out, args.job_timeout, args.restart_every, counts
                )
                for _ in range(min(args.workers, len(pending)))
            )
        )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--lean-project", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--job-timeout", type=float, default=300.0)
    parser.add_argument("--restart-every", type=int, default=200)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    counts = asyncio.run(run(args))
    print(json.dumps(dict(sorted(counts.items()))))


if __name__ == "__main__":
    main()
