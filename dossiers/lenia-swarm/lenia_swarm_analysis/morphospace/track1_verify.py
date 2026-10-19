from __future__ import annotations

import gzip
import hashlib
import json
import math
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import read_json, sha256_bytes, sha256_file
from lenia_swarm_analysis.morphospace.track1_spec import track1_family_metadata

CORRECTED_SHADER = b"float gxU = (u20 + 2.0f * u21 + u22) - (u00 + 2.0f * u01 + u02)"
CORRECTED_DENOMINATOR = b"float denom = totalWeight + 1.0e-10f"
BUGGY_SHADER = b"float gxU = (u00 + 2.0f * u10 + u20) - (u02 + 2.0f * u12 + u22)"

MOVER_DISPLACEMENT = 5.0
DIAGONAL_HALF_WIDTH = math.radians(11.25)
FLOAT_TOLERANT_KEYS = ("score",)


def engine_signature(engine: Path) -> dict[str, Any]:
    data = engine.read_bytes()
    corrected = CORRECTED_SHADER in data and CORRECTED_DENOMINATOR in data
    buggy = BUGGY_SHADER in data
    if corrected == buggy:
        raise SystemExit(f"{engine}: static shader signature is ambiguous")
    return {
        "path": str(engine),
        "sha256": sha256_bytes(data),
        "class": "corrected" if corrected else "buggy",
    }


def verify_track1_runs(
    *,
    run_root: Path,
    archive_dir: Path,
    run_ids: list[str],
    engine: Path,
    replay_offsets: list[int],
    replay_count: int,
    scratch_root: Path,
    output_path: Path,
    jobs: int,
) -> dict[str, Any]:
    signature = engine_signature(engine)
    if signature["class"] != "corrected":
        raise SystemExit(f"{engine}: replay engine carries the buggy shader signature")
    scratch_root.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def one(run_id: str) -> dict[str, Any]:
        row = inspect_run(run_root / run_id, archive_dir=archive_dir)
        row["replay"] = replay_run(
            run_root / run_id,
            engine=engine,
            offsets=replay_offsets,
            count=replay_count,
            scratch_root=scratch_root,
        )
        return row

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        rows = list(pool.map(one, run_ids))
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return {
        "engine": signature,
        "runCount": len(rows),
        "complete": sum(1 for row in rows if row["complete"]),
        "regenerated": sum(1 for row in rows if row["provenance"]["resultsDifferFromArchive"]),
        "replayExact": sum(1 for row in rows if row["replay"]["exact"]),
        "outputPath": str(output_path),
    }


def inspect_run(run_dir: Path, *, archive_dir: Path) -> dict[str, Any]:
    run_id = run_dir.name
    summary = read_json(run_dir / "summary.json")
    checkpoint = read_json(run_dir / "checkpoint.json")
    seed_start = int(summary["seedStart"])
    count = int(summary["count"])
    results_path = run_dir / "results.jsonl"

    seeds: list[int] = []
    filters_passed = 0
    headings: list[float] = []
    digest = hashlib.sha256()
    with results_path.open("rb") as handle:
        for line in handle:
            digest.update(line)
            if not line.strip():
                continue
            row = json.loads(line)
            seeds.append(int(row["seed"]))
            if row.get("filters_passed") is True:
                filters_passed += 1
            metrics = row["metrics"]
            if float(metrics["displacement"]) > MOVER_DISPLACEMENT:
                headings.append(float(metrics["heading_rad"]))

    expected = set(range(seed_start, seed_start + count))
    seed_set = set(seeds)
    export_dirs = sum(1 for path in (run_dir / "exports").iterdir() if path.is_dir())
    completeness = {
        "summaryCount": count,
        "summaryResultsCount": int(summary["resultsCount"]),
        "resultLines": len(seeds),
        "uniqueSeeds": len(seed_set),
        "missingSeeds": len(expected - seed_set),
        "unexpectedSeeds": len(seed_set - expected),
        "checkpointCompletedBatches": len(checkpoint["completedBatches"]),
        "expectedBatches": math.ceil(count / int(checkpoint["batchSize"])),
        "collectedCount": int(summary["collectedCount"]),
        "exportedCount": int(summary["exportedCount"]),
        "exportDirs": export_dirs,
        "filtersPassed": filters_passed,
    }
    complete = (
        completeness["resultLines"] == count
        and completeness["summaryResultsCount"] == count
        and completeness["uniqueSeeds"] == count
        and completeness["missingSeeds"] == 0
        and completeness["unexpectedSeeds"] == 0
        and completeness["checkpointCompletedBatches"] == completeness["expectedBatches"]
        and completeness["exportDirs"] == completeness["exportedCount"]
    )

    results_sha = digest.hexdigest()
    archived_sha = _archived_results_sha(archive_dir, run_id)
    return {
        "runId": run_id,
        "path": str(run_dir),
        "family": track1_family_metadata(run_id)["familyKey"],
        "seedStart": seed_start,
        "complete": complete,
        "completeness": completeness,
        "provenance": {
            "resultsSha256": results_sha,
            "resultsMtime": _mtime(results_path),
            "summaryMtime": _mtime(run_dir / "summary.json"),
            "archivedMarker": (run_dir / "ARCHIVED.json").exists(),
            "archivedResultsSha256": archived_sha,
            "resultsDifferFromArchive": archived_sha != results_sha,
            "configSha256": sha256_file(run_dir / "config.json"),
            "searchSha256": sha256_file(run_dir / "search.json"),
            "inputHash": checkpoint["inputHash"],
        },
        "orientation": orientation_signature(headings),
    }


def orientation_signature(headings: list[float]) -> dict[str, Any]:
    if not headings:
        return {"movers": 0, "nearDiagonalFraction": None, "meanCos4Theta": None}
    quarter = math.pi / 2
    near = sum(
        1 for theta in headings
        if abs((theta % quarter) - quarter / 2) <= DIAGONAL_HALF_WIDTH
    )
    return {
        "movers": len(headings),
        "nearDiagonalFraction": near / len(headings),
        "meanCos4Theta": sum(math.cos(4 * theta) for theta in headings) / len(headings),
    }


def replay_run(
    run_dir: Path,
    *,
    engine: Path,
    offsets: list[int],
    count: int,
    scratch_root: Path,
) -> dict[str, Any]:
    summary = read_json(run_dir / "summary.json")
    seed_start = int(summary["seedStart"])
    wanted: dict[int, dict[str, Any]] = {}
    batches = []
    for offset in offsets:
        start = seed_start + offset
        replay_id = f"{run_dir.name}-replay-{offset}"
        out_dir = scratch_root / replay_id
        if out_dir.exists():
            raise SystemExit(f"{out_dir}: replay scratch already exists")
        command = [
            str(engine), "discover", "local",
            "--backend", "metal-full",
            "--config", str(run_dir / "config.json"),
            "--search", str(run_dir / "search.json"),
            "--output", str(out_dir),
            "--run-id", replay_id,
            "--seed", str(start),
            "--count", str(count),
            "--no-promotion", "--no-log-console",
            "--log-dir", str(out_dir / "logs"),
        ]
        completed = subprocess.run(
            command, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False
        )
        if completed.returncode != 0:
            raise SystemExit(f"{replay_id}: replay failed: {completed.stderr[-2000:]}")
        for line in (out_dir / replay_id / "results.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                wanted[int(row["seed"])] = row
        shutil.rmtree(out_dir)
        batches.append({"seedStart": start, "count": count})

    archived: dict[int, dict[str, Any]] = {}
    with (run_dir / "results.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if int(row["seed"]) in wanted:
                archived[int(row["seed"])] = row
    if set(archived) != set(wanted):
        raise SystemExit(f"{run_dir.name}: replayed seeds missing from results.jsonl")

    return {"batches": batches, **compare_records(wanted, archived)}


def compare_records(
    replayed_rows: dict[int, dict[str, Any]], archived_rows: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    mismatched_keys: dict[str, int] = {}
    tolerant_max_rel = 0.0
    exact_seeds = 0
    for seed, replayed in replayed_rows.items():
        original = archived_rows[seed]
        differing = [
            key for key in sorted(set(replayed) | set(original))
            if key not in FLOAT_TOLERANT_KEYS and replayed.get(key) != original.get(key)
        ]
        # invariant: the engine omits score exactly when filters fail, so a presence
        # mismatch is a real difference and only shared scores are compared with tolerance
        for key in FLOAT_TOLERANT_KEYS:
            if (key in replayed) != (key in original):
                differing.append(key)
            elif key in original:
                a, b = float(replayed[key]), float(original[key])
                tolerant_max_rel = max(tolerant_max_rel, abs(a - b) / max(abs(b), 1e-12))
        for key in differing:
            mismatched_keys[key] = mismatched_keys.get(key, 0) + 1
        if not differing:
            exact_seeds += 1
    return {
        "seeds": len(replayed_rows),
        "exactSeeds": exact_seeds,
        "mismatchedKeys": mismatched_keys,
        "scoreMaxRelativeDifference": tolerant_max_rel,
        "exact": exact_seeds == len(replayed_rows),
    }


def _archived_results_sha(archive_dir: Path, run_id: str) -> str:
    manifest_path = archive_dir / f"{run_id}.manifest.json.gz"
    with gzip.open(manifest_path, "rt", encoding="utf-8") as handle:
        manifest = json.load(handle)
    return manifest[f"{run_id}/results.jsonl"]["sha256"]


def _mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
