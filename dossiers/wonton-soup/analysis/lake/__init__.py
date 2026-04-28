from __future__ import annotations

from analysis.lake.db import LakePaths, connect, ensure_schema, resolve_lake_paths
from analysis.lake.export_parquet import export_parquet
from analysis.lake.extract import extract_facts
from analysis.lake.index import index_logs
from analysis.lake.job import load_job_config, run_job
from analysis.lake.reference import build_goal_outcomes_reference
from analysis.lake.score_k import score_k_for_run

__all__ = [
    "LakePaths",
    "connect",
    "ensure_schema",
    "resolve_lake_paths",
    "index_logs",
    "extract_facts",
    "export_parquet",
    "build_goal_outcomes_reference",
    "score_k_for_run",
    "load_job_config",
    "run_job",
]
