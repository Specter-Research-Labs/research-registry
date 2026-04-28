from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from analysis import postprocess_metrics
from analysis.logs import read_json, sha256_file, write_json_atomic

PostprocessParams = postprocess_metrics.PostprocessParams


@dataclass(frozen=True)
class PostprocessRunState:
    run_dir: Path
    run_id: str | None
    created_at: str | None
    eligible: bool
    needs_processing: bool
    reason: str


@dataclass(frozen=True)
class PostprocessBatchReport:
    discovered: int
    eligible: int
    pending: int
    processed: int
    succeeded: int
    failed: int
    skipped: int
    states: list[PostprocessRunState]
    failures: list[dict[str, str]]


def inspect_postprocess_run_state(
    run_dir: Path,
    *,
    params: PostprocessParams,
    include_partial: bool,
) -> PostprocessRunState:
    run_id: str | None = None
    created_at: str | None = None
    run_config_path = run_dir / "run_config.json"
    if run_config_path.exists():
        try:
            cfg = read_json(run_config_path)
        except Exception:
            cfg = None
        if isinstance(cfg, dict):
            run_id_raw = cfg.get("run_id")
            if isinstance(run_id_raw, str) and run_id_raw:
                run_id = run_id_raw
            created_raw = cfg.get("created_at")
            if isinstance(created_raw, str) and created_raw:
                created_at = created_raw

    summary_path = run_dir / "summary.json.gz"
    if not summary_path.exists():
        return PostprocessRunState(
            run_dir=run_dir,
            run_id=run_id,
            created_at=created_at,
            eligible=False,
            needs_processing=False,
            reason="missing_summary",
        )

    run_status_path = run_dir / "run_status.json"
    if not run_status_path.exists():
        return PostprocessRunState(
            run_dir=run_dir,
            run_id=run_id,
            created_at=created_at,
            eligible=False,
            needs_processing=False,
            reason="missing_run_status",
        )

    try:
        run_status = read_json(run_status_path)
    except Exception:
        run_status = None
    if not isinstance(run_status, dict):
        return PostprocessRunState(
            run_dir=run_dir,
            run_id=run_id,
            created_at=created_at,
            eligible=False,
            needs_processing=False,
            reason="invalid_run_status",
        )

    status = run_status.get("status")
    partial_results = run_status.get("partial_results") is True
    status_ok = status == "completed" or (include_partial and partial_results)
    if not status_ok:
        return PostprocessRunState(
            run_dir=run_dir,
            run_id=run_id,
            created_at=created_at,
            eligible=False,
            needs_processing=False,
            reason="ineligible_status",
        )

    summary_sha = sha256_file(summary_path)
    goal_cache_sha = sha256_file(run_dir / "goal_cache.json.gz")
    metrics_path = run_dir / "postprocess_metrics.json"
    if not metrics_path.exists():
        return PostprocessRunState(
            run_dir=run_dir,
            run_id=run_id,
            created_at=created_at,
            eligible=True,
            needs_processing=True,
            reason="missing_postprocess_metrics",
        )

    try:
        metrics = read_json(metrics_path)
    except Exception:
        metrics = None
    if not isinstance(metrics, dict):
        return PostprocessRunState(
            run_dir=run_dir,
            run_id=run_id,
            created_at=created_at,
            eligible=True,
            needs_processing=True,
            reason="invalid_postprocess_metrics",
        )

    inputs = metrics.get("inputs")
    if not isinstance(inputs, dict):
        return PostprocessRunState(
            run_dir=run_dir,
            run_id=run_id,
            created_at=created_at,
            eligible=True,
            needs_processing=True,
            reason="missing_inputs_hashes",
        )
    prev_summary = inputs.get("summary_sha256")
    prev_goal_cache = inputs.get("goal_cache_sha256")
    if prev_summary != summary_sha or prev_goal_cache != goal_cache_sha:
        return PostprocessRunState(
            run_dir=run_dir,
            run_id=run_id,
            created_at=created_at,
            eligible=True,
            needs_processing=True,
            reason="stale_inputs",
        )

    prev_params = metrics.get("params")
    if not isinstance(prev_params, dict):
        return PostprocessRunState(
            run_dir=run_dir,
            run_id=run_id,
            created_at=created_at,
            eligible=True,
            needs_processing=True,
            reason="missing_params",
        )
    expected_params = postprocess_metrics._staleness_params(params)
    for key, expected in expected_params.items():
        if prev_params.get(key) != expected:
            return PostprocessRunState(
                run_dir=run_dir,
                run_id=run_id,
                created_at=created_at,
                eligible=True,
                needs_processing=True,
                reason="stale_params",
            )

    return PostprocessRunState(
        run_dir=run_dir,
        run_id=run_id,
        created_at=created_at,
        eligible=True,
        needs_processing=False,
        reason="up_to_date",
    )


def _parse_created_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def discover_postprocess_run_states(
    logs_dirs: list[Path],
    *,
    params: PostprocessParams,
    include_partial: bool,
) -> list[PostprocessRunState]:
    run_dirs: dict[Path, Path] = {}
    for root in logs_dirs:
        if not root.exists():
            continue
        for cfg_path in root.rglob("run_config.json"):
            run_dir = cfg_path.parent.resolve()
            parent_cfg = run_dir.parent / "run_config.json"
            if run_dir.name.startswith("provider=") and parent_cfg.exists():
                continue
            run_dirs[run_dir] = run_dir

    states = [
        inspect_postprocess_run_state(
            run_dir=run_dir,
            params=params,
            include_partial=include_partial,
        )
        for run_dir in run_dirs.values()
    ]

    def _sort_key(state: PostprocessRunState) -> tuple[int, str, str]:
        created = _parse_created_at(state.created_at)
        if created is not None:
            return (0, created.isoformat(), state.run_dir.as_posix())
        run_key = state.run_id if state.run_id else state.run_dir.name
        return (1, run_key, state.run_dir.as_posix())

    states.sort(key=_sort_key)
    return states


def postprocess_unprocessed_runs(
    *,
    logs_dirs: list[Path],
    params: PostprocessParams,
    include_partial: bool = True,
    limit: int | None = None,
    continue_on_error: bool = True,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> PostprocessBatchReport:
    states = discover_postprocess_run_states(
        logs_dirs,
        params=params,
        include_partial=include_partial,
    )
    eligible_states = [state for state in states if state.eligible]
    pending_states = [state for state in eligible_states if state.needs_processing]
    if limit is not None:
        pending_states = pending_states[: max(0, limit)]

    failures: list[dict[str, str]] = []
    succeeded = 0
    processed = 0

    total_runs = len(pending_states)
    for idx, state in enumerate(pending_states, start=1):
        if progress_cb is not None:
            progress_cb(
                {
                    "event": "postprocess_batch_run_start",
                    "run_idx": idx,
                    "runs_total": total_runs,
                    "run_dir": str(state.run_dir),
                    "reason": state.reason,
                }
            )
        try:
            report = postprocess_metrics.postprocess_run(state.run_dir, params=params)
            write_json_atomic(state.run_dir / "postprocess_metrics.json", report)
            succeeded += 1
            processed += 1
            if progress_cb is not None:
                progress_cb(
                    {
                        "event": "postprocess_batch_run_end",
                        "run_idx": idx,
                        "runs_total": total_runs,
                        "run_dir": str(state.run_dir),
                        "status": "completed",
                    }
                )
        except Exception as exc:
            processed += 1
            failures.append(
                {
                    "run_dir": str(state.run_dir),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            if progress_cb is not None:
                progress_cb(
                    {
                        "event": "postprocess_batch_run_end",
                        "run_idx": idx,
                        "runs_total": total_runs,
                        "run_dir": str(state.run_dir),
                        "status": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            if not continue_on_error:
                break

    failed = len(failures)
    skipped = len(states) - processed
    return PostprocessBatchReport(
        discovered=len(states),
        eligible=len(eligible_states),
        pending=len(pending_states),
        processed=processed,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        states=states,
        failures=failures,
    )
