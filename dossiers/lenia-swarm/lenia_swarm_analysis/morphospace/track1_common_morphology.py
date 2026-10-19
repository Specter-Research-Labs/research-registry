"""common_morphology_v1 observations straight from track-1 harvest results.

The warehouse path derives one observation per specimen from its terminal fingerprint. Track-1
harvests store that fingerprint in each results.jsonl record, so the same features can be read
without a warehouse. Each run is measured twice, once from its current results.jsonl and once from
the archived results.jsonl it replaced, and the two are paired by seed. Coordinates are z-scored
in a frozen frame (the robust centre and scale of an earlier corpus) so that shifts are comparable
with that corpus.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from lenia_swarm_analysis.morphospace.common_morphology import (
    AXIS_IDS,
    _fingerprint_point_cloud,
    point_cloud_shape_features,
)
from lenia_swarm_analysis.morphospace.track1_spec import track1_family_metadata
from lenia_swarm_analysis.morphospace.track1_verify import (
    MOVER_DISPLACEMENT,
    orientation_signature,
)

COMPACT_BODY_FRACTION = 0.99
COMPACT_BODY_COMPONENTS = 2
ERAS = ("archived", "current")
_COLUMNS = {
    "run_id": "VARCHAR", "family": "VARCHAR", "era": "VARCHAR", "seed": "BIGINT",
    "has_observation": "BOOLEAN", **{axis: "DOUBLE" for axis in AXIS_IDS},
    "filters_passed": "BOOLEAN", "displacement": "DOUBLE", "heading_rad": "DOUBLE",
    "harvest_largest_component_fraction": "DOUBLE", "harvest_component_count": "DOUBLE",
}


def results_observations(lines: Iterable[bytes]) -> Iterator[dict[str, Any]]:
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        seed = int(row["seed"])
        metrics = row["metrics"]
        cloud = _fingerprint_point_cloud(
            row["descriptor_bundle"]["terminal"], specimen_id=f"seed {seed}"
        )
        features = None if cloud is None else point_cloud_shape_features(cloud[0], weights=cloud[1])
        yield {
            "seed": seed,
            "has_observation": features is not None,
            **{axis: (None if features is None else features[axis]) for axis in AXIS_IDS},
            "filters_passed": row.get("filters_passed") is True,
            "displacement": float(metrics["displacement"]),
            "heading_rad": float(metrics["heading_rad"]),
            "harvest_largest_component_fraction": float(metrics["largest_component_fraction"]),
            "harvest_component_count": float(metrics["component_count"]),
        }


def load_frame(profile_path: Path) -> dict[str, tuple[float, float]]:
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    frame = {
        axis["axisId"]: (
            float(axis["metadata"]["robustCenter"]),
            float(axis["metadata"]["robustScale"]),
        )
        for axis in profile["axes"]
    }
    if tuple(frame) != AXIS_IDS:
        raise SystemExit(f"{profile_path}: axes {tuple(frame)} differ from {AXIS_IDS}")
    return frame


def _archived_lines(archive_dir: Path, run_id: str) -> Iterator[bytes]:
    member = f"{run_id}/results.jsonl"
    # tarfile cannot read zstd on this Python, so the archive is decompressed by the zstd CLI.
    process = subprocess.Popen(
        ["zstd", "-dc", str(archive_dir / f"{run_id}.tar.zst")], stdout=subprocess.PIPE
    )
    assert process.stdout is not None
    found = False
    with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
        for info in archive:
            if info.name == member:
                handle = archive.extractfile(info)
                assert handle is not None
                found = True
                yield from handle
                break
    process.stdout.close()
    process.wait()
    if not found:
        raise SystemExit(f"{archive_dir}: {member} not in archive")


def _measure_run(args: tuple[Path, Path, str, Path]) -> Path:
    run_root, archive_dir, run_id, parts_dir = args
    family = track1_family_metadata(run_id)["familyKey"]
    rows = []
    with (run_root / run_id / "results.jsonl").open("rb") as handle:
        rows += [{"era": "current", **obs} for obs in results_observations(handle)]
    rows += [{"era": "archived", **obs} for obs in results_observations(
        _archived_lines(archive_dir, run_id))]
    path = parts_dir / f"{run_id}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps({"run_id": run_id, "family": family, **row}) + "\n")
    return path


def derive_track1_common_morphology(
    *,
    run_root: Path,
    archive_dir: Path,
    run_ids: list[str],
    frame_profile: Path,
    v8_metadata: Path,
    v8_shapes: Path,
    output_dir: Path,
    jobs: int,
) -> dict[str, Any]:
    frame = load_frame(frame_profile)
    parts_dir = output_dir / "observation-parts"
    parts_dir.mkdir(parents=True, exist_ok=False)
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        list(pool.map(_measure_run, [(run_root, archive_dir, rid, parts_dir) for rid in run_ids]))

    observations = output_dir / "observations.parquet"
    con = duckdb.connect()
    con.execute(f"""
        COPY (SELECT * FROM read_json('{parts_dir}/*.jsonl', columns = {_COLUMNS})
              ORDER BY run_id, seed, era)
        TO '{observations}' (FORMAT parquet, COMPRESSION zstd)
    """)
    shutil.rmtree(parts_dir)
    con.execute(f"CREATE VIEW obs AS SELECT * FROM read_parquet('{observations}')")
    v8 = _v8_reproduction(con, v8_metadata, v8_shapes)
    if v8["oursOnly"] or v8["v8Only"] or v8["maxAbsDifference"] != 0.0:
        raise SystemExit(f"archived observations do not reproduce v8: {v8}")
    summary = {
        "frame": str(frame_profile),
        "runCount": len(run_ids),
        "records": dict(con.execute(
            "SELECT era, count(*) FROM obs GROUP BY era").fetchall()),
        "observations": dict(con.execute(
            "SELECT era, count(*) FROM obs WHERE has_observation GROUP BY era").fetchall()),
        "v8Reproduction": v8,
        "pairedShift": _paired_shift(con, frame),
        "classChanges": _class_changes(con),
        "orientation": _orientation(con),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _v8_reproduction(
    con: duckdb.DuckDBPyConnection, v8_metadata: Path, v8_shapes: Path
) -> dict[str, Any]:
    vector = ", ".join(AXIS_IDS)
    rows = con.execute(f"""
        WITH v8 AS (
            SELECT m.specimen_id, s.vector
            FROM read_parquet('{v8_metadata}') m
            JOIN read_parquet('{v8_shapes}') s USING (signature, observation_id)
        )
        SELECT o.run_id, o.seed, [{vector}] AS ours, v8.vector AS theirs
        FROM obs o
        LEFT JOIN v8 ON v8.specimen_id = 'result:' || o.run_id || '|overall|' || o.seed
        WHERE o.era = 'archived'
    """).fetchall()
    ours_only = sum(1 for _, _, ours, theirs in rows if ours[0] is not None and theirs is None)
    theirs_only = sum(1 for _, _, ours, theirs in rows if ours[0] is None and theirs is not None)
    both = [(np.array(o, dtype=float), np.array(t, dtype=float))
            for _, _, o, t in rows if o[0] is not None and t is not None]
    max_abs = max((float(np.max(np.abs(o - t))) for o, t in both), default=None)
    return {
        "archivedRecords": len(rows),
        "matched": len(both),
        "oursOnly": ours_only,
        "v8Only": theirs_only,
        "maxAbsDifference": max_abs,
    }


def _paired_shift(
    con: duckdb.DuckDBPyConnection, frame: dict[str, tuple[float, float]]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for axis, (center, scale) in frame.items():
        rows = con.execute(f"""
            SELECT a.family, (c.{axis} - a.{axis}) / {scale} AS dz, a.{axis}, c.{axis}
            FROM obs a JOIN obs c USING (run_id, seed)
            WHERE a.era = 'archived' AND c.era = 'current'
              AND a.has_observation AND c.has_observation
        """).fetchall()
        by_family: dict[str, list[float]] = {}
        for family, dz, _, _ in rows:
            by_family.setdefault(family, []).append(dz)
        by_family["all"] = [row[1] for row in rows]
        out[axis] = {
            "frameCenter": center,
            "frameScale": scale,
            **{family: _distribution(values) for family, values in sorted(by_family.items())},
            "medianZ": {
                "archived": (float(np.median([row[2] for row in rows])) - center) / scale,
                "current": (float(np.median([row[3] for row in rows])) - center) / scale,
            },
        }
    return out


def _distribution(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    q25, q50, q75 = np.quantile(array, [0.25, 0.5, 0.75])
    return {
        "pairs": int(array.size),
        "meanDz": float(array.mean()),
        "medianDz": float(q50),
        "q25Dz": float(q25),
        "q75Dz": float(q75),
        "meanAbsDz": float(np.abs(array).mean()),
    }


def _class_changes(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    classes = {
        "mover": f"displacement > {MOVER_DISPLACEMENT}",
        "compactBody": (f"harvest_largest_component_fraction >= {COMPACT_BODY_FRACTION} "
                        f"AND harvest_component_count <= {COMPACT_BODY_COMPONENTS}"),
        "filtersPassed": "filters_passed",
        "hasObservation": "has_observation",
    }
    out: dict[str, Any] = {}
    for name, predicate in classes.items():
        rows = con.execute(f"""
            WITH c AS (SELECT run_id, seed, family, era, ({predicate}) AS k FROM obs)
            SELECT a.family, a.k, b.k, count(*)
            FROM c a JOIN c b USING (run_id, seed)
            WHERE a.era = 'archived' AND b.era = 'current'
            GROUP BY ALL
        """).fetchall()
        table: dict[str, dict[str, int]] = {}
        for family, before, after, count in rows:
            for key in (family, "all"):
                cell = table.setdefault(key, {"bothNo": 0, "gained": 0, "lost": 0, "bothYes": 0})
                label = {(False, False): "bothNo", (False, True): "gained",
                         (True, False): "lost", (True, True): "bothYes"}[(before, after)]
                cell[label] += count
        out[name] = {"definition": predicate, **dict(sorted(table.items()))}
    return out


def _orientation(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for era in ERAS:
        rows = con.execute(
            "SELECT family, heading_rad FROM obs WHERE era = ? AND displacement > ?",
            [era, MOVER_DISPLACEMENT],
        ).fetchall()
        by_family: dict[str, list[float]] = {"all": [row[1] for row in rows]}
        for family, heading in rows:
            by_family.setdefault(family, []).append(heading)
        out[era] = {family: orientation_signature(headings)
                    for family, headings in sorted(by_family.items())}
    return out

