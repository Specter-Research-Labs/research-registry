from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from analysis.lake.db import root_id_for_path, run_key_for_run_dir
from analysis.logs import (
    ProviderRun,
    iter_provider_runs,
    read_json,
    read_json_gz,
    relpath_under,
    sha256_file,
)


def _maybe_read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return read_json(path)
    except Exception:
        return None


def _maybe_read_json_gz(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return read_json_gz(path)
    except Exception:
        return None


def _maybe_read_json_with_error(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, None
    try:
        return read_json(path), None
    except Exception as exc:
        return None, f"{path.name}: {type(exc).__name__}: {exc}"


def _maybe_read_json_gz_with_error(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, None
    try:
        return read_json_gz(path), None
    except Exception as exc:
        return None, f"{path.name}: {type(exc).__name__}: {exc}"


def _get_str(d: dict[str, Any], key: str) -> str | None:
    value = d.get(key)
    return value if isinstance(value, str) else None


def _get_bool(d: dict[str, Any], key: str) -> bool | None:
    value = d.get(key)
    return value if isinstance(value, bool) else None


def _get_dict(d: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = d.get(key)
    return value if isinstance(value, dict) else None


_RUN_CONFIG_EPHEMERAL_KEYS = {
    # Per-run fields that should not affect "configuration identity".
    "run_id",
    "created_at",
    "log_dir",
    # Includes pid and other per-run environment details.
    "runtime",
}

def _method_view(run_config: dict[str, Any]) -> dict[str, Any]:
    """Return the run's methodological configuration.

    This is the "cohorting" view: it should include the knobs that change behavior/semantics,
    but exclude per-run selection ephemera and UI/runtime noise.
    """

    out: dict[str, Any] = {}

    # Top-level behavioral configuration.
    for k in (
        "format_version",
        "backend",
        "mode",
        "corpus",
        "corpus_spec",
        "corpus_artifact",
        "goal_sig_scheme",
        "trace_mcts",
        "analysis",
        "workers",
        "allow_easy",
        "sampling",
        "basin_seeds",
        "mcts_mode",
        "distributed_mcts",
        "mode_defaults",
        "guidance",
        "mcts",
        "interventions",
        "problem_space",
    ):
        if k in run_config:
            out[k] = run_config[k]

    # Provider configuration (structured).
    providers_meta = run_config.get("providers_meta")
    if isinstance(providers_meta, dict):
        # Keep structured config; drop freeform descriptions to avoid accidental drift causing
        # cohort fragmentation.
        pm: dict[str, Any] = {}
        for k in ("names", "primary", "label", "config"):
            if k in providers_meta:
                pm[k] = providers_meta[k]
        if pm:
            out["providers_meta"] = pm

    return out


def _full_view(run_config: dict[str, Any]) -> dict[str, Any]:
    """Return the full configuration view used for strict equality checks.

    This includes the method view plus theorem selection details so two runs with the same cohort
    but different selected theorem sets do not collapse to the same hash.
    """

    out = {"method": _method_view(run_config)}
    sel = run_config.get("theorem_selection")
    if isinstance(sel, dict):
        out["theorem_selection"] = sel
    return out


def _canonical_json(value: Any) -> str:
    # Canonical encoding for stable hashing and provenance records.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _stable_hash(value: Any) -> str:
    h = hashlib.sha256(_canonical_json(value).encode("utf-8"))
    return h.hexdigest()


def _sanitize_run_config(run_config: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in run_config.items():
        if k in _RUN_CONFIG_EPHEMERAL_KEYS:
            continue
        out[k] = v
    return out


@dataclass(frozen=True)
class IndexReport:
    roots_indexed: int
    runs_indexed: int
    files_indexed: int
    errors: list[str]


def _discover_nested_provider_runs(root: Path, *, max_depth: int = 6) -> list[ProviderRun]:
    runs: list[ProviderRun] = []
    candidate_dirs = sorted(p.parent for p in root.rglob("run_config.json"))
    for candidate in candidate_dirs:
        try:
            rel_parts = candidate.resolve().relative_to(root.resolve()).parts
        except ValueError:
            continue
        if not rel_parts or len(rel_parts) > max_depth:
            continue
        if any(part.startswith(".") for part in rel_parts):
            continue
        try:
            runs.extend(iter_provider_runs(candidate))
        except FileNotFoundError:
            continue
    return runs


def discover_run_dirs(logs_dir: Path) -> list[ProviderRun]:
    """Discover single-provider run dirs under a logs root.

    This first scans one directory level under logs_dir (standard layout) and then falls back to a
    bounded nested search for wrapper layouts that contain run dirs below the top level.
    """

    runs: list[ProviderRun] = []
    if not logs_dir.exists():
        return runs
    for child in sorted(p for p in logs_dir.iterdir() if p.is_dir()):
        try:
            runs.extend(iter_provider_runs(child))
        except FileNotFoundError:
            runs.extend(_discover_nested_provider_runs(child))
    # Deduplicate (some callers may pass a provider dir directly).
    seen: set[Path] = set()
    out: list[ProviderRun] = []
    for r in runs:
        if r.run_dir in seen:
            continue
        seen.add(r.run_dir)
        out.append(r)
    return out


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _canonical_root_for_run(
    *,
    run_dir: Path,
    roots: list[tuple[str, Path]],
) -> tuple[str, str]:
    candidates = [(root_id, root_path) for root_id, root_path in roots if _path_is_under(run_dir, root_path)]
    if not candidates:
        raise RuntimeError(f"No enclosing log root found for run_dir {run_dir}")
    candidates.sort(key=lambda item: (len(item[1].parts), len(str(item[1])), str(item[1])))
    root_id, root_path = candidates[0]
    return root_id, relpath_under(root_path, run_dir)


def index_logs(
    conn: duckdb.DuckDBPyConnection,
    *,
    logs_dirs: list[Path],
) -> IndexReport:
    errors: list[str] = []
    roots_indexed = 0
    runs_indexed = 0
    files_indexed = 0

    resolved_logs_dirs = [logs_dir.resolve() for logs_dir in logs_dirs]
    for logs_dir in resolved_logs_dirs:
        root_id = root_id_for_path(logs_dir)
        # Avoid dialect-specific upsert syntax; keep this compatible across DuckDB versions.
        exists = conn.execute(
            "SELECT 1 FROM log_roots WHERE root_id = ? LIMIT 1",
            [root_id],
        ).fetchone()
        if exists is None:
            conn.execute(
                "INSERT INTO log_roots(root_id, root_path) VALUES (?, ?)",
                [root_id, str(logs_dir)],
            )
        roots_indexed += 1

    root_rows = conn.execute(
        "SELECT root_id, root_path FROM log_roots ORDER BY root_path"
    ).fetchall()
    known_roots = [
        (root_id, Path(root_path).resolve())
        for root_id, root_path in root_rows
        if isinstance(root_id, str) and isinstance(root_path, str)
    ]

    for logs_dir in resolved_logs_dirs:
        for provider_run in discover_run_dirs(logs_dir):
            run_dir = provider_run.run_dir.resolve()
            root_id, rel_run_dir = _canonical_root_for_run(
                run_dir=run_dir,
                roots=known_roots,
            )
            run_key = run_key_for_run_dir(run_dir)

            run_config, cfg_err = _maybe_read_json_with_error(run_dir / "run_config.json")
            if cfg_err:
                errors.append(f"{rel_run_dir}: {cfg_err}")
            run_status, status_err = _maybe_read_json_with_error(run_dir / "run_status.json")
            if status_err:
                errors.append(f"{rel_run_dir}: {status_err}")
            summary_gz, summary_gz_err = _maybe_read_json_gz_with_error(run_dir / "summary.json.gz")
            if summary_gz_err:
                errors.append(f"{rel_run_dir}: {summary_gz_err}")
            if summary_gz is not None:
                summary = summary_gz
            else:
                summary, summary_err = _maybe_read_json_with_error(run_dir / "summary.json")
                if summary_err:
                    errors.append(f"{rel_run_dir}: {summary_err}")

            run_id = None
            provider = provider_run.provider
            backend = None
            mode = None
            corpus = None
            created_at = None
            trace_mcts = None
            problem_space = None
            config_whitelist_hash = None
            config_full_hash = None
            if isinstance(run_config, dict):
                run_id = _get_str(run_config, "run_id")
                backend = _get_str(run_config, "backend")
                mode = _get_str(run_config, "mode")
                corpus = _get_str(run_config, "corpus")
                created_at = _get_str(run_config, "created_at")
                if provider is None:
                    provider = _get_str(run_config, "provider")
                trace_mcts = _get_bool(run_config, "trace_mcts")
                problem_space = _get_dict(run_config, "problem_space")
                # Hashes for cohorting and drift detection.
                sanitized = _sanitize_run_config(run_config)
                config_whitelist_hash = _stable_hash(_method_view(sanitized))
                config_full_hash = _stable_hash(_full_view(sanitized))

            goal_sig_scheme = None
            if isinstance(run_config, dict):
                # Basin-mode runs often skip summary.json, so carry goal signature from
                # run_config to keep selection filters (e.g., goal_sig_scheme=ast) usable.
                goal_sig_scheme = _get_str(run_config, "goal_sig_scheme")
            if isinstance(summary, dict):
                summary_goal_sig_scheme = summary.get("goal_sig_scheme")
                if isinstance(summary_goal_sig_scheme, str):
                    goal_sig_scheme = summary_goal_sig_scheme

            # Atomic upsert: delete+insert in a single transaction to avoid partial state on crash.
            conn.begin()
            conn.execute("DELETE FROM run_files WHERE run_key = ?", [run_key])
            conn.execute("DELETE FROM runs WHERE run_key = ?", [run_key])

            conn.execute(
                """
                INSERT INTO runs(
                  run_key, root_id, rel_run_dir, run_dir,
                  run_id, provider, backend, mode, corpus, created_at,
                  goal_sig_scheme, trace_mcts, problem_space,
                  config_whitelist_hash, config_full_hash,
                  run_config, run_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_key,
                    root_id,
                    rel_run_dir,
                    str(run_dir),
                    run_id,
                    provider,
                    backend,
                    mode,
                    corpus,
                    created_at,
                    goal_sig_scheme,
                    trace_mcts,
                    json.dumps(problem_space) if problem_space is not None else None,
                    config_whitelist_hash,
                    config_full_hash,
                    json.dumps(run_config) if run_config is not None else None,
                    json.dumps(run_status) if run_status is not None else None,
                ],
            )

            for name in (
                "run_config.json",
                "run_status.json",
                "summary.json.gz",
                "summary.json",
                "goal_cache.json.gz",
                "goal_cache.json",
                "postprocess_metrics.json",
                "root_goal_similarity.json",
                "external_statement_similarity.json",
                "providers_summary.json",
                "basin_analysis.json",
                "failure_analysis.json",
                "attractor_clusters.json",
                "sheaf_analysis.json",
            ):
                path = run_dir / name
                # postprocess_metrics.json is written at the multi-provider root
                # (parent of provider=*).
                if (
                    name == "postprocess_metrics.json"
                    and not path.exists()
                    and run_dir.name.startswith("provider=")
                ):
                    path = run_dir.parent / name
                if not path.exists():
                    continue
                sha = sha256_file(path)
                st = path.stat()
                conn.execute(
                    """
                    INSERT INTO run_files(run_key, file_name, sha256, bytes, mtime_epoch)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [run_key, name, sha, int(st.st_size), int(st.st_mtime)],
                )
                files_indexed += 1
            conn.commit()
            runs_indexed += 1

    return IndexReport(
        roots_indexed=roots_indexed,
        runs_indexed=runs_indexed,
        files_indexed=files_indexed,
        errors=errors,
    )
