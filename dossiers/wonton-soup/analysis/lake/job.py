from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from analysis.lake.job_config import (
    build_selected_runs_query,
    create_selected_runs_view,
    resolve_same_method_as_selection,
)
from analysis.lake.job_config import load_job_config as _load_job_config

load_job_config = _load_job_config


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, (list, dict)):
        return value
    return str(value)


def _materialize_jsonl(conn: Any, *, query: str, out_path: Path) -> int:
    cur = conn.execute(query)
    cols = [column[0] for column in cur.description]

    def rows() -> Iterable[dict[str, Any]]:
        while True:
            batch = cur.fetchmany(2048)
            if not batch:
                break
            for row in batch:
                yield {key: _jsonable(value) for key, value in zip(cols, row, strict=True)}

    from analysis.lake.db import write_jsonl

    return write_jsonl(out_path, rows())


def _materialize_parquet(conn: Any, *, query: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    conn.execute("COPY (" + query + ") TO ? (FORMAT PARQUET)", [str(out_path)])


def _materialize_dashboard_v2(
    *,
    rows: list[tuple[str, str, str, str]],
    out_path: Path,
) -> int:
    from analysis.export_dashboard import export_run, write_manifest

    run_entries = []
    for _, _, _, run_dir in rows:
        run_entries.append(export_run(Path(run_dir).resolve(), out_path, None))
    default_run = run_entries[0]["id"] if run_entries else None
    write_manifest(out_path, run_entries, default_run)
    return len(run_entries)


def _resolve_logs_root_selection(
    selection: dict[str, Any],
    *,
    logs_root: Path | None,
) -> dict[str, Any]:
    resolved = dict(selection)
    if logs_root is None:
        return resolved
    root = logs_root.resolve()
    resolved.setdefault("run_dir_prefix", str(root))
    rel_run_dir = resolved.get("rel_run_dir")
    if rel_run_dir is not None:
        rel_values = [rel_run_dir] if isinstance(rel_run_dir, str) else list(rel_run_dir)
        resolved["run_dir"] = [str((root / rel).resolve()) for rel in rel_values]
        resolved.pop("rel_run_dir", None)
    return resolved


@dataclass(frozen=True)
class JobRunReport:
    job_run_id: str
    out_dir: Path
    selected_runs: int
    datasets_written: list[dict[str, Any]]
    ref_id: str | None


def run_job(
    conn: Any,
    *,
    job: dict[str, Any],
    logs_root: Path | None,
    out_dir: Path | None,
) -> JobRunReport:
    from analysis.lake.db import (
        _stable_id,
        resolve_lake_paths,
        utc_timestamp,
        write_json,
    )
    from analysis.lake.reference import build_goal_outcomes_reference
    from analysis.lake.score_k import score_k_for_run

    selection = _resolve_logs_root_selection(dict(job["selection"]), logs_root=logs_root)

    selection_meta = resolve_same_method_as_selection(conn, selection=selection)
    selected = create_selected_runs_view(conn, selection=selection)
    run_keys = selected["run_keys"]
    if not run_keys:
        raise ValueError("No runs selected (check lake reconcile and selection filters)")

    paths = resolve_lake_paths()
    if out_dir is None:
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        selection_key = json.dumps(selection, sort_keys=True)
        job_run_id = f"{timestamp}-{_stable_id(job['name'], selection_key, n=12)}"
        out_dir = paths.root / "jobs" / job["name"] / job_run_id
    else:
        job_run_id = _stable_id(job["name"], str(out_dir.resolve()), utc_timestamp(), n=12)
        out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ref_id: str | None = None
    reference_resolved: dict[str, Any] | None = None
    if job["reference"]:
        reference_resolved = dict(job["reference"])
        if "build_outcomes" in reference_resolved:
            ref_selection = reference_resolved.get("selection")
            if not isinstance(ref_selection, dict) or not ref_selection:
                raise ValueError(
                    "reference.selection must be a non-empty object "
                    "when reference.build_outcomes is set"
                )
            ref_selection = _resolve_logs_root_selection(ref_selection, logs_root=logs_root)
            ref_query, ref_params = build_selected_runs_query(selection=ref_selection)
            ref_rows = conn.execute(ref_query, ref_params).fetchall()
            ref_run_keys = [
                row[0]
                for row in ref_rows
                if isinstance(row, tuple) and row and isinstance(row[0], str)
            ]
            if not ref_run_keys:
                raise ValueError("No reference runs selected (check reference.selection filters)")

            build = reference_resolved.get("build_outcomes")
            if not isinstance(build, dict):
                raise ValueError("reference.build_outcomes must be an object")
            alpha = build.get("alpha", 1.0)
            if not isinstance(alpha, (int, float)) or float(alpha) <= 0:
                raise ValueError("reference.build_outcomes.alpha must be > 0")
            meta = build.get("meta", {})
            if meta is not None and not isinstance(meta, dict):
                raise ValueError("reference.build_outcomes.meta must be an object")
            report = build_goal_outcomes_reference(
                conn,
                run_keys=ref_run_keys,
                alpha=float(alpha),
                meta=meta or {},
            )
            ref_id = report.ref_id
            reference_resolved["ref_id"] = ref_id
            reference_resolved["artifact_path"] = str(report.artifact_path)
            reference_resolved["selection"] = ref_selection
            reference_resolved["members"] = {"count": len(ref_run_keys)}
        elif isinstance(reference_resolved.get("ref_id"), str):
            ref_id = reference_resolved["ref_id"]
        if reference_resolved.get("score_k") is True:
            if ref_id is None:
                raise ValueError("reference.score_k requires reference.ref_id or build_outcomes")
            rows = conn.execute(
                "SELECT run_key, run_dir FROM runs WHERE run_key IN ("
                + ",".join("?" for _ in run_keys)
                + ") ORDER BY run_key",
                run_keys,
            ).fetchall()
            for run_key, run_dir in rows:
                if not isinstance(run_key, str) or not isinstance(run_dir, str):
                    continue
                run_path = Path(run_dir).resolve()
                if run_path.exists():
                    score_k_for_run(conn, run_key=run_key, run_dir=run_path, ref_id=ref_id)

    conn.execute("DROP TABLE IF EXISTS job_context")
    conn.execute("CREATE TEMP TABLE job_context(ref_id VARCHAR)")
    if ref_id is not None:
        conn.execute("INSERT INTO job_context VALUES (?)", [ref_id])

    datasets_written: list[dict[str, Any]] = []
    datasets_manifest: list[dict[str, Any]] = []
    for dataset in job["datasets"]:
        generator = dataset.get("generator")
        query = dataset.get("query")

        file_name = dataset.get("file")
        if file_name is None:
            if dataset["format"] == "jsonl":
                file_name = dataset["name"] + ".jsonl"
            elif dataset["format"] == "parquet":
                file_name = dataset["name"] + ".parquet"
            else:
                file_name = dataset["name"]
        out_path = out_dir / file_name
        if generator is not None:
            if generator != "wonton_dashboard_v2":
                raise ValueError(f"Unknown dataset generator: {generator!r}")
            if dataset["format"] != "dir":
                raise ValueError(
                    "dataset generator 'wonton_dashboard_v2' requires format='dir'"
                )
            run_count = _materialize_dashboard_v2(
                rows=list(selected["rows"]),
                out_path=out_path,
            )
            datasets_written.append(
                {
                    "name": dataset["name"],
                    "path": file_name,
                    "format": dataset["format"],
                    "runs": run_count,
                }
            )
        elif dataset["format"] == "jsonl":
            if not isinstance(query, str):
                raise ValueError(f"dataset {dataset.get('name')!r} missing query")
            if "order by" not in query.lower():
                raise ValueError(
                    f"dataset {dataset['name']!r} query must include ORDER BY for "
                    "deterministic JSONL exports"
                )
            row_count = _materialize_jsonl(conn, query=query, out_path=out_path)
            datasets_written.append(
                {
                    "name": dataset["name"],
                    "path": file_name,
                    "format": dataset["format"],
                    "rows": row_count,
                }
            )
        else:
            if not isinstance(query, str):
                raise ValueError(f"dataset {dataset.get('name')!r} missing query")
            _materialize_parquet(conn, query=query, out_path=out_path)
            datasets_written.append(
                {"name": dataset["name"], "path": file_name, "format": dataset["format"]}
            )
        datasets_manifest.append(
            {"name": dataset["name"], "path": file_name, "format": dataset["format"]}
        )

    manifest = {
        "schema_version": 1,
        "format": "specter-viz",
        "job": {
            "name": job["name"],
            "job_run_id": job_run_id,
            "created_at": utc_timestamp(),
            "selected_runs": selected["count"],
        },
        "selection_stats": selected.get("selection_stats", {}),
        "selection_meta": selection_meta or {},
        "selection": selection,
        "reference": reference_resolved or {},
        "datasets": datasets_manifest,
    }
    write_json(out_dir / "manifest.json", manifest)

    inputs = {"selected_runs": [{"run_key": run_key} for run_key in run_keys]}
    write_json(out_dir / "inputs.json", inputs)
    job_payload = dict(job)
    job_payload["reference"] = job_payload["reference"] or {}
    write_json(out_dir / "job_config.json", job_payload)

    conn.execute(
        """
        INSERT INTO lake_job_runs(
          job_run_id, job_name, status, out_dir, logs_root, selection, reference, datasets, inputs
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            job_run_id,
            job["name"],
            "completed",
            str(out_dir),
            str(logs_root) if logs_root is not None else None,
            json.dumps(selection),
            json.dumps(reference_resolved) if reference_resolved is not None else None,
            json.dumps(datasets_manifest),
            json.dumps(inputs),
        ],
    )
    return JobRunReport(
        job_run_id=job_run_id,
        out_dir=out_dir,
        selected_runs=selected["count"],
        datasets_written=datasets_written,
        ref_id=ref_id,
    )
