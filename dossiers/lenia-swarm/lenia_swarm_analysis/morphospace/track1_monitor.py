from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..morphospace_cli import refresh_compendium_warehouse
from .promote_results import promote_results_jsonl
from .track1_spec import track1_family_metadata
from .warehouse import connect_read_only_database


def stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(log_path: Path, event: str, **payload: object) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {"event": event, "recordedAt": stamp(), **payload}
    with log_path.open("a", encoding="utf-8", buffering=1) as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def complete_raw_runs(run_root: Path) -> list[str]:
    complete: list[str] = []
    for summary_path in sorted(run_root.glob("track1b-*-8192-s*/summary.json")):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if int(summary.get("count") or 0) != 8192:
            continue
        if int(summary.get("resultsCount") or 0) != 8192:
            continue
        complete.append(summary_path.parent.name)
    return complete


def promoted_runs(compendium_path: Path) -> set[str]:
    connection = sqlite3.connect(compendium_path)
    try:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT run_id FROM results WHERE run_id LIKE 'track1b-%'"
            )
        }
    finally:
        connection.close()


def refreshed_runs(warehouse_path: Path, *, expected_count: int) -> set[str]:
    connection = connect_read_only_database(warehouse_path)
    try:
        return {
            str(row[0])
            for row in connection.execute(
                """
                SELECT run_id
                FROM studies
                WHERE run_id LIKE 'track1b-%'
                  AND (
                      SELECT COUNT(DISTINCT observation_id)
                      FROM observations
                      WHERE observations.study_id = studies.study_id
                        AND observation_kind = 'synthetic_ca_terminal_embedding'
                  ) >= ?
                  AND (
                      SELECT COUNT(DISTINCT observation_id)
                      FROM observations
                      WHERE observations.study_id = studies.study_id
                        AND observation_kind = 'common_point_cloud_morphology'
                  ) >= ?
                  AND (
                      SELECT COUNT(DISTINCT state_id)
                      FROM anatomical_states
                      WHERE anatomical_states.study_id = studies.study_id
                        AND source_kind = 'specimen_baseline'
                  ) >= ?
                """,
                [expected_count, expected_count, expected_count],
            ).fetchall()
        }
    finally:
        connection.close()


def source_algorithm(run_id: str) -> str:
    return track1_family_metadata(run_id)["sourceAlgorithm"]


def promote(*, root: Path, run_id: str, compendium_path: Path, run_root: Path) -> dict[str, Any]:
    started = time.time()
    payload = promote_results_jsonl(
        compendium_path=compendium_path,
        run_dir=run_root / run_id,
        run_id=run_id,
        source_mode="track1-harvest",
        source_algorithm=source_algorithm(run_id),
        batch_size=2048,
    )
    payload["durationSeconds"] = round(time.time() - started, 3)
    payload["root"] = str(root)
    return payload


def refresh(
    *,
    run_id: str,
    compendium_path: Path,
    warehouse_path: Path,
) -> dict[str, Any]:
    started = time.time()
    payload = refresh_compendium_warehouse(
        warehouse_path=warehouse_path,
        compendium_path=compendium_path,
        run_id=run_id,
        topology=False,
    )
    payload["durationSeconds"] = round(time.time() - started, 3)
    return payload


def monitor_once(
    *,
    root: Path,
    run_root: Path,
    compendium_path: Path,
    warehouse_path: Path,
    log_path: Path,
    expected_count: int,
) -> str:
    complete = complete_raw_runs(run_root)
    promoted = promoted_runs(compendium_path)

    unpromoted = [run_id for run_id in complete if run_id not in promoted]
    if unpromoted:
        payload = promote(
            root=root,
            run_id=unpromoted[0],
            compendium_path=compendium_path,
            run_root=run_root,
        )
        log(log_path, "promoted", **payload)
        return "promoted"

    refreshed = refreshed_runs(warehouse_path, expected_count=expected_count)
    unrefreshed = [
        run_id for run_id in complete if run_id in promoted and run_id not in refreshed
    ]
    if unrefreshed:
        payload = refresh(
            run_id=unrefreshed[0],
            compendium_path=compendium_path,
            warehouse_path=warehouse_path,
        )
        log(log_path, "warehouse-refreshed", **payload)
        return "warehouse-refreshed"

    log(
        log_path,
        "idle",
        completeRuns=len(complete),
        promotedRuns=len(promoted),
        refreshedRuns=len(refreshed),
    )
    return "idle"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Promote completed Track 1 Flow Lenia chunks and backfill warehouse studies."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--sleep-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    run_root = root / "artifacts/flow-universe-runs/track1-20260520"
    compendium_path = root / "artifacts/compendium.sqlite"
    warehouse_path = root / "artifacts/morphospace.duckdb"
    log_path = root / "artifacts/morphospace-analysis/run-logs/track1-monitor-20260521.jsonl"

    log(log_path, "monitor-start", root=str(root))
    while True:
        try:
            monitor_once(
                root=root,
                run_root=run_root,
                compendium_path=compendium_path,
                warehouse_path=warehouse_path,
                log_path=log_path,
                expected_count=8192,
            )
        except Exception as exc:
            log(log_path, "error", error=f"{type(exc).__name__}: {exc}")
        if args.once:
            return
        time.sleep(args.sleep_seconds)


if __name__ == "__main__":
    main()
