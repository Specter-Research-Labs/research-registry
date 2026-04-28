from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from prover.mcts import TACTIC_FAMILIES
from prover.providers.base import normalize_tactic, tactic_family
from runtime_paths import resolve_artifacts_root as _resolve_runtime_artifacts_root


@dataclass(frozen=True)
class ProviderRun:
    run_dir: Path
    provider: str | None


@dataclass(frozen=True)
class RunArtifacts:
    summary_path: Path | None
    basin_seeds: int | None
    has_basin_analysis: bool

    @property
    def has_summary(self) -> bool:
        return self.summary_path is not None

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


def resolve_artifacts_dir() -> Path:
    return _resolve_runtime_artifacts_root()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def read_json_gz(path: Path) -> Any:
    with gzip.open(path, "rt") as f:
        return json.load(f)


def read_json_auto(path: Path) -> Any:
    if path.suffix == ".gz" or path.name.endswith(".json.gz"):
        return read_json_gz(path)
    return read_json(path)


def write_json_atomic(path: Path, payload: Any, *, indent: int = 2) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=indent))
    tmp.replace(path)
    if not path.exists():
        raise RuntimeError(f"Missing after atomic write: {path}")


def write_json_gz_atomic(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt") as f:
        json.dump(payload, f)
    tmp.replace(path)
    if not path.exists():
        raise RuntimeError(f"Missing after atomic write: {path}")


def relpath_under(base: Path, path: Path) -> str:
    """Return a stable, non-absolute relative path when possible.

    We avoid embedding absolute host paths into artifacts that may be copied or committed.
    """
    try:
        rel = path.resolve().relative_to(base.resolve())
    except ValueError:
        return path.name
    return str(rel)


def inspect_run_artifacts(run_dir: Path) -> RunArtifacts:
    run_dir = run_dir.resolve()
    summary_path = None
    summary_gz = run_dir / "summary.json.gz"
    summary_json = run_dir / "summary.json"
    if summary_gz.exists():
        summary_path = summary_gz
    elif summary_json.exists():
        summary_path = summary_json

    if summary_path is not None:
        return RunArtifacts(
            summary_path=summary_path,
            basin_seeds=None,
            has_basin_analysis=False,
        )

    basin_seeds = None
    run_config_path = run_dir / "run_config.json"
    if run_config_path.exists():
        try:
            run_config = read_json(run_config_path)
        except Exception:
            run_config = None
        if isinstance(run_config, dict):
            raw_basin_seeds = run_config.get("basin_seeds")
            if isinstance(raw_basin_seeds, int) and raw_basin_seeds > 0:
                basin_seeds = raw_basin_seeds

    has_basin_analysis = False
    if run_dir.exists():
        for child in sorted(p for p in run_dir.iterdir() if p.is_dir()):
            if child.name.startswith(".") or child.name.startswith("provider="):
                continue
            if (child / "basin_analysis.json").exists() or (
                child / "basin_analysis.json.gz"
            ).exists():
                has_basin_analysis = True
                break

    return RunArtifacts(
        summary_path=summary_path,
        basin_seeds=basin_seeds,
        has_basin_analysis=has_basin_analysis,
    )


def iter_provider_runs(run_dir: Path) -> list[ProviderRun]:
    """Return a list of single-provider run dirs.

    Supports:
    - Single-provider run dir: contains run_config.json
    - Multi-provider root dir: contains provider=<name>/ subdirs with run_config.json
    """
    run_dir = run_dir.resolve()
    provider_dirs = sorted(p for p in run_dir.glob("provider=*") if p.is_dir())
    result: list[ProviderRun] = []
    for p in provider_dirs:
        if not (p / "run_config.json").exists():
            continue
        provider = p.name.split("=", 1)[1] if "=" in p.name else None
        result.append(ProviderRun(run_dir=p, provider=provider))
    if result:
        return result

    # Multi-provider roots also write a top-level run_config.json. Prefer provider subruns when
    # present, but fall back to treating this as a single-provider run if no provider dirs exist.
    if (run_dir / "run_config.json").exists():
        return [ProviderRun(run_dir=run_dir, provider=None)]

    raise FileNotFoundError(f"No run_config.json found under: {run_dir}")


def iter_theorem_variant_prefixes(theorem_dir: Path) -> Iterable[str]:
    """Yield variant prefixes that have MCTS traces.

    Example: wild_type_mcts_trace.jsonl -> prefix wild_type
    """
    for trace_path in sorted(theorem_dir.glob("*_mcts_trace.jsonl*")):
        name = trace_path.name
        # macOS AppleDouble sidecars (._*) are binary metadata, not real traces.
        if name.startswith("._"):
            continue
        if not name.endswith(".jsonl") and not name.endswith(".jsonl.gz"):
            continue
        if "_mcts_trace" not in name:
            continue
        yield name.split("_mcts_trace", 1)[0]


def ged_value(entry: object) -> float | None:
    if not isinstance(entry, dict):
        return None
    value = entry.get("value")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_history_total_attempts(history: dict[str, Any]) -> int | None:
    detour = history.get("detour_metrics")
    if isinstance(detour, dict):
        total = detour.get("total_attempts")
        if isinstance(total, int):
            return total
    iterations = history.get("iterations")
    if not isinstance(iterations, list):
        return None
    total_attempts = 0
    for rec in iterations:
        if not isinstance(rec, dict):
            continue
        attempts = rec.get("attempts")
        if not isinstance(attempts, list):
            continue
        total_attempts += sum(1 for a in attempts if isinstance(a, dict))
    return total_attempts


def load_candidates_for_iterations(
    trace_path: Path,
    *,
    required: dict[int, str],
) -> tuple[dict[int, list[str]], list[str]]:
    found: dict[int, list[str]] = {}
    notes: list[str] = []
    if not trace_path.exists():
        return found, [f"missing_trace: {trace_path.name}"]

    remaining = set(required.keys())
    bad_json_lines = 0
    try:
        with trace_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    bad_json_lines += 1
                    continue
                if not isinstance(rec, dict) or rec.get("event") != "iteration":
                    continue
                it = rec.get("iteration")
                if not isinstance(it, int) or it not in remaining:
                    continue
                node = rec.get("node")
                if not isinstance(node, dict):
                    continue
                mvar = node.get("mvar_id")
                if not isinstance(mvar, str) or mvar != required[it]:
                    continue
                tactics = rec.get("tactics")
                if not isinstance(tactics, list):
                    continue
                candidates: list[str] = []
                for item in tactics:
                    if not isinstance(item, dict):
                        continue
                    t = item.get("tactic")
                    if isinstance(t, str) and t.strip():
                        candidates.append(t)
                found[it] = candidates
                remaining.remove(it)
                if not remaining:
                    break
    except OSError as exc:
        notes.append(f"trace_read_failed:{type(exc).__name__}:{exc}")
    if bad_json_lines:
        notes.append(f"trace_bad_json_lines:{bad_json_lines}")
    if remaining:
        notes.append(f"missing_trace_iterations:{len(remaining)}")
    return found, notes


def family_index(fam: str) -> int:
    try:
        return TACTIC_FAMILIES.index(fam)
    except ValueError:
        return len(TACTIC_FAMILIES) - 1


@dataclass(frozen=True)
class SolutionStepExtraction:
    valid: bool
    validity_notes: list[str]
    tau_agent: int | None
    step_specs: list[dict[str, Any]] = field(default_factory=list)
    expected_steps: int = 0
    dropped_steps: int = 0
    candidates_by_iter: dict[int, list[str]] = field(default_factory=dict)


def extract_solution_steps(
    *,
    theorem_dir: Path,
    variant: str,
    mvar_to_sig: dict[str, str] | None = None,
) -> SolutionStepExtraction:
    history_path = theorem_dir / f"{variant}_history.json"
    tree_path = theorem_dir / f"{variant}_mcts_tree.json"
    trace_path = theorem_dir / f"{variant}_mcts_trace.jsonl"

    def _invalid(notes: list[str]) -> SolutionStepExtraction:
        return SolutionStepExtraction(valid=False, validity_notes=notes, tau_agent=None)

    if not history_path.exists():
        return _invalid([f"missing history: {history_path.name}"])
    if not tree_path.exists():
        return _invalid([f"missing mcts_tree: {tree_path.name}"])

    history = read_json(history_path)
    if not isinstance(history, dict):
        return _invalid(["history is not an object"])
    tau_agent = safe_history_total_attempts(history)
    if tau_agent is None or tau_agent <= 0:
        return _invalid([f"invalid tau_agent (total_attempts): {tau_agent!r}"])

    solution_path = history.get("solution_path")
    if not isinstance(solution_path, list) or not solution_path:
        return _invalid(["missing solution_path (requires solved run)"])

    tree = read_json(tree_path)
    if not isinstance(tree, dict):
        return _invalid(["mcts_tree is not an object"])
    nodes = tree.get("nodes")
    if not isinstance(nodes, dict):
        return _invalid(["mcts_tree.nodes must be a dict"])

    iterations = history.get("iterations")
    if not isinstance(iterations, list):
        return _invalid(["history.iterations must be a list"])

    notes: list[str] = []
    step_specs: list[dict[str, Any]] = []
    required_trace: dict[int, str] = {}
    expected_steps = sum(1 for step in solution_path if isinstance(step, dict))
    dropped_steps = 0

    for step in solution_path:
        if not isinstance(step, dict):
            continue
        mvar_id = step.get("mvar_id")
        tactic = step.get("tactic")
        if not isinstance(mvar_id, str) or not mvar_id:
            notes.append("solution_step missing mvar_id")
            dropped_steps += 1
            continue
        if not isinstance(tactic, str) or not tactic:
            notes.append(f"solution_step missing tactic for mvar_id={mvar_id}")
            dropped_steps += 1
            continue
        node = nodes.get(mvar_id)
        if not isinstance(node, dict):
            notes.append(f"mcts_tree missing node for mvar_id={mvar_id}")
            dropped_steps += 1
            continue

        goal_sig = node.get("goal_sig") if isinstance(node.get("goal_sig"), str) else None
        if goal_sig is None and mvar_to_sig is not None:
            sig = mvar_to_sig.get(mvar_id)
            goal_sig = sig if isinstance(sig, str) else None
        if not isinstance(goal_sig, str) or not goal_sig:
            notes.append(f"missing goal_sig for mvar_id={mvar_id}")
            dropped_steps += 1
            continue

        children_map = node.get("children")
        if not isinstance(children_map, dict):
            notes.append(f"mcts_tree node.children missing for mvar_id={mvar_id}")
            dropped_steps += 1
            continue
        expected_children = children_map.get(tactic)
        if not isinstance(expected_children, list):
            notes.append(f"mcts_tree missing children for tactic={tactic!r} mvar_id={mvar_id}")
            dropped_steps += 1
            continue
        expected_child_set = {c for c in expected_children if isinstance(c, str)}

        solving_iter: int | None = None
        for rec in iterations:
            if not isinstance(rec, dict):
                continue
            selected = rec.get("selected_path")
            if not isinstance(selected, list) or not selected:
                continue
            if selected[-1] != mvar_id:
                continue
            attempts = rec.get("attempts")
            if not isinstance(attempts, list):
                continue
            for a in attempts:
                if not isinstance(a, dict):
                    continue
                if a.get("outcome") != "success":
                    continue
                if a.get("tactic") != tactic:
                    continue
                child_ids = a.get("child_mvar_ids", [])
                if not isinstance(child_ids, list):
                    continue
                child_set = {c for c in child_ids if isinstance(c, str)}
                if child_set == expected_child_set:
                    it = rec.get("iteration")
                    if isinstance(it, int):
                        solving_iter = it
                        break
            if solving_iter is not None:
                break

        if solving_iter is None:
            notes.append(f"missing solving iteration for mvar_id={mvar_id} tactic={tactic!r}")
            dropped_steps += 1
            continue

        required_trace[solving_iter] = mvar_id
        step_specs.append(
            {
                "mvar_id": mvar_id,
                "iteration": solving_iter,
                "goal_sig": goal_sig,
                "tactic": tactic,
                "tactic_norm": normalize_tactic(tactic),
                "tactic_family": tactic_family(tactic),
            }
        )

    if not step_specs:
        notes.append("no usable solution steps")
        return SolutionStepExtraction(
            valid=False, validity_notes=notes, tau_agent=tau_agent,
        )
    if expected_steps != len(step_specs):
        notes.append(f"partial_solution_path: expected={expected_steps} got={len(step_specs)}")

    candidates_by_iter, trace_notes = load_candidates_for_iterations(
        trace_path,
        required=required_trace,
    )
    notes.extend(trace_notes)

    return SolutionStepExtraction(
        valid=True,
        validity_notes=notes,
        tau_agent=tau_agent,
        step_specs=step_specs,
        expected_steps=expected_steps,
        dropped_steps=dropped_steps,
        candidates_by_iter=candidates_by_iter,
    )
