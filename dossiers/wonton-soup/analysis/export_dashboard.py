# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, TypedDict

if __package__ in (None, ""):
    raise RuntimeError(
        "Run this module as `python -m analysis.export_dashboard` from the dossier root."
    )

from .logs import inspect_run_artifacts, relpath_under
from .run_metadata import (
    build_run_label,
    build_run_meta,
    load_json_mapping,
    load_run_snapshot,
)
from .viz_payloads import build_dashboard_payload_v2
from .viz_server import resolve_logs_dir


class RunEntry(TypedDict):
    id: str
    label: str
    dashboard: str | None
    meta: dict[str, Any] | None


class DashboardRunIncompatibleError(RuntimeError):
    pass


def _validate_run_id(value: Any, *, source: Path) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Invalid run_id in {source}")
    if "/" in value or "\\" in value:
        raise RuntimeError(f"Invalid run_id in {source}: path separators are not allowed")
    return value


def _normalize_dashboard_run_id(value: Any, *, fallback: str, source: Path) -> str:
    if value is None:
        return _validate_run_id(fallback, source=source)
    if not isinstance(value, str):
        raise RuntimeError(f"Invalid run_id in {source}")
    normalized = value.strip().replace("\\", "/").strip("/")
    if not normalized:
        raise RuntimeError(f"Invalid run_id in {source}")
    if "/" in normalized:
        normalized = normalized.replace("/", "__")
    return _validate_run_id(normalized, source=source)


def _fallback_run_id_from_dir(run_dir: Path) -> str:
    parts = [run_dir.name]
    parent = run_dir.parent.name
    grandparent = run_dir.parent.parent.name if run_dir.parent.parent != run_dir.parent else ""
    if parent.startswith("provider="):
        if grandparent:
            parts.insert(0, grandparent)
        parts.insert(1 if grandparent else 0, parent)
    elif parent and parent not in {"logs", "data"} and ("=" in run_dir.name or "=" in parent):
        parts.insert(0, parent)
    return "__".join(parts)


def _format_run_ref(run_dir: Path, *, root_dir: Path | None) -> str:
    if root_dir is None:
        return run_dir.as_posix()
    return relpath_under(root_dir.resolve(), run_dir.resolve())


def _validate_dashboard_run_dirs(
    run_dirs: list[Path], *, root_dir: Path | None
) -> list[Path]:
    incompatible: list[str] = []
    compatible: list[Path] = []
    for run_dir in run_dirs:
        reason = inspect_run_artifacts(run_dir).dashboard_incompatibility()
        if reason is None:
            compatible.append(run_dir)
            continue
        incompatible.append(f"{_format_run_ref(run_dir, root_dir=root_dir)}: {reason}")
    if incompatible:
        detail_lines = "\n".join(f"- {line}" for line in incompatible[:20])
        extra = ""
        if len(incompatible) > 20:
            extra = f"\n- ... and {len(incompatible) - 20} more"
        raise DashboardRunIncompatibleError(
            "Dashboard export requires summary.json(.gz) at the run root. "
            "The selection included incompatible runs:\n"
            f"{detail_lines}{extra}"
        )
    return compatible


def _format_pct(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    return f"{value * 100:.1f}%"


def list_runs(logs_dir: Path) -> list[Path]:
    from .lake.index import discover_run_dirs

    discovered = [provider_run.run_dir for provider_run in discover_run_dirs(logs_dir)]
    run_dirs = sorted(
        {run_dir.resolve() for run_dir in discovered},
        key=lambda path: path.as_posix(),
    )
    return _validate_dashboard_run_dirs(run_dirs, root_dir=logs_dir)


def export_run(
    run_dir: Path,
    out_dir: Path,
    label: str | None,
    *,
    include_file_backed_details: bool = True,
) -> RunEntry:
    _validate_dashboard_run_dirs([run_dir], root_dir=None)
    artifacts = inspect_run_artifacts(run_dir)
    summary_path = artifacts.summary_path
    if summary_path is None:
        raise DashboardRunIncompatibleError(
            f"{run_dir}: missing summary.json(.gz) at the run root"
        )
    summary = load_json_mapping(summary_path)
    run_snapshot = load_run_snapshot(run_dir, include_summary_aggregates=False)
    run_config = run_snapshot.config
    run_status = run_snapshot.status

    payload = build_dashboard_payload_v2(
        summary,
        run_dir,
        run_config,
        run_status,
        include_file_backed_details=include_file_backed_details,
    )
    run_id_value = summary.get("run_id")
    fallback_run_id = _fallback_run_id_from_dir(run_dir)
    run_id = _normalize_dashboard_run_id(
        run_id_value,
        fallback=fallback_run_id,
        source=summary_path,
    )
    if (
        run_dir.parent.name.startswith("provider=")
        and isinstance(run_id_value, str)
        and run_id == run_dir.name
    ):
        run_id = _validate_run_id(fallback_run_id, source=run_dir)
    label_run_id = run_id_value if isinstance(run_id_value, str) and run_id_value else run_id
    aggregates = summary.get("aggregates")
    summary_aggregates = aggregates if isinstance(aggregates, dict) else None
    theorem_count = None
    if summary_aggregates is not None:
        theorem_total = summary_aggregates.get("theorem_count")
        if isinstance(theorem_total, int):
            theorem_count = theorem_total
    if theorem_count is None:
        theorem_count = run_snapshot.theorem_count
    extra_parts: list[str] = []
    if summary_aggregates is not None:
        wild_rate = _format_pct(summary_aggregates.get("wild_type_solve_rate"))
        if wild_rate:
            extra_parts.append(f"wild {wild_rate}")
        int_rate = _format_pct(summary_aggregates.get("intervention_solve_rate"))
        if int_rate:
            extra_parts.append(f"int {int_rate}")
    resolved_label = label or build_run_label(
        label_run_id,
        run_config,
        run_status,
        theorem_count=theorem_count,
        style="dashboard",
        extra_parts=extra_parts,
    )
    meta = build_run_meta(
        aggregates if isinstance(aggregates, dict) else None,
        run_config,
        run_status,
    )

    run_out_dir = out_dir / "data" / run_id
    run_out_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = run_out_dir / "dashboard_v2.json"
    dashboard_path.write_text(json.dumps(payload, indent=2) + "\n")

    return RunEntry(
        {
            "id": run_id,
            "label": resolved_label,
            "dashboard": f"data/{run_id}/dashboard_v2.json",
            "meta": meta,
        }
    )


def load_manifest(out_dir: Path) -> tuple[list[RunEntry], str | None]:
    manifest_path = out_dir / "data" / "manifest.json"
    if not manifest_path.exists():
        return [], None
    data = load_json_mapping(manifest_path)
    runs = data.get("runs")
    if runs is None:
        runs = []
    if not isinstance(runs, list):
        raise RuntimeError(f"Invalid manifest.json: runs is not a list in {manifest_path}")
    normalized: list[RunEntry] = []
    seen: set[str] = set()
    for idx, entry in enumerate(runs, start=1):
        if not isinstance(entry, dict):
            raise RuntimeError(
                f"Invalid manifest.json: run entry {idx} is not an object in {manifest_path}"
            )
        run_id = entry.get("id")
        label = entry.get("label")
        dashboard = entry.get("dashboard")
        if not isinstance(run_id, str) or not run_id:
            raise RuntimeError(
                f"Invalid manifest.json: run entry {idx} missing id in {manifest_path}"
            )
        if run_id in seen:
            raise RuntimeError(
                f"Invalid manifest.json: duplicate run id {run_id} in {manifest_path}"
            )
        if not isinstance(label, str) or not label:
            raise RuntimeError(
                f"Invalid manifest.json: run entry {idx} missing label in {manifest_path}"
            )
        if dashboard is not None and not isinstance(dashboard, str):
            raise RuntimeError(
                f"Invalid manifest.json: run entry {idx} has invalid dashboard in {manifest_path}"
            )
        meta = entry.get("meta")
        if meta is not None and not isinstance(meta, dict):
            raise RuntimeError(
                f"Invalid manifest.json: run entry {idx} has invalid meta in {manifest_path}"
            )
        normalized.append(
            RunEntry({"id": run_id, "label": label, "dashboard": dashboard, "meta": meta})
        )
        seen.add(run_id)
    default_run = data.get("default_run")
    if default_run is not None and not isinstance(default_run, str):
        raise RuntimeError(
            f"Invalid manifest.json: default_run is not a string in {manifest_path}"
        )
    return normalized, default_run


def write_manifest(out_dir: Path, runs: list[RunEntry], default_run: str | None) -> None:
    manifest = {"runs": runs, "default_run": default_run}
    manifest_path = out_dir / "data" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def upsert_run(
    runs: list[RunEntry],
    index_by_id: dict[str, int],
    entry: RunEntry,
    *,
    preserve_label: bool,
) -> None:
    idx = index_by_id.get(entry["id"])
    if idx is None:
        index_by_id[entry["id"]] = len(runs)
        runs.append(entry)
        return
    merged = dict(runs[idx])
    merged.update(entry)
    if preserve_label:
        label = runs[idx].get("label")
        if isinstance(label, str) and label:
            merged["label"] = label
    runs[idx] = RunEntry(merged)


def resolve_run_dir(logs_dir: Path, run_id: str | None) -> Path:
    if run_id is not None:
        resolved = _validate_run_id(run_id, source=logs_dir)
        return logs_dir / resolved
    latest_path = logs_dir / "latest_run.json"
    if not latest_path.exists():
        raise RuntimeError("No run id provided and latest_run.json is missing")
    latest = load_json_mapping(latest_path)
    latest_run_id = _validate_run_id(latest.get("run_id"), source=latest_path)
    return logs_dir / latest_run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Wonton-Soup dashboard data")
    parser.add_argument(
        "--logs-dir",
        default="logs",
        help="Path to logs directory (default: ./logs or $SPECTER_LOG_ROOT)",
    )
    parser.add_argument(
        "--out-dir",
        default="dashboard/www",
        help="Output directory (default: dashboard/www)",
    )
    parser.add_argument("--run-id", default=None, help="Run ID to export")
    parser.add_argument("--label", default=None, help="Label for the run")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export all discovered dashboard-compatible runs; fail on incompatible run shapes",
    )
    parser.add_argument(
        "--refresh-labels",
        action="store_true",
        help="Recompute default labels for existing runs (ignored when --label is set).",
    )

    args = parser.parse_args()
    if args.all and args.run_id:
        parser.error("--all cannot be combined with --run-id")
    if args.all and args.label:
        parser.error("--all cannot be combined with --label")

    logs_dir = resolve_logs_dir(args.logs_dir)
    if not logs_dir.exists():
        raise FileNotFoundError(f"Logs directory not found: {logs_dir}")

    out_dir = Path(args.out_dir).resolve()

    runs, default_run = load_manifest(out_dir)
    index_by_id = {entry["id"]: idx for idx, entry in enumerate(runs)}
    if default_run is not None and default_run not in index_by_id:
        raise RuntimeError(
            f"Invalid manifest.json: default_run {default_run} not present in runs"
        )

    if args.all:
        for run_dir in list_runs(logs_dir):
            exported = export_run(run_dir, out_dir, None)
            upsert_run(
                runs,
                index_by_id,
                exported,
                preserve_label=not args.refresh_labels,
            )
    else:
        run_dir = resolve_run_dir(logs_dir, args.run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir}")
        run_entry = export_run(run_dir, out_dir, args.label)
        upsert_run(
            runs,
            index_by_id,
            run_entry,
            preserve_label=args.label is None and not args.refresh_labels,
        )
        default_run = run_entry["id"]

    if default_run is None and runs:
        default_run = runs[0]["id"]
    write_manifest(out_dir, runs, default_run)
    print(f"Exported {len(runs)} run(s) to {out_dir}")


if __name__ == "__main__":
    main()
