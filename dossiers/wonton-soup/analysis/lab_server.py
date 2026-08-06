from __future__ import annotations

import argparse
import gzip
import json
import os
import signal
import subprocess
import sys
import threading
import uuid
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime_paths import DOSSIER_NAME, resolve_artifacts_root, resolve_logs_root


DOSSIER_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "lab_static"
PRESETS_DIR = DOSSIER_ROOT / "analysis" / "lake" / "presets"
NOTEBOOK_PATH = DOSSIER_ROOT / "analysis" / "notebooks" / "deep_analysis.html"
TEXT_SUFFIXES = {".log", ".md", ".sql", ".txt", ".html"}
RECENT_LOG_LINES = 160
GRAPH_RENDER_LIMIT = 120


@dataclass(frozen=True)
class ProviderRun:
    run_dir: Path
    provider: str | None


@dataclass(frozen=True)
class RunArtifacts:
    has_summary: bool
    basin_seeds: int | None
    has_basin_analysis: bool

    @property
    def is_basin_only(self) -> bool:
        return not self.has_summary and (
            self.basin_seeds is not None or self.has_basin_analysis
        )

    def dashboard_incompatibility(self) -> str | None:
        if self.has_summary:
            return None
        if not self.is_basin_only:
            return "missing summary.json(.gz) at the run root"
        details: list[str] = []
        if self.basin_seeds is not None:
            details.append(f"basin_seeds={self.basin_seeds}")
        if self.has_basin_analysis:
            details.append("basin_analysis present")
        suffix = f" ({', '.join(details)})" if details else ""
        return "basin-only run with no summary.json(.gz) at the run root" + suffix


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json_dict(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _read_json_auto(path: Path) -> Any:
    if path.suffix == ".gz" or path.name.endswith(".json.gz") or path.name.endswith(".jsonl.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_logs_dir_arg(logs_dir: str | None) -> Path:
    if logs_dir is None or logs_dir == "logs":
        return resolve_logs_root().resolve()
    return Path(logs_dir).resolve()


def _resolve_fonts_dir(viz_path: Path, fonts_dir: str | None) -> Path:
    if fonts_dir:
        return Path(fonts_dir).resolve()
    candidates = [viz_path, *viz_path.parents]
    for parent in candidates:
        candidate = (parent / "site" / "fonts").resolve()
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Fonts directory not found. Pass --fonts-dir or add site/fonts near {viz_path}"
    )


def _runtime_lab_root() -> Path:
    raw = os.environ.get("SPECTER_RUNTIME_ROOT")
    if raw is not None:
        trimmed = raw.strip()
        if not trimmed:
            raise ValueError("SPECTER_RUNTIME_ROOT is set but empty.")
        return (Path(os.path.expanduser(trimmed)).resolve() / DOSSIER_NAME / "lab").resolve()
    return (DOSSIER_ROOT / "tmp" / "lab").resolve()


def _ensure_under(root: Path, target: Path) -> Path:
    resolved_root = root.resolve()
    resolved = target.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"path escapes root: {target}") from exc
    return resolved


def _relative_to_logs(logs_dir: Path, target: Path | str | None) -> str | None:
    if target is None:
        return None
    try:
        path = Path(target).resolve()
    except OSError:
        return str(target)
    try:
        return path.relative_to(logs_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def _inspect_run_artifacts(run_dir: Path) -> RunArtifacts:
    has_summary = (run_dir / "summary.json.gz").exists() or (run_dir / "summary.json").exists()
    if has_summary:
        return RunArtifacts(has_summary=True, basin_seeds=None, has_basin_analysis=False)

    basin_seeds = None
    run_config = _read_json_dict(run_dir / "run_config.json")
    if isinstance(run_config, dict):
        raw = run_config.get("basin_seeds")
        if isinstance(raw, int) and raw > 0:
            basin_seeds = raw

    has_basin_analysis = False
    for child in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        if child.name.startswith(".") or child.name.startswith("provider="):
            continue
        if (child / "basin_analysis.json").exists() or (child / "basin_analysis.json.gz").exists():
            has_basin_analysis = True
            break

    return RunArtifacts(
        has_summary=False,
        basin_seeds=basin_seeds,
        has_basin_analysis=has_basin_analysis,
    )


def _iter_provider_runs(run_dir: Path) -> list[ProviderRun]:
    run_dir = run_dir.resolve()
    provider_dirs = sorted(p for p in run_dir.glob("provider=*") if p.is_dir())
    result: list[ProviderRun] = []
    for provider_dir in provider_dirs:
        if not (provider_dir / "run_config.json").exists():
            continue
        provider = provider_dir.name.split("=", 1)[1] if "=" in provider_dir.name else None
        result.append(ProviderRun(run_dir=provider_dir, provider=provider))
    if result:
        return result
    if (run_dir / "run_config.json").exists():
        return [ProviderRun(run_dir=run_dir, provider=None)]
    raise FileNotFoundError(f"No run_config.json found under: {run_dir}")


def _discover_nested_provider_runs(root: Path, *, max_depth: int = 6) -> list[ProviderRun]:
    runs: list[ProviderRun] = []
    for candidate in sorted(p.parent for p in root.rglob("run_config.json")):
        try:
            rel_parts = candidate.resolve().relative_to(root.resolve()).parts
        except ValueError:
            continue
        if not rel_parts or len(rel_parts) > max_depth:
            continue
        if any(part.startswith(".") for part in rel_parts):
            continue
        try:
            runs.extend(_iter_provider_runs(candidate))
        except FileNotFoundError:
            continue
    return runs


def _discover_run_dirs(logs_dir: Path) -> list[ProviderRun]:
    runs: list[ProviderRun] = []
    if not logs_dir.exists():
        return runs
    for child in sorted(p for p in logs_dir.iterdir() if p.is_dir()):
        try:
            runs.extend(_iter_provider_runs(child))
        except FileNotFoundError:
            runs.extend(_discover_nested_provider_runs(child))
    seen: set[Path] = set()
    unique: list[ProviderRun] = []
    for run in runs:
        if run.run_dir in seen:
            continue
        seen.add(run.run_dir)
        unique.append(run)
    return unique


def _coerce_str(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _top_level_files(run_dir: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for child in sorted(run_dir.iterdir()):
        if not child.is_file():
            continue
        kind = "json"
        if child.name.endswith(".jsonl") or child.name.endswith(".jsonl.gz"):
            kind = "jsonl"
        elif child.suffix.lower() in TEXT_SUFFIXES:
            kind = "text"
        elif child.suffix.lower() == ".gz" and child.name.endswith(".json.gz"):
            kind = "json"
        else:
            continue
        try:
            stat = child.stat()
        except OSError:
            continue
        files.append(
            {
                "name": child.name,
                "kind": kind,
                "bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            }
        )
    return files


def _load_summary(run_dir: Path) -> dict[str, Any] | None:
    for candidate in (run_dir / "summary.json.gz", run_dir / "summary.json"):
        if not candidate.exists():
            continue
        try:
            payload = _read_json_auto(candidate)
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None
    return None


def _load_run_config(run_dir: Path) -> dict[str, Any] | None:
    return _read_json_dict(run_dir / "run_config.json")


def _load_run_status(run_dir: Path) -> dict[str, Any] | None:
    return _read_json_dict(run_dir / "run_status.json")


def _discover_theorem_names(run_dir: Path, summary: dict[str, Any] | None) -> list[str]:
    if isinstance(summary, dict):
        theorems = summary.get("theorems")
        if isinstance(theorems, list):
            names = [entry.get("name") for entry in theorems if isinstance(entry, dict)]
            return sorted(name for name in names if isinstance(name, str))
    names: list[str] = []
    for child in sorted(run_dir.iterdir()):
        if not child.is_dir() or child.name.startswith(".") or child.name.startswith("provider="):
            continue
        names.append(child.name)
    return names


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _ged_from_intervention(entry: dict[str, Any]) -> float | None:
    direct = entry.get("ged")
    if isinstance(direct, (int, float)):
        return float(direct)
    for key in ("ged_search_graph", "ged_proof_graph", "ged_trace_graph"):
        raw = entry.get(key)
        if isinstance(raw, dict):
            nested = raw.get("value")
            if isinstance(nested, (int, float)):
                return float(nested)
    return None


def _intervention_behavior_counts(theorems: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "total": 0,
        "controls": 0,
        "rescued": 0,
        "preserved": 0,
        "degraded": 0,
        "inert": 0,
        "solved": 0,
        "failed": 0,
    }
    for theorem in theorems:
        if not isinstance(theorem, dict):
            continue
        for intervention in theorem.get("interventions", []):
            if not isinstance(intervention, dict):
                continue
            counts["total"] += 1
            if intervention.get("is_control") is True:
                counts["controls"] += 1
            solved = intervention.get("solved") is True
            baseline_solved = intervention.get("baseline_solved") is True
            counts["solved" if solved else "failed"] += 1
            if baseline_solved and solved:
                counts["preserved"] += 1
            elif baseline_solved and not solved:
                counts["degraded"] += 1
            elif not baseline_solved and solved:
                counts["rescued"] += 1
            else:
                counts["inert"] += 1
    total = counts["total"]
    rates = {
        key: round((value / total), 4) if total else 0.0
        for key, value in counts.items()
        if key != "total"
    }
    return {"counts": counts, "rates": rates}


def _theorem_rows(theorems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for theorem in theorems:
        if not isinstance(theorem, dict):
            continue
        name = theorem.get("name")
        if not isinstance(name, str):
            continue
        wild = theorem.get("wild_type")
        interventions = theorem.get("interventions")
        if not isinstance(wild, dict):
            wild = {}
        if not isinstance(interventions, list):
            interventions = []
        geds = [
            value
            for value in (_ged_from_intervention(entry) for entry in interventions if isinstance(entry, dict))
            if value is not None
        ]
        rescued = 0
        degraded = 0
        for entry in interventions:
            if not isinstance(entry, dict):
                continue
            solved = entry.get("solved") is True
            baseline_solved = entry.get("baseline_solved") is True
            if solved and not baseline_solved:
                rescued += 1
            if baseline_solved and not solved:
                degraded += 1
        rows.append(
            {
                "name": name,
                "wild_solved": wild.get("solved") is True,
                "iterations": wild.get("iterations"),
                "intervention_count": len(interventions),
                "rescued_count": rescued,
                "degraded_count": degraded,
                "mean_ged": _mean(geds),
            }
        )
    rows.sort(key=lambda row: row["name"])
    return rows


def _summarize_metrics(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    trajectory = data.get("trajectory") if isinstance(data.get("trajectory"), dict) else {}
    detour = data.get("detour") if isinstance(data.get("detour"), dict) else {}
    proof_term = data.get("proof_term") if isinstance(data.get("proof_term"), dict) else {}
    summary: dict[str, Any] = {}
    for key, source_key in (
        ("total_iterations", ("trajectory", "total_iterations")),
        ("backtrack_count", ("trajectory", "backtrack_count")),
        ("max_depth_reached", ("trajectory", "max_depth_reached")),
        ("unique_goals_visited", ("trajectory", "unique_goals_visited")),
        ("tactic_diversity", ("trajectory", "tactic_diversity")),
        ("total_attempts", ("detour", "total_attempts")),
        ("failure_ratio", ("detour", "failure_ratio")),
        ("proof_node_count", ("proof_term", "node_count")),
        ("proof_depth", ("proof_term", "depth")),
        ("unique_consts", ("proof_term", "unique_consts")),
    ):
        bucket, field_name = source_key
        source = trajectory if bucket == "trajectory" else detour if bucket == "detour" else proof_term
        value = source.get(field_name)
        if isinstance(value, (int, float)):
            summary[key] = value
    return summary or None


def _summarize_graph(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return None
    depths = [node.get("depth") for node in nodes if isinstance(node, dict) and isinstance(node.get("depth"), int)]
    tactic_counts: dict[str, int] = {}
    terminal_count = 0
    for node in nodes:
        if isinstance(node, dict) and node.get("is_terminal") is True:
            terminal_count += 1
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        tactic = edge.get("tactic_norm") or edge.get("tactic")
        if isinstance(tactic, str) and tactic:
            tactic_counts[tactic] = tactic_counts.get(tactic, 0) + 1
    top_tactics = [
        {"tactic": tactic, "count": count}
        for tactic, count in sorted(tactic_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "terminal_count": terminal_count,
        "max_depth": max(depths) if depths else None,
        "renderable": len(nodes) <= GRAPH_RENDER_LIMIT,
        "top_tactics": top_tactics,
    }


def _summarize_tree(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    nodes = data.get("nodes")
    if isinstance(nodes, dict):
        entries = list(nodes.values())
    elif isinstance(nodes, list):
        entries = nodes
    else:
        return None
    depths: list[int] = []
    solved = 0
    visits: list[int] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        depth = entry.get("depth")
        if isinstance(depth, int):
            depths.append(depth)
        if entry.get("solved") is True:
            solved += 1
        visits_value = entry.get("visits")
        if isinstance(visits_value, int):
            visits.append(visits_value)
    return {
        "node_count": len(entries),
        "solved_nodes": solved,
        "max_depth": max(depths) if depths else None,
        "max_visits": max(visits) if visits else None,
    }


def _summarize_history(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    iterations = data.get("iterations")
    if not isinstance(iterations, list):
        return None
    total_attempts = 0
    successful_attempts = 0
    tactic_counts: dict[str, int] = {}
    for record in iterations:
        if not isinstance(record, dict):
            continue
        attempts = record.get("attempts")
        if not isinstance(attempts, list):
            continue
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            total_attempts += 1
            tactic = attempt.get("tactic")
            if isinstance(tactic, str) and tactic:
                tactic_counts[tactic] = tactic_counts.get(tactic, 0) + 1
            if attempt.get("outcome") == "success":
                successful_attempts += 1
    solution_path = data.get("solution_path")
    solution_steps = len(solution_path) if isinstance(solution_path, list) else None
    top_tactics = [
        {"tactic": tactic, "count": count}
        for tactic, count in sorted(tactic_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]
    return {
        "iteration_count": len(iterations),
        "total_attempts": total_attempts,
        "successful_attempts": successful_attempts,
        "solution_steps": solution_steps,
        "top_tactics": top_tactics,
    }


def _summarize_comparison(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    proof_term_diff = data.get("proof_term_diff") if isinstance(data.get("proof_term_diff"), dict) else {}
    return {
        "ged": data.get("ged"),
        "hash_mismatch": data.get("hash_mismatch"),
        "axiom_delta": data.get("axiom_delta") if isinstance(data.get("axiom_delta"), list) else [],
        "axiom_removed": data.get("axiom_removed") if isinstance(data.get("axiom_removed"), list) else [],
        "divergence_depth": proof_term_diff.get("divergence_depth"),
        "divergence_path": proof_term_diff.get("divergence_path"),
        "consts_only_in_other": (
            proof_term_diff.get("consts_only_in_other")
            if isinstance(proof_term_diff.get("consts_only_in_other"), list)
            else []
        ),
    }


def _variant_index(theorem_dir: Path) -> dict[str, Any]:
    variant_files: dict[str, dict[str, str]] = {}
    extra_files: dict[str, str | None] = {
        "ged_matrix": None,
        "attractor_clusters": None,
        "basin_analysis": None,
    }
    kinds = [
        "history",
        "mcts_tree",
        "mcts_trace",
        "graph",
        "metrics",
        "comparison",
        "assembly",
        "proof_term",
    ]
    for file in theorem_dir.iterdir():
        if not file.is_file():
            continue
        name = file.name
        if name in {"ged_matrix.json", "ged_matrix.json.gz"}:
            extra_files["ged_matrix"] = name
            continue
        if name in {"attractor_clusters.json", "attractor_clusters.json.gz"}:
            extra_files["attractor_clusters"] = name
            continue
        if name in {"basin_analysis.json", "basin_analysis.json.gz"}:
            extra_files["basin_analysis"] = name
            continue
        for kind in kinds:
            if kind == "mcts_trace":
                suffixes = (f"_{kind}.jsonl", f"_{kind}.jsonl.gz")
            else:
                suffixes = (f"_{kind}.json", f"_{kind}.json.gz")
            matched_suffix = next((suffix for suffix in suffixes if name.endswith(suffix)), None)
            if matched_suffix is None:
                continue
            variant = name[: -len(matched_suffix)]
            variant_files.setdefault(variant, {})[kind] = name
            break

    def variant_sort(name: str) -> tuple[int, str]:
        return (0, name) if name == "wild_type" else (1, name)

    variants = sorted(variant_files, key=variant_sort)
    return {"variants": variants, "variant_files": variant_files, "extra_files": extra_files}


def _load_variant_summaries(theorem_dir: Path, index: dict[str, Any]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    variant_files = index.get("variant_files")
    if not isinstance(variant_files, dict):
        return summaries
    for variant, files in variant_files.items():
        if not isinstance(files, dict):
            continue
        summary: dict[str, Any] = {}
        metrics_file = files.get("metrics")
        if isinstance(metrics_file, str):
            try:
                metrics_payload = _read_json_auto(theorem_dir / metrics_file)
            except Exception:
                metrics_payload = None
            metrics_summary = _summarize_metrics(metrics_payload)
            if metrics_summary:
                summary["metrics"] = metrics_summary
        graph_file = files.get("graph")
        if isinstance(graph_file, str):
            try:
                graph_payload = _read_json_auto(theorem_dir / graph_file)
            except Exception:
                graph_payload = None
            graph_summary = _summarize_graph(graph_payload)
            if graph_summary:
                summary["graph"] = graph_summary
        tree_file = files.get("mcts_tree")
        if isinstance(tree_file, str):
            try:
                tree_payload = _read_json_auto(theorem_dir / tree_file)
            except Exception:
                tree_payload = None
            tree_summary = _summarize_tree(tree_payload)
            if tree_summary:
                summary["mcts_tree"] = tree_summary
        history_file = files.get("history")
        if isinstance(history_file, str):
            try:
                history_payload = _read_json_auto(theorem_dir / history_file)
            except Exception:
                history_payload = None
            history_summary = _summarize_history(history_payload)
            if history_summary:
                summary["history"] = history_summary
        comparison_file = files.get("comparison")
        if isinstance(comparison_file, str):
            try:
                comparison_payload = _read_json_auto(theorem_dir / comparison_file)
            except Exception:
                comparison_payload = None
            comparison_summary = _summarize_comparison(comparison_payload)
            if comparison_summary:
                summary["comparison"] = comparison_summary
        summaries[variant] = summary
    return summaries


def _compact_theorem_summary(entry: dict[str, Any]) -> dict[str, Any]:
    wild = entry.get("wild_type") if isinstance(entry.get("wild_type"), dict) else {}
    interventions = entry.get("interventions")
    if not isinstance(interventions, list):
        interventions = []
    compact_interventions: list[dict[str, Any]] = []
    for item in interventions:
        if not isinstance(item, dict):
            continue
        compact_interventions.append(
            {
                "name": item.get("name"),
                "solved": item.get("solved"),
                "baseline_solved": item.get("baseline_solved"),
                "is_control": item.get("is_control"),
                "blocked": item.get("blocked"),
                "ged": _ged_from_intervention(item),
                "axiom_delta": item.get("axiom_delta") if isinstance(item.get("axiom_delta"), list) else [],
            }
        )
    wild_metrics = wild.get("metrics") if isinstance(wild.get("metrics"), dict) else {}
    return {
        "name": entry.get("name"),
        "wild_type": {
            "solved": wild.get("solved"),
            "iterations": wild.get("iterations"),
            "metrics": _summarize_metrics(wild_metrics),
        },
        "interventions": compact_interventions,
    }


@dataclass
class JobRecord:
    id: str
    kind: str
    label: str
    argv: list[str]
    cwd: str
    created_at: str
    status: str = "queued"
    started_at: str | None = None
    ended_at: str | None = None
    exit_code: int | None = None
    pid: int | None = None
    run_dir: str | None = None
    output_path: str | None = None
    log_path: str | None = None
    recent_lines: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "argv": self.argv,
            "cwd": self.cwd,
            "created_at": self.created_at,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "exit_code": self.exit_code,
            "pid": self.pid,
            "run_dir": self.run_dir,
            "output_path": self.output_path,
            "log_path": self.log_path,
            "recent_lines": self.recent_lines,
            "notes": self.notes,
            "raw_metadata": self.raw_metadata,
        }


class LabJobManager:
    def __init__(self, *, state_dir: Path, logs_dir: Path):
        self.state_dir = state_dir
        self.logs_dir = logs_dir.resolve()
        self.registry_path = self.state_dir / "jobs.json"
        self.jobs_dir = self.state_dir / "jobs"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._load()

    def _load(self) -> None:
        data = _read_json_dict(self.registry_path)
        jobs_raw = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(jobs_raw, list):
            return
        for item in jobs_raw:
            if not isinstance(item, dict):
                continue
            try:
                record = JobRecord(
                    id=str(item["id"]),
                    kind=str(item["kind"]),
                    label=str(item["label"]),
                    argv=[str(arg) for arg in item.get("argv", [])],
                    cwd=str(item["cwd"]),
                    created_at=str(item["created_at"]),
                    status=str(item.get("status", "orphaned")),
                    started_at=_coerce_str(item.get("started_at")),
                    ended_at=_coerce_str(item.get("ended_at")),
                    exit_code=_coerce_int(item.get("exit_code")),
                    pid=_coerce_int(item.get("pid")),
                    run_dir=_coerce_str(item.get("run_dir")),
                    output_path=_coerce_str(item.get("output_path")),
                    log_path=_coerce_str(item.get("log_path")),
                    recent_lines=[str(line) for line in item.get("recent_lines", [])][-RECENT_LOG_LINES:],
                    notes=[str(line) for line in item.get("notes", [])],
                    raw_metadata=item.get("raw_metadata", {}) if isinstance(item.get("raw_metadata"), dict) else {},
                )
            except KeyError:
                continue
            if record.status in {"queued", "running", "stopping"}:
                record.status = "orphaned"
                record.notes.append("server restarted while job state was non-terminal")
            self._jobs[record.id] = record

    def _persist(self) -> None:
        payload = {
            "updated_at": _utc_now(),
            "jobs": [job.to_dict() for job in self.list_records()],
        }
        self.registry_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    def list_records(self) -> list[JobRecord]:
        return sorted(
            self._jobs.values(),
            key=lambda job: (job.created_at, job.id),
            reverse=True,
        )

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [job.to_dict() for job in self.list_records()]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return None if job is None else job.to_dict()

    def launch(
        self,
        *,
        kind: str,
        label: str,
        argv: list[str],
        cwd: Path,
        output_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        job_dir = self.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        log_path = job_dir / "stdout.log"
        with self._lock:
            record = JobRecord(
                id=job_id,
                kind=kind,
                label=label,
                argv=argv,
                cwd=str(cwd),
                created_at=_utc_now(),
                status="running",
                started_at=_utc_now(),
                output_path=output_path,
                log_path=str(log_path),
                raw_metadata=metadata or {},
            )
            self._jobs[job_id] = record
            self._persist()

        process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        with self._lock:
            record.pid = process.pid
            self._processes[job_id] = process
            self._persist()

        worker = threading.Thread(
            target=self._pump_process,
            args=(job_id, process, log_path),
            daemon=True,
            name=f"wonton-lab-job-{job_id}",
        )
        worker.start()
        return record.to_dict()

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            process = self._processes.get(job_id)
            job = self._jobs.get(job_id)
            if process is None or job is None:
                return None
            if job.status in {"succeeded", "failed", "cancelled"}:
                return job.to_dict()
            job.status = "stopping"
            job.notes.append("termination requested")
            self._persist()
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        return self.get_job(job_id)

    def read_log(self, job_id: str) -> str | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.log_path is None:
                return None
            log_path = Path(job.log_path)
        if not log_path.exists():
            return ""
        try:
            return log_path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _pump_process(self, job_id: str, process: subprocess.Popen[str], log_path: Path) -> None:
        assert process.stdout is not None
        with log_path.open("w", encoding="utf-8") as sink:
            for line in process.stdout:
                sink.write(line)
                sink.flush()
                self._consume_line(job_id, line.rstrip("\n"))
        exit_code = process.wait()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                if job.status == "stopping":
                    job.status = "cancelled"
                else:
                    job.status = "succeeded" if exit_code == 0 else "failed"
                job.exit_code = exit_code
                job.ended_at = _utc_now()
            self._processes.pop(job_id, None)
            self._persist()

    def _consume_line(self, job_id: str, line: str) -> None:
        payload: dict[str, Any] | None = None
        if line.startswith("{") and line.endswith("}"):
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, dict):
                payload = decoded
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if line:
                job.recent_lines.append(line)
                job.recent_lines = job.recent_lines[-RECENT_LOG_LINES:]
            if payload is not None:
                event = payload.get("event")
                if isinstance(event, str):
                    job.raw_metadata["last_agent_event"] = payload
                rel_run = _relative_to_logs(self.logs_dir, payload.get("log_dir"))
                if isinstance(rel_run, str):
                    job.run_dir = rel_run
                summary_path = payload.get("summary_path")
                if isinstance(summary_path, str):
                    job.raw_metadata["summary_path"] = summary_path
            self._persist()


@dataclass(frozen=True)
class LabContext:
    logs_dir: Path
    artifacts_dir: Path
    state_dir: Path
    static_dir: Path
    fonts_dir: Path
    lake_db_path: Path
    lake_exports_dir: Path
    lake_jobs_dir: Path
    notebook_html: Path
    presets_dir: Path


class LabApp:
    def __init__(self, context: LabContext):
        self.context = context
        self.jobs = LabJobManager(state_dir=context.state_dir, logs_dir=context.logs_dir)

    def bootstrap(self) -> dict[str, Any]:
        return {
            "runtime": self.analysis_state(),
            "launchers": self.launcher_specs(),
        }

    def launcher_specs(self) -> list[dict[str, Any]]:
        preset_options = [
            {"label": preset["name"], "value": preset["path"]}
            for preset in self.list_presets()
        ]
        return [
            {
                "id": "lean_run",
                "label": "Lean Run",
                "description": "Launch a standard Lean corpus run with interventions and tracing.",
                "fields": [
                    {"id": "mode", "label": "Mode", "type": "text", "default": "dev"},
                    {"id": "corpus", "label": "Corpus", "type": "text", "default": "easy"},
                    {"id": "provider", "label": "Provider", "type": "text", "default": ""},
                    {"id": "budget", "label": "Budget", "type": "text", "default": ""},
                    {"id": "limit", "label": "Limit", "type": "number", "default": ""},
                    {"id": "sample", "label": "Sample", "type": "number", "default": ""},
                    {"id": "seed", "label": "Seed", "type": "number", "default": ""},
                    {"id": "workers", "label": "Workers", "type": "number", "default": ""},
                    {"id": "theorem", "label": "Theorem", "type": "text", "default": ""},
                    {"id": "run_id", "label": "Run ID", "type": "text", "default": ""},
                    {"id": "with_interventions", "label": "Interventions", "type": "boolean", "default": True},
                    {"id": "trace_mcts", "label": "Trace MCTS", "type": "boolean", "default": True},
                    {"id": "analysis", "label": "Run post analysis", "type": "boolean", "default": False},
                ],
            },
            {
                "id": "lean_basin",
                "label": "Lean Basin",
                "description": "Launch basin seeds for a Lean run configuration.",
                "fields": [
                    {"id": "seeds", "label": "Seeds", "type": "number", "default": 8},
                    {"id": "mode", "label": "Mode", "type": "text", "default": "dev"},
                    {"id": "corpus", "label": "Corpus", "type": "text", "default": "easy"},
                    {"id": "provider", "label": "Provider", "type": "text", "default": ""},
                    {"id": "budget", "label": "Budget", "type": "text", "default": ""},
                    {"id": "limit", "label": "Limit", "type": "number", "default": ""},
                    {"id": "sample", "label": "Sample", "type": "number", "default": ""},
                    {"id": "seed", "label": "Seed", "type": "number", "default": ""},
                    {"id": "workers", "label": "Workers", "type": "number", "default": ""},
                    {"id": "blind", "label": "Blind baseline", "type": "boolean", "default": False},
                    {"id": "trace_mcts", "label": "Trace MCTS", "type": "boolean", "default": True},
                ],
            },
            {
                "id": "causal_contrast",
                "label": "Causal Contrast",
                "description": "Run matched centralized and distributed MCTS proof-search conditions.",
                "fields": [
                    {"id": "providers", "label": "Providers", "type": "text", "default": "heuristic"},
                    {"id": "corpus", "label": "Corpus", "type": "text", "default": "easy"},
                    {"id": "budget", "label": "Budget", "type": "text", "default": "quick"},
                    {"id": "limit", "label": "Limit", "type": "number", "default": ""},
                    {"id": "sample", "label": "Sample", "type": "number", "default": ""},
                    {"id": "seed", "label": "Seed", "type": "number", "default": 20260602},
                    {"id": "workers", "label": "Workers", "type": "number", "default": 1},
                    {"id": "run_id", "label": "Run ID", "type": "text", "default": "causal-contrast"},
                    {"id": "mcts_agents", "label": "Distributed agents", "type": "number", "default": 4},
                    {
                        "id": "mcts_expansion_policy",
                        "label": "Expansion policy",
                        "type": "text",
                        "default": "all-successes",
                    },
                    {"id": "mcts_inflight", "label": "Distributed inflight", "type": "number", "default": 16},
                    {"id": "mcts_virtual_loss", "label": "Virtual loss", "type": "number", "default": 1},
                    {"id": "mcts_block_fraction", "label": "Block fraction", "type": "number", "default": ""},
                    {"id": "mcts_block_duration", "label": "Block duration", "type": "number", "default": ""},
                    {"id": "mcts_block_seed", "label": "Block seed", "type": "number", "default": ""},
                    {"id": "mcts_block_immovable_fraction", "label": "Immovable fraction", "type": "number", "default": ""},
                    {"id": "mcts_unfreeze_after", "label": "Unfreeze after", "type": "number", "default": ""},
                    {"id": "mcts_unfreeze_prob", "label": "Unfreeze probability", "type": "number", "default": ""},
                    {"id": "mcts_reroute_max", "label": "Reroute max", "type": "number", "default": ""},
                    {"id": "mcts_delay_prob", "label": "Delay probability", "type": "number", "default": ""},
                    {"id": "mcts_delay_duration", "label": "Delay duration", "type": "number", "default": ""},
                    {"id": "mcts_delay_seed", "label": "Delay seed", "type": "number", "default": ""},
                    {"id": "with_interventions", "label": "Interventions", "type": "boolean", "default": True},
                    {"id": "trace_mcts", "label": "Trace MCTS", "type": "boolean", "default": True},
                    {"id": "analysis", "label": "Run post analysis", "type": "boolean", "default": False},
                    {"id": "no_sync", "label": "No remote sync", "type": "boolean", "default": True},
                ],
            },
            {
                "id": "postprocess",
                "label": "Postprocess",
                "description": "Run heavy metrics over a selected run or the whole logs root.",
                "fields": [
                    {"id": "run_dir", "label": "Run", "type": "text", "default": ""},
                    {"id": "limit", "label": "Limit", "type": "number", "default": ""},
                    {"id": "dry_run", "label": "Dry run", "type": "boolean", "default": False},
                ],
            },
            {
                "id": "lake_reconcile",
                "label": "Lake Reconcile",
                "description": "Refresh the lake database from the logs root.",
                "fields": [
                    {"id": "prune", "label": "Prune stale runs", "type": "boolean", "default": False},
                ],
            },
            {
                "id": "lake_job_preset",
                "label": "Lake Preset",
                "description": "Materialize a pinned lake preset into an output directory.",
                "fields": [
                    {
                        "id": "config",
                        "label": "Preset",
                        "type": "select",
                        "default": preset_options[0]["value"] if preset_options else "",
                        "options": preset_options,
                    }
                ],
            },
            {
                "id": "analysis_export",
                "label": "Notebook Export",
                "description": "Export the deep analysis notebook to HTML for in-app viewing.",
                "fields": [
                    {"id": "output", "label": "Output", "type": "text", "default": "analysis/notebooks/deep_analysis.html"},
                ],
            },
        ]

    def analysis_state(self) -> dict[str, Any]:
        lake_db_exists = self.context.lake_db_path.exists()
        lake_runs = None
        if lake_db_exists:
            try:
                import duckdb

                with duckdb.connect(str(self.context.lake_db_path)) as conn:
                    row = conn.execute("SELECT count(*) FROM runs").fetchone()
                if row and isinstance(row[0], int):
                    lake_runs = row[0]
            except Exception:
                lake_runs = None
        notebook_info = None
        if self.context.notebook_html.exists():
            stat = self.context.notebook_html.stat()
            notebook_info = {
                "path": str(self.context.notebook_html),
                "bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            }
        outputs = []
        if self.context.lake_jobs_dir.exists():
            for child in sorted(
                (p for p in self.context.lake_jobs_dir.iterdir() if p.is_dir()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )[:20]:
                try:
                    stat = child.stat()
                except OSError:
                    continue
                outputs.append(
                    {
                        "name": child.name,
                        "path": str(child),
                        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    }
                )
        return {
            "logs_dir": str(self.context.logs_dir),
            "artifacts_dir": str(self.context.artifacts_dir),
            "state_dir": str(self.context.state_dir),
            "lake": {
                "db_path": str(self.context.lake_db_path),
                "db_exists": lake_db_exists,
                "runs_indexed": lake_runs,
                "exports_dir": str(self.context.lake_exports_dir),
                "jobs_dir": str(self.context.lake_jobs_dir),
                "recent_job_outputs": outputs,
            },
            "notebook": notebook_info,
            "presets": self.list_presets(),
        }

    def list_presets(self) -> list[dict[str, Any]]:
        from analysis.lake.job import load_job_config

        presets: list[dict[str, Any]] = []
        if not self.context.presets_dir.exists():
            return presets
        for path in sorted(self.context.presets_dir.glob("*.json")):
            try:
                config = load_job_config(path)
            except Exception as exc:
                presets.append(
                    {
                        "name": path.stem,
                        "path": str(path),
                        "valid": False,
                        "error": str(exc),
                    }
                )
                continue
            if isinstance(config, dict):
                datasets = config.get("datasets")
                if not isinstance(datasets, list):
                    datasets = []
                presets.append(
                    {
                        "name": config.get("name") or path.stem,
                        "path": str(path),
                        "valid": True,
                        "selection": config.get("selection"),
                        "reference": config.get("reference"),
                        "datasets": [
                            {
                                "name": dataset.get("name"),
                                "format": dataset.get("format"),
                                "query": dataset.get("query"),
                                "generator": dataset.get("generator"),
                            }
                            for dataset in datasets
                            if isinstance(dataset, dict)
                        ],
                    }
                )
                continue
            presets.append(
                {
                    "name": config.name,
                    "path": str(path),
                    "valid": True,
                    "selection": config.selection,
                    "reference": config.reference,
                    "datasets": [
                        {
                            "name": dataset.name,
                            "format": dataset.format,
                            "query": dataset.query,
                            "generator": dataset.generator,
                        }
                        for dataset in config.datasets
                    ],
                }
            )
        return presets

    def list_contrasts(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not self.context.logs_dir.exists():
            return rows
        for summary_path in sorted(self.context.logs_dir.rglob("paired_contrast_summary.json")):
            try:
                payload = _read_json_dict(summary_path)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            try:
                rel_dir = summary_path.parent.resolve().relative_to(
                    self.context.logs_dir.resolve()
                ).as_posix()
                stat = summary_path.stat()
            except OSError:
                continue
            providers = payload.get("providers")
            provider_count = len(providers) if isinstance(providers, list) else 0
            theorem_pairs = payload.get("theorem_pairs")
            pair_count = len(theorem_pairs) if isinstance(theorem_pairs, list) else 0
            experiment = payload.get("experiment") if isinstance(payload.get("experiment"), dict) else {}
            rows.append(
                {
                    "rel_dir": rel_dir,
                    "run_id": payload.get("run_id") or rel_dir,
                    "generated_at": payload.get("generated_at"),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    "provider_count": provider_count,
                    "theorem_pair_count": pair_count,
                    "corpus": experiment.get("corpus"),
                    "budget": experiment.get("budget"),
                    "summary_file": summary_path.name,
                    "providers": providers if isinstance(providers, list) else [],
                }
            )
        rows.sort(
            key=lambda row: (
                row.get("generated_at") is not None,
                row.get("generated_at") or row.get("modified_at") or "",
                row["rel_dir"],
            ),
            reverse=True,
        )
        return rows

    def load_contrast(self, rel_dir: str) -> dict[str, Any]:
        if not rel_dir:
            raise ValueError("missing contrast")
        contrast_dir = _ensure_under(self.context.logs_dir, self.context.logs_dir / Path(rel_dir))
        summary_path = contrast_dir / "paired_contrast_summary.json"
        if not summary_path.exists():
            raise FileNotFoundError(rel_dir)
        payload = _read_json_dict(summary_path)
        if not isinstance(payload, dict):
            raise ValueError(f"invalid paired contrast summary: {summary_path}")
        payload["rel_dir"] = rel_dir
        return payload

    def list_runs(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        if not self.context.logs_dir.exists():
            return runs
        for provider_run in _discover_run_dirs(self.context.logs_dir):
            run_dir = provider_run.run_dir.resolve()
            rel_run_dir = run_dir.relative_to(self.context.logs_dir.resolve()).as_posix()
            run_config = _load_run_config(run_dir)
            run_status = _load_run_status(run_dir)
            artifacts = _inspect_run_artifacts(run_dir)
            summary = _load_summary(run_dir) if artifacts.has_summary else None
            aggregates = summary.get("aggregates") if isinstance(summary, dict) else None
            theorem_count = None
            if isinstance(aggregates, dict) and isinstance(aggregates.get("theorem_count"), int):
                theorem_count = aggregates["theorem_count"]
            elif isinstance(run_config, dict):
                selection = run_config.get("theorem_selection")
                if isinstance(selection, dict) and isinstance(selection.get("selected_count"), int):
                    theorem_count = selection["selected_count"]
            created_at = None
            if isinstance(run_config, dict):
                created_at = _coerce_str(run_config.get("created_at"))
            if created_at is None:
                try:
                    created_at = datetime.fromtimestamp(run_dir.stat().st_mtime, timezone.utc).isoformat()
                except OSError:
                    created_at = None
            runs.append(
                {
                    "rel_run_dir": rel_run_dir,
                    "run_id": run_config.get("run_id") if isinstance(run_config, dict) else run_dir.name,
                    "provider": provider_run.provider
                    or (run_config.get("provider") if isinstance(run_config, dict) else None),
                    "mode": run_config.get("mode") if isinstance(run_config, dict) else None,
                    "corpus": run_config.get("corpus") if isinstance(run_config, dict) else None,
                    "budget": run_config.get("budget_label") if isinstance(run_config, dict) else None,
                    "status": run_status.get("status") if isinstance(run_status, dict) else None,
                    "partial_results": run_status.get("partial_results") if isinstance(run_status, dict) else None,
                    "created_at": created_at,
                    "theorem_count": theorem_count,
                    "summary_available": artifacts.has_summary,
                    "is_basin_only": artifacts.is_basin_only,
                    "dashboard_incompatibility": artifacts.dashboard_incompatibility(),
                    "wild_type_solve_rate": (
                        aggregates.get("wild_type_solve_rate") if isinstance(aggregates, dict) else None
                    ),
                    "intervention_solve_rate": (
                        aggregates.get("intervention_solve_rate") if isinstance(aggregates, dict) else None
                    ),
                    "intervention_count": (
                        aggregates.get("intervention_count") if isinstance(aggregates, dict) else None
                    ),
                    "capabilities": run_status.get("capabilities") if isinstance(run_status, dict) else None,
                }
            )
        runs.sort(
            key=lambda row: (
                row.get("created_at") is not None,
                row.get("created_at") or "",
                row["rel_run_dir"],
            ),
            reverse=True,
        )
        return runs

    def _resolve_run(self, rel_run_dir: str) -> Path:
        if not rel_run_dir:
            raise ValueError("missing run")
        candidate = self.context.logs_dir / Path(rel_run_dir)
        return _ensure_under(self.context.logs_dir, candidate)

    def load_run(self, rel_run_dir: str) -> dict[str, Any]:
        from analysis.viz_payloads import build_dashboard_payload_v2, build_provider_deep_dive

        run_dir = self._resolve_run(rel_run_dir)
        run_config = _load_run_config(run_dir)
        run_status = _load_run_status(run_dir)
        summary = _load_summary(run_dir)
        theorem_names = _discover_theorem_names(run_dir, summary)
        payload: dict[str, Any] = {
            "rel_run_dir": rel_run_dir,
            "run_dir": str(run_dir),
            "run_config": run_config,
            "run_status": run_status,
            "root_files": _top_level_files(run_dir),
            "theorem_names": theorem_names,
        }
        if summary is not None:
            theorems = summary.get("theorems")
            if not isinstance(theorems, list):
                theorems = []
            payload["dashboard"] = build_dashboard_payload_v2(
                summary,
                run_dir,
                run_config,
                run_status,
                include_file_backed_details=False,
            )
            payload["theorem_rows"] = _theorem_rows(theorems)
            payload["behavior_breakdown"] = _intervention_behavior_counts(theorems)
        else:
            payload["dashboard"] = None
            payload["theorem_rows"] = []
            payload["behavior_breakdown"] = None
        provider_deep_dive = build_provider_deep_dive(run_dir)
        if provider_deep_dive is not None:
            payload["provider_deep_dive"] = provider_deep_dive
        return payload

    def load_theorem(self, rel_run_dir: str, theorem_name: str) -> dict[str, Any]:
        run_dir = self._resolve_run(rel_run_dir)
        theorem_dir = _ensure_under(run_dir, run_dir / theorem_name)
        if not theorem_dir.exists() or not theorem_dir.is_dir():
            raise FileNotFoundError(theorem_name)
        summary = _load_summary(run_dir)
        theorem_summary = None
        if isinstance(summary, dict):
            for entry in summary.get("theorems", []):
                if isinstance(entry, dict) and entry.get("name") == theorem_name:
                    theorem_summary = _compact_theorem_summary(entry)
                    break
        index = _variant_index(theorem_dir)
        return {
            "rel_run_dir": rel_run_dir,
            "theorem": theorem_name,
            "summary": theorem_summary,
            "index": index,
            "variant_summaries": _load_variant_summaries(theorem_dir, index),
        }

    def read_file(
        self,
        *,
        rel_run_dir: str,
        filename: str,
        theorem_name: str | None = None,
    ) -> tuple[str, bytes]:
        if "/" in filename or "\\" in filename:
            raise ValueError("invalid filename")
        run_dir = self._resolve_run(rel_run_dir)
        target = run_dir / filename if theorem_name is None else run_dir / theorem_name / filename
        target = _ensure_under(run_dir if theorem_name else self.context.logs_dir, target)
        if not target.exists():
            raise FileNotFoundError(filename)
        name = target.name
        if name.endswith(".json") or name.endswith(".json.gz"):
            payload = _read_json_auto(target)
            return ("application/json; charset=utf-8", json.dumps(payload, indent=2, ensure_ascii=True).encode("utf-8"))
        if name.endswith(".jsonl") or name.endswith(".jsonl.gz"):
            if name.endswith(".gz"):
                with gzip.open(target, "rt", encoding="utf-8") as handle:
                    text = handle.read()
            else:
                text = target.read_text(encoding="utf-8")
            return ("application/x-ndjson; charset=utf-8", text.encode("utf-8"))
        if target.suffix.lower() in TEXT_SUFFIXES:
            return ("text/plain; charset=utf-8", target.read_text(encoding="utf-8").encode("utf-8"))
        raise ValueError("unsupported file type")

    def launch_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind = _coerce_str(payload.get("kind"))
        if kind == "lean_run":
            argv = self._build_lean_command(payload, basin=False)
            label = f"lean run {payload.get('mode') or 'dev'}"
            return self.jobs.launch(kind=kind, label=label, argv=argv, cwd=DOSSIER_ROOT)
        if kind == "lean_basin":
            argv = self._build_lean_command(payload, basin=True)
            label = f"lean basin {payload.get('mode') or 'dev'}"
            return self.jobs.launch(kind=kind, label=label, argv=argv, cwd=DOSSIER_ROOT)
        if kind == "causal_contrast":
            argv = self._build_causal_contrast_command(payload)
            label = f"causal contrast {payload.get('providers') or 'heuristic'}"
            return self.jobs.launch(kind=kind, label=label, argv=argv, cwd=DOSSIER_ROOT)
        if kind == "postprocess":
            argv = ["uv", "run", "python", "wonton.py", "postprocess", "--agent"]
            run_dir = _coerce_str(payload.get("run_dir"))
            if run_dir:
                argv.extend(["--run-dir", str(self._resolve_run(run_dir))])
            else:
                argv.extend(["--logs-dir", str(self.context.logs_dir)])
            limit = _coerce_int(payload.get("limit"))
            if limit is not None:
                argv.extend(["--limit", str(limit)])
            if _coerce_bool(payload.get("dry_run")):
                argv.append("--dry-run")
            label = f"postprocess {run_dir or 'logs'}"
            return self.jobs.launch(kind=kind, label=label, argv=argv, cwd=DOSSIER_ROOT)
        if kind == "lake_reconcile":
            argv = [
                "uv",
                "run",
                "python",
                "wonton.py",
                "lake",
                "reconcile",
                "--logs-dir",
                str(self.context.logs_dir),
                "--db",
                str(self.context.lake_db_path),
            ]
            if _coerce_bool(payload.get("prune")):
                argv.append("--prune")
            return self.jobs.launch(kind=kind, label="lake reconcile", argv=argv, cwd=DOSSIER_ROOT)
        if kind == "lake_job_preset":
            config_path = _coerce_str(payload.get("config"))
            if config_path is None:
                raise ValueError("missing preset config")
            preset = Path(config_path)
            preset = _ensure_under(self.context.presets_dir, preset)
            out_dir = self.context.lake_jobs_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{preset.stem}"
            argv = [
                "uv",
                "run",
                "python",
                "wonton.py",
                "lake",
                "job",
                "run",
                "--config",
                str(preset),
                "--logs-dir",
                str(self.context.logs_dir),
                "--db",
                str(self.context.lake_db_path),
                "--out-dir",
                str(out_dir),
            ]
            return self.jobs.launch(
                kind=kind,
                label=f"lake preset {preset.stem}",
                argv=argv,
                cwd=DOSSIER_ROOT,
                output_path=str(out_dir),
                metadata={"preset": preset.stem},
            )
        if kind == "analysis_export":
            output = _coerce_str(payload.get("output")) or "analysis/notebooks/deep_analysis.html"
            argv = [
                "uv",
                "run",
                "python",
                "wonton.py",
                "analysis",
                "export",
                "--output",
                output,
            ]
            return self.jobs.launch(
                kind=kind,
                label="analysis export",
                argv=argv,
                cwd=DOSSIER_ROOT,
                output_path=str((DOSSIER_ROOT / output).resolve()),
            )
        raise ValueError(f"unknown job kind: {kind!r}")

    def _build_lean_command(self, payload: dict[str, Any], *, basin: bool) -> list[str]:
        argv = ["uv", "run", "python", "wonton.py", "lean", "basin" if basin else "run", "--agent", "--plain"]
        if basin:
            seeds = _coerce_int(payload.get("seeds"))
            if seeds is None or seeds < 1:
                raise ValueError("lean basin requires seeds >= 1")
            argv.extend(["--seeds", str(seeds)])
            if _coerce_bool(payload.get("blind")):
                argv.append("--blind")
        for key, flag in (
            ("mode", "--mode"),
            ("corpus", "--corpus"),
            ("provider", "--provider"),
            ("budget", "--budget"),
            ("theorem", "--theorem"),
            ("run_id", "--run-id"),
        ):
            value = _coerce_str(payload.get(key))
            if value is not None:
                argv.extend([flag, value])
        for key, flag in (
            ("limit", "--limit"),
            ("sample", "--sample"),
            ("seed", "--seed"),
            ("workers", "--workers"),
        ):
            value = _coerce_int(payload.get(key))
            if value is not None:
                argv.extend([flag, str(value)])
        if basin:
            if _coerce_bool(payload.get("trace_mcts"), default=True):
                argv.append("--trace-mcts")
            else:
                argv.append("--no-trace-mcts")
        else:
            if _coerce_bool(payload.get("with_interventions"), default=True):
                argv.append("--with-interventions")
            else:
                argv.append("--wild-only")
            if _coerce_bool(payload.get("trace_mcts"), default=True):
                argv.append("--trace-mcts")
            else:
                argv.append("--no-trace-mcts")
            if _coerce_bool(payload.get("analysis")):
                argv.append("--analysis")
        return argv

    def _build_causal_contrast_command(self, payload: dict[str, Any]) -> list[str]:
        argv = ["uv", "run", "python", "-m", "experiments.causal_contrast.run"]
        for key, flag in (
            ("providers", "--providers"),
            ("corpus", "--corpus"),
            ("budget", "--budget"),
            ("run_id", "--run-id"),
            ("mcts_expansion_policy", "--mcts-expansion-policy"),
        ):
            value = _coerce_str(payload.get(key))
            if value is not None:
                argv.extend([flag, value])
        for key, flag in (
            ("limit", "--limit"),
            ("sample", "--sample"),
            ("seed", "--seed"),
            ("workers", "--workers"),
            ("mcts_agents", "--mcts-agents"),
            ("mcts_inflight", "--mcts-inflight"),
            ("mcts_virtual_loss", "--mcts-virtual-loss"),
            ("mcts_block_duration", "--mcts-block-duration"),
            ("mcts_block_seed", "--mcts-block-seed"),
            ("mcts_unfreeze_after", "--mcts-unfreeze-after"),
            ("mcts_reroute_max", "--mcts-reroute-max"),
            ("mcts_delay_duration", "--mcts-delay-duration"),
            ("mcts_delay_seed", "--mcts-delay-seed"),
        ):
            value = _coerce_int(payload.get(key))
            if value is not None:
                argv.extend([flag, str(value)])
        for key, flag in (
            ("mcts_block_fraction", "--mcts-block-fraction"),
            ("mcts_block_immovable_fraction", "--mcts-block-immovable-fraction"),
            ("mcts_unfreeze_prob", "--mcts-unfreeze-prob"),
            ("mcts_delay_prob", "--mcts-delay-prob"),
        ):
            value = _coerce_float(payload.get(key))
            if value is not None:
                argv.extend([flag, str(value)])
        if _coerce_bool(payload.get("with_interventions"), default=True):
            argv.append("--with-interventions")
        else:
            argv.append("--wild-only")
        if _coerce_bool(payload.get("trace_mcts"), default=True):
            argv.append("--trace-mcts")
        else:
            argv.append("--no-trace-mcts")
        if _coerce_bool(payload.get("analysis")):
            argv.append("--analysis")
        if _coerce_bool(payload.get("no_sync"), default=True):
            argv.append("--no-sync")
        return argv


class LabHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, app: LabApp, static_dir: Path, fonts_dir: Path, **kwargs):
        self.app = app
        self.static_dir = static_dir
        self.fonts_dir = fonts_dir
        super().__init__(*args, directory=str(static_dir), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed)
            return
        if parsed.path.startswith("/fonts/"):
            self._handle_fonts(parsed)
            return
        if parsed.path == "/":
            self.path = "/index.html"
            return super().do_GET()
        target = self.static_dir / parsed.path.lstrip("/")
        if target.exists() and target.is_file():
            return super().do_GET()
        self.path = "/index.html"
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/jobs/launch":
            payload = self._read_json_body()
            if not isinstance(payload, dict):
                return self._send_error(HTTPStatus.BAD_REQUEST, "body must be an object")
            try:
                job = self.app.launch_job(payload)
            except Exception as exc:
                return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            self._send_json(job, status=HTTPStatus.CREATED)
            return
        if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/cancel"):
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) != 4:
                return self._send_error(HTTPStatus.NOT_FOUND, "unknown endpoint")
            job = self.app.jobs.cancel(parts[2])
            if job is None:
                return self._send_error(HTTPStatus.NOT_FOUND, "job not found")
            self._send_json(job)
            return
        self._send_error(HTTPStatus.NOT_FOUND, "unknown endpoint")

    def _handle_api(self, parsed) -> None:
        parts = [part for part in parsed.path.split("/") if part]
        query = parse_qs(parsed.query)
        if parts == ["api", "bootstrap"]:
            return self._send_json(self.app.bootstrap())
        if parts == ["api", "analysis"]:
            return self._send_json(self.app.analysis_state())
        if parts == ["api", "runs"]:
            return self._send_json({"runs": self.app.list_runs()})
        if parts == ["api", "contrasts"]:
            return self._send_json({"contrasts": self.app.list_contrasts()})
        if parts == ["api", "contrast"]:
            contrast = self._query_value(query, "contrast")
            if contrast is None:
                return self._send_error(HTTPStatus.BAD_REQUEST, "missing contrast")
            try:
                payload = self.app.load_contrast(contrast)
            except FileNotFoundError:
                return self._send_error(HTTPStatus.NOT_FOUND, f"contrast not found: {contrast}")
            except ValueError as exc:
                return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return self._send_json(payload)
        if parts == ["api", "run"]:
            run = self._query_value(query, "run")
            if run is None:
                return self._send_error(HTTPStatus.BAD_REQUEST, "missing run")
            try:
                payload = self.app.load_run(run)
            except FileNotFoundError:
                return self._send_error(HTTPStatus.NOT_FOUND, f"run not found: {run}")
            except ValueError as exc:
                return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return self._send_json(payload)
        if parts == ["api", "theorem"]:
            run = self._query_value(query, "run")
            theorem = self._query_value(query, "theorem")
            if run is None or theorem is None:
                return self._send_error(HTTPStatus.BAD_REQUEST, "missing run or theorem")
            try:
                payload = self.app.load_theorem(run, theorem)
            except FileNotFoundError:
                return self._send_error(HTTPStatus.NOT_FOUND, f"theorem not found: {theorem}")
            except ValueError as exc:
                return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return self._send_json(payload)
        if parts == ["api", "file"]:
            run = self._query_value(query, "run")
            filename = self._query_value(query, "file")
            theorem = self._query_value(query, "theorem")
            if run is None or filename is None:
                return self._send_error(HTTPStatus.BAD_REQUEST, "missing run or file")
            try:
                content_type, body = self.app.read_file(rel_run_dir=run, theorem_name=theorem, filename=filename)
            except FileNotFoundError:
                return self._send_error(HTTPStatus.NOT_FOUND, f"file not found: {filename}")
            except ValueError as exc:
                return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return self._send_bytes(body, content_type=content_type)
        if parts == ["api", "notebook"]:
            path = self.app.context.notebook_html
            if not path.exists():
                return self._send_error(HTTPStatus.NOT_FOUND, "notebook export missing")
            try:
                data = path.read_bytes()
            except OSError as exc:
                return self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return self._send_bytes(data, content_type="text/html; charset=utf-8")
        if parts == ["api", "jobs"]:
            return self._send_json({"jobs": self.app.jobs.list_jobs()})
        if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
            job = self.app.jobs.get_job(parts[2])
            if job is None:
                return self._send_error(HTTPStatus.NOT_FOUND, "job not found")
            return self._send_json(job)
        if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "log":
            text = self.app.jobs.read_log(parts[2])
            if text is None:
                return self._send_error(HTTPStatus.NOT_FOUND, "job not found")
            return self._send_bytes(text.encode("utf-8"), content_type="text/plain; charset=utf-8")
        self._send_error(HTTPStatus.NOT_FOUND, "unknown endpoint")

    def _handle_fonts(self, parsed) -> None:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            return self._send_error(HTTPStatus.NOT_FOUND, "unknown font path")
        target = self.fonts_dir / "/".join(parts[1:])
        try:
            target = _ensure_under(self.fonts_dir, target)
        except ValueError as exc:
            return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        if not target.exists() or not target.is_file():
            return self._send_error(HTTPStatus.NOT_FOUND, "font not found")
        try:
            data = target.read_bytes()
        except OSError as exc:
            return self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
        return self._send_bytes(data, content_type=self.guess_type(str(target)) or "application/octet-stream")

    def _read_json_body(self) -> Any:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return None
        try:
            length = int(raw_length)
        except ValueError:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def _query_value(self, query: dict[str, list[str]], key: str) -> str | None:
        values = query.get(key)
        if not values:
            return None
        return unquote(values[0])

    def _send_json(self, payload: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2, ensure_ascii=True).encode("utf-8")
        self._send_bytes(body, status=status, content_type="application/json; charset=utf-8")

    def _send_bytes(
        self,
        body: bytes,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message, "status": int(status)}, status=status)


def build_context(*, logs_dir: str | None) -> LabContext:
    resolved_logs = _resolve_logs_dir_arg(logs_dir)
    artifacts_dir = resolve_artifacts_root().resolve()
    state_dir = _runtime_lab_root()
    lake_root = artifacts_dir / "lake"
    fonts_dir = _resolve_fonts_dir(DOSSIER_ROOT / "analysis" / "lab_server.py", None)
    return LabContext(
        logs_dir=resolved_logs,
        artifacts_dir=artifacts_dir,
        state_dir=state_dir,
        static_dir=STATIC_DIR,
        fonts_dir=fonts_dir,
        lake_db_path=(lake_root / "lake.duckdb").resolve(),
        lake_exports_dir=(lake_root / "exports").resolve(),
        lake_jobs_dir=(lake_root / "jobs").resolve(),
        notebook_html=NOTEBOOK_PATH.resolve(),
        presets_dir=PRESETS_DIR.resolve(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Wonton Lab local browser workbench")
    parser.add_argument("--logs-dir", default="logs", help="Logs root (default: runtime logs root or ./logs)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--open-browser", action="store_true", help="Open the browser on startup")
    args = parser.parse_args()

    context = build_context(logs_dir=args.logs_dir)
    app = LabApp(context)
    handler = lambda *handler_args, **handler_kwargs: LabHandler(
        *handler_args,
        app=app,
        static_dir=context.static_dir,
        fonts_dir=context.fonts_dir,
        **handler_kwargs,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Wonton Lab listening on {url}")
    print(f"Logs root: {context.logs_dir}")
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
