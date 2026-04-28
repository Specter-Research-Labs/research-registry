from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from analysis.lake.db import connect, ensure_schema, root_id_for_path
from analysis.lake.extract import extract_facts
from analysis.lake.index import index_logs
from analysis.lake.job import load_job_config, run_job


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(payload, f)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _summary(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "goal_sig_scheme": "ast",
        "theorems": [
            {
                "name": "t1",
                "wild_type": {"solved": True, "iterations": 2, "metrics": {}},
                "interventions": [
                    {
                        "name": "block_intro",
                        "blocked": ["intro"],
                        "solved": True,
                        "status": "solved",
                        "metrics": {},
                        "ged_search_graph": {"value": 1.0, "normalized": 0.25},
                    }
                ],
            }
        ],
        "aggregates": {},
    }


CAPABILITIES_ALL = {
    "has_proof_term": True,
    "has_proof_term_pretty": True,
    "has_assembly_trace": True,
    "has_proof_term_metrics": True,
}


def _run_status(
    *,
    status: str = "completed",
    partial_results: bool = False,
    capabilities: dict[str, bool] | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "partial_results": partial_results,
        "goal_id_scheme": "checkpoint",
        "capabilities": capabilities or CAPABILITIES_ALL,
    }


def _write_run(
    logs_root: Path,
    rel_run_dir: str,
    *,
    run_id: str,
    provider: str,
    mode: str = "research",
    corpus: str = "expanded",
    config_extra: dict[str, object] | None = None,
    status: dict[str, object] | None = None,
) -> Path:
    run_dir = logs_root / rel_run_dir
    config: dict[str, object] = {
        "run_id": run_id,
        "backend": "lean",
        "provider": provider,
        "mode": mode,
        "corpus": corpus,
        "trace_mcts": True,
    }
    if config_extra:
        config.update(config_extra)
    _write_json(run_dir / "run_config.json", config)
    if status is not None:
        _write_json(run_dir / "run_status.json", status)
    _write_json_gz(run_dir / "summary.json.gz", _summary(run_id))
    return run_dir


@contextmanager
def _indexed_lake(
    tmp_path: Path,
    logs_root: Path,
    *,
    index_roots: list[Path] | None = None,
    extract_root: Path | None = None,
    with_goal_outcomes: bool = False,
) -> Iterator[Any]:
    conn = connect(tmp_path / "lake.duckdb")
    try:
        ensure_schema(conn)
        for root in index_roots or [logs_root]:
            index_logs(conn, logs_dirs=[root])
        root = extract_root or logs_root
        rid = root_id_for_path(root)
        run_rows = conn.execute(
            "SELECT run_key, rel_run_dir FROM runs WHERE root_id = ?",
            [rid],
        ).fetchall()
        extract_facts(
            conn,
            root_dir=root,
            run_rows=[(rk, rel) for rk, rel in run_rows],
            with_goal_outcomes=with_goal_outcomes,
        )
        yield conn
    finally:
        conn.close()


def _job_payload(
    *,
    name: str,
    selection: dict[str, object],
    datasets: list[dict[str, object]],
    reference: object = None,
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "name": name,
        "selection": selection,
        "reference": reference,
        "datasets": datasets,
    }


def _run_job_payload(
    conn: Any,
    tmp_path: Path,
    logs_root: Path,
    payload: dict[str, object],
    *,
    config_name: str = "job.json",
    out_name: str = "out",
) -> tuple[Any, Path]:
    job_cfg = tmp_path / config_name
    _write_json(job_cfg, payload)
    out_dir = tmp_path / out_name
    return run_job(
        conn, job=load_job_config(job_cfg), logs_root=logs_root, out_dir=out_dir
    ), out_dir


def test_lake_job_run_smoke(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    run_dir = _write_run(
        logs_root,
        "corpus-1",
        run_id="corpus-1",
        provider="reprover",
        mode="dev",
        corpus="easy",
    )
    _write_json_gz(
        run_dir / "goal_cache.json.gz",
        {
            "entries": {
                "sigA": {
                    "occurrences": {
                        "m1": {"outcomes": {"2": [True, False], "4": [False]}},
                    }
                }
            }
        },
    )

    with _indexed_lake(tmp_path, logs_root, with_goal_outcomes=True) as conn:
        rep, out_dir = _run_job_payload(
            conn,
            tmp_path,
            logs_root,
            _job_payload(
                name="smoke_job",
                selection={"provider": ["reprover"]},
                reference={
                    "selection": {"provider": ["reprover"]},
                    "build_outcomes": {"alpha": 1.0},
                },
                datasets=[
                    {
                        "name": "wild",
                        "format": "jsonl",
                        "query": (
                            "SELECT w.* FROM theorem_wild w "
                            "JOIN selected_runs r USING(run_key) "
                            "ORDER BY w.run_key, w.theorem"
                        ),
                    }
                ],
            ),
        )
        assert (out_dir / "manifest.json").exists()
        assert (out_dir / "wild.jsonl").exists()
        assert rep.selected_runs == 1
        assert rep.ref_id is not None

        job_row = conn.execute(
            "SELECT status, out_dir FROM lake_job_runs WHERE job_run_id = ?",
            [rep.job_run_id],
        ).fetchone()
        assert job_row is not None
        assert job_row[0] == "completed"


def test_lake_job_same_method_as_run_id(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"

    def write_run(run_id: str, provider: str) -> None:
        _write_run(
            logs_root,
            run_id,
            run_id=run_id,
            provider=provider,
            mode="dev",
            corpus="easy",
            config_extra={
                "providers_meta": {"config": {"provider": provider}},
                "problem_space": {"schema_version": 1, "P": {"S": {"repr": "goal_sig"}}},
            },
        )

    write_run("corpus-1", "reprover")
    write_run("corpus-2", "reprover")
    write_run("corpus-3", "deepseek")

    with _indexed_lake(tmp_path, logs_root) as conn:
        rep, out_dir = _run_job_payload(
            conn,
            tmp_path,
            logs_root,
            _job_payload(
                name="same_method",
                selection={"same_method_as": {"run_id": "corpus-1"}},
                datasets=[
                    {
                        "name": "runs",
                        "format": "jsonl",
                        "query": (
                            "SELECT r.run_id, r.provider, r.config_whitelist_hash "
                            "FROM runs r JOIN selected_runs s USING(run_key) "
                            "ORDER BY r.run_id"
                        ),
                    }
                ],
            ),
        )
        assert rep.selected_runs == 2

        rows = _read_jsonl(out_dir / "runs.jsonl")
        assert [r["run_id"] for r in rows] == ["corpus-1", "corpus-2"]
        assert rows[0]["config_whitelist_hash"] == rows[1]["config_whitelist_hash"]


def test_lake_job_selection_rel_run_dir(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"

    _write_run(
        logs_root,
        "matrix/deepseek/centralized-no-basin",
        run_id="matrix-centralized",
        provider="deepseek",
    )
    _write_run(
        logs_root,
        "matrix/deepseek/distributed-no-basin",
        run_id="matrix-distributed",
        provider="deepseek",
    )
    _write_run(
        logs_root,
        "matrix/reprover/distributed",
        run_id="matrix-reprover",
        provider="reprover",
    )

    with _indexed_lake(tmp_path, logs_root) as conn:
        report, out_dir = _run_job_payload(
            conn,
            tmp_path,
            logs_root,
            _job_payload(
                name="rel_run_dir_selection",
                selection={
                    "rel_run_dir": [
                        "matrix/deepseek/centralized-no-basin",
                        "matrix/deepseek/distributed-no-basin",
                    ]
                },
                datasets=[
                    {
                        "name": "runs",
                        "format": "jsonl",
                        "query": (
                            "SELECT run_id, rel_run_dir FROM runs "
                            "JOIN selected_runs USING(run_key) "
                            "ORDER BY rel_run_dir"
                        ),
                    }
                ],
            ),
        )
        assert report.selected_runs == 2

        rows = _read_jsonl(out_dir / "runs.jsonl")
        assert [row["run_id"] for row in rows] == ["matrix-centralized", "matrix-distributed"]
        assert [row["rel_run_dir"] for row in rows] == [
            "matrix/deepseek/centralized-no-basin",
            "matrix/deepseek/distributed-no-basin",
        ]


def test_lake_job_selection_rel_run_dir_under_child_logs_root(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    child_root = logs_root / "matrix"

    _write_run(
        child_root,
        "deepseek/centralized-no-basin",
        run_id="matrix-centralized",
        provider="deepseek",
    )
    _write_run(
        child_root,
        "deepseek/distributed-no-basin",
        run_id="matrix-distributed",
        provider="deepseek",
    )

    with _indexed_lake(
        tmp_path,
        logs_root,
        index_roots=[logs_root, child_root],
    ) as conn:
        report, out_dir = _run_job_payload(
            conn,
            tmp_path,
            child_root,
            _job_payload(
                name="child_rel_run_dir_selection",
                selection={
                    "rel_run_dir": [
                        "deepseek/centralized-no-basin",
                        "deepseek/distributed-no-basin",
                    ]
                },
                datasets=[
                    {
                        "name": "runs",
                        "format": "jsonl",
                        "query": (
                            "SELECT run_id, rel_run_dir FROM runs "
                            "JOIN selected_runs USING(run_key) "
                            "ORDER BY rel_run_dir"
                        ),
                    }
                ],
            ),
            config_name="job-child.json",
            out_name="out-child",
        )
        assert report.selected_runs == 2

        rows = _read_jsonl(out_dir / "runs.jsonl")
        assert [row["run_id"] for row in rows] == ["matrix-centralized", "matrix-distributed"]
        assert [row["rel_run_dir"] for row in rows] == [
            "matrix/deepseek/centralized-no-basin",
            "matrix/deepseek/distributed-no-basin",
        ]


def test_lake_job_dashboard_generator(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"

    for rel_run_dir, run_id in (
        ("deepseek/centralized-no-basin", "matrix-centralized"),
        ("deepseek/distributed-no-basin", "matrix-distributed"),
    ):
        _write_run(
            logs_root,
            rel_run_dir,
            run_id=run_id,
            provider="deepseek",
            corpus="matrix",
            config_extra={"theorem_selection": {"selected_count": 1}},
            status=_run_status(),
        )

    with _indexed_lake(tmp_path, logs_root) as conn:
        report, out_dir = _run_job_payload(
            conn,
            tmp_path,
            logs_root,
            _job_payload(
                name="dashboard_bundle",
                selection={
                    "rel_run_dir": [
                        "deepseek/centralized-no-basin",
                        "deepseek/distributed-no-basin",
                    ],
                    "require_completed": True,
                },
                datasets=[
                    {
                        "name": "wonton_dashboard_v2",
                        "generator": "wonton_dashboard_v2",
                        "format": "dir",
                    }
                ],
            ),
            config_name="dashboard-job.json",
        )

        assert report.selected_runs == 2
        assert (out_dir / "wonton_dashboard_v2" / "data" / "manifest.json").exists()


def test_lake_job_selection_quality_gates(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"

    caps_missing = dict(CAPABILITIES_ALL)
    caps_missing["has_proof_term_metrics"] = False

    for dir_name, run_id, created_at, status, partial_results, capabilities in (
        ("a-old", "corpus-a", "2026-02-10T01:00:00", "completed", False, CAPABILITIES_ALL),
        (
            "a-new-missing-cap",
            "corpus-a",
            "2026-02-14T01:00:00",
            "completed",
            False,
            caps_missing,
        ),
        ("b-partial", "corpus-b", "2026-02-15T01:00:00", "completed", True, CAPABILITIES_ALL),
        ("c-running", "corpus-c", "2026-02-16T01:00:00", "running", False, CAPABILITIES_ALL),
        ("d-complete", "corpus-d", "2026-02-17T01:00:00", "completed", False, CAPABILITIES_ALL),
    ):
        _write_run(
            logs_root,
            dir_name,
            run_id=run_id,
            provider="reprover",
            config_extra={
                "created_at": created_at,
                "providers_meta": {"config": {"provider": "reprover"}},
            },
            status=_run_status(
                status=status,
                partial_results=partial_results,
                capabilities=capabilities,
            ),
        )

    with _indexed_lake(tmp_path, logs_root) as conn:
        report, out_dir = _run_job_payload(
            conn,
            tmp_path,
            logs_root,
            _job_payload(
                name="quality_gated_selection",
                selection={
                    "require_completed": True,
                    "exclude_partial_results": True,
                    "require_capabilities": [
                        "has_proof_term",
                        "has_proof_term_pretty",
                        "has_assembly_trace",
                        "has_proof_term_metrics",
                    ],
                    "order_by": "created_at_desc",
                    "dedupe_run_id": True,
                    "max_runs": 2,
                },
                datasets=[
                    {
                        "name": "runs",
                        "format": "jsonl",
                        "query": (
                            "SELECT run_id, created_at FROM runs "
                            "JOIN selected_runs USING(run_key) "
                            "ORDER BY created_at DESC, run_id"
                        ),
                    }
                ],
            ),
        )
        assert report.selected_runs == 2

        rows = _read_jsonl(out_dir / "runs.jsonl")
        assert [row["run_id"] for row in rows] == ["corpus-d", "corpus-a"]

        manifest = _read_json(out_dir / "manifest.json")
        stats = manifest.get("selection_stats")
        assert isinstance(stats, dict)
        assert stats.get("require_completed") is True
        assert stats.get("exclude_partial_results") is True
        assert stats.get("dedupe_run_id") is True
        assert stats.get("max_runs") == 2
