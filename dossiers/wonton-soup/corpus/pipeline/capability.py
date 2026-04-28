from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from corpus.artifacts import (
    CorpusRef,
    compute_build_id,
    iter_jsonl,
    parse_corpus_ref,
    resolve_corpus_build_dir,
    sha256_file,
    write_current_id,
    write_json_atomic,
    write_jsonl,
)

DOSSIER_ROOT = Path(__file__).resolve().parents[2]


def _slug(text: str) -> str:
    s = text.strip()
    for ch in (":", "#", "@", "/", "\\", " "):
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_") or "corpus"


def _has_ymd_prefix(value: str) -> bool:
    if len(value) < 11:
        return False
    if value[4] != "-" or value[7] != "-" or value[10] != "-":
        return False
    y = value[0:4]
    m = value[5:7]
    d = value[8:10]
    return y.isdigit() and m.isdigit() and d.isdigit()


def _normalize_run_id_for_logs(run_id: str) -> str:
    """Match orchestrator.lean's run_id prefixing logic, but keep it stable.

    `run_corpus` prefixes the first path component with a date if it doesn't already start
    with YYYY-MM-DD. For sweeps we want run dirs to be stable across resume, so if the head
    already contains a YYYY-MM-DD substring we use that.
    """
    if run_id.startswith("corpus-"):
        return run_id
    head, sep, tail = run_id.partition("/")
    if _has_ymd_prefix(head):
        return run_id
    m = re.search(r"\\b\\d{4}-\\d{2}-\\d{2}\\b", head)
    date = m.group(0) if m else datetime.now().strftime("%Y-%m-%d")
    return f"{date}-{head}{sep}{tail}" if sep else f"{date}-{head}"


def _load_manifest(build_dir: Path) -> dict[str, Any]:
    path = build_dir / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"manifest.json not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid manifest.json (not an object): {path}")
    return data


def _median_or_none(values: list[int]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


@dataclass(frozen=True)
class CapabilitySweepResult:
    corpus_ref: str
    build_dir: Path
    sweep_root: Path
    runs: list[Path]
    capability_path: Path
    derived_feasible_dir: Path
    reachable_count: int
    total_count: int
    reachable_rate: float


def _derive_feasible_slice(
    *,
    output_build_dir: Path,
    items_build_dir: Path,
    backend: str,
    corpus_id: str,
    parent_build_id: str,
    parent_manifest: dict[str, Any],
    capability_path: Path,
    reachable_ids: set[str],
    reachable_threshold: float,
) -> Path:
    derived_root = output_build_dir / "derived" / "feasible"
    derived_root.mkdir(parents=True, exist_ok=True)

    items_path = items_build_dir / str(parent_manifest.get("items_file") or "items.jsonl")
    items: list[dict[str, Any]] = []
    for row in iter_jsonl(items_path):
        item_id = row.get("item_id")
        if isinstance(item_id, str) and item_id in reachable_ids:
            items.append(row)

    tmp_dir = derived_root / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_items = tmp_dir / f"items.{os.getpid()}.jsonl.tmp"
    write_jsonl(tmp_items, items)
    derived_items_sha = sha256_file(tmp_items)
    capability_sha = sha256_file(capability_path)

    fingerprint = {
        "kind": "derived_feasible",
        "parent_build_id": parent_build_id,
        "parent_items_sha256": str(parent_manifest.get("items_sha256") or ""),
        "capability_sha256": capability_sha,
        "derived_items_sha256": derived_items_sha,
        "derived_items_total": len(items),
    }
    derived_build_id = compute_build_id(fingerprint)
    derived_dir = derived_root / derived_build_id
    if derived_dir.exists():
        write_current_id(derived_root, derived_build_id)
        copied = derived_dir / "capability.jsonl"
        if not copied.exists():
            shutil.copy2(capability_path, copied)
        if tmp_items.exists():
            tmp_items.unlink()
        return derived_dir

    derived_dir.mkdir(parents=True, exist_ok=False)
    tmp_items.replace(derived_dir / "items.jsonl")
    shutil.copy2(capability_path, derived_dir / "capability.jsonl")

    provenance = list(parent_manifest.get("provenance") or [])
    provenance.append(
        {
            "kind": "derived",
            "derived_kind": "feasible",
            "parent_build_id": parent_build_id,
            "capability_sha256": capability_sha,
            "reachable_threshold": reachable_threshold,
        }
    )
    build_config = dict(parent_manifest.get("build_config") or {})
    build_config.update(
        {
            "derived_kind": "feasible",
            "parent_build_id": parent_build_id,
            "capability_sha256": capability_sha,
            "reachable_threshold": reachable_threshold,
        }
    )
    manifest = {
        **parent_manifest,
        "build_id": derived_build_id,
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "provenance": provenance,
        "build_config": build_config,
        "counts": {"items_total": len(items)},
        "items_file": "items.jsonl",
        "items_sha256": derived_items_sha,
        "parent": {
            "build_id": parent_build_id,
            "items_sha256": str(parent_manifest.get("items_sha256") or ""),
        },
    }
    write_json_atomic(derived_dir / "manifest.json", manifest)
    write_current_id(derived_root, derived_build_id)
    if tmp_dir.exists():
        try:
            tmp_dir.rmdir()
        except OSError:
            pass
    return derived_dir


def run_lean_capability_sweep(
    *,
    corpus_ref: str,
    sweep_root: str | None = None,
    providers: list[str] | None = None,
    include_heuristic: bool = False,
    mcts_modes: list[str] | None = None,
    distributed_agents: int | None = None,
    distributed_inflight: int | None = None,
    basin_seeds: int = 5,
    budget: str = "deep",
    budget_tiers: list[int] | None = None,
    deepseek_num_samples: int | None = None,
    bfs_num_samples: int | None = None,
    internlm_num_samples: int | None = None,
    offset: int = 0,
    sample: int | None = None,
    seed: int | None = None,
    reachable_threshold: float = 0.2,
    min_feasible_rate: float = 0.05,
    allow_low_feasible: bool = False,
    allow_partial: bool = False,
    resume: bool = False,
) -> CapabilitySweepResult:
    """Gate B for Lean: run basin analysis across provider x mcts_mode and derive feasible slice.

    This uses the existing basin-analysis machinery (run_corpus(..., basin_seeds=N)).
    """
    from orchestrator.lean import BUDGET_PRESETS, resolve_logs_dir, run_corpus

    ref = parse_corpus_ref(corpus_ref)
    base_ref = CorpusRef(
        backend=ref.backend,
        corpus_id=ref.corpus_id,
        build_id=ref.build_id,
        derived=None,
    )
    base_build_dir = resolve_corpus_build_dir(base_ref)
    items_build_dir = base_build_dir
    if ref.derived is not None:
        derived_root = base_build_dir / "derived" / ref.derived
        if not derived_root.exists():
            raise FileNotFoundError(f"Derived path not found: {derived_root}")
        current = derived_root / "CURRENT"
        if current.exists():
            derived_build_id = current.read_text().strip()
            if not derived_build_id:
                raise ValueError(f"Empty CURRENT pointer: {current}")
            items_build_dir = derived_root / derived_build_id
        else:
            items_build_dir = derived_root

    manifest = _load_manifest(items_build_dir)
    if str(manifest.get("backend") or ref.backend) != "lean":
        raise ValueError(
            f"Expected a Lean corpus artifact (backend=lean), got: {manifest.get('backend')}"
        )

    corpus_id = str(manifest.get("corpus_id") or ref.corpus_id)
    parent_build_id = str(manifest.get("build_id") or "")
    if not parent_build_id:
        raise ValueError("manifest.json missing build_id")

    if providers is None:
        providers = ["reprover", "deepseek"]
        if include_heuristic:
            providers.append("heuristic")
    if not providers:
        raise ValueError("providers must be non-empty")
    if mcts_modes is None:
        mcts_modes = ["centralized"]
    mcts_modes = [m.strip() for m in mcts_modes if m.strip()]
    if not mcts_modes:
        raise ValueError("mcts_modes must be non-empty")
    for mode in mcts_modes:
        if mode not in {"centralized", "distributed"}:
            raise ValueError(f"Unknown mcts_mode: {mode}")

    if budget_tiers is None:
        if budget not in BUDGET_PRESETS:
            raise ValueError(
                f"Unknown budget preset: {budget!r} (expected one of {sorted(BUDGET_PRESETS)})"
            )
        budget_tiers = list(BUDGET_PRESETS[budget])

    if sample is not None and seed is None:
        raise ValueError("--seed is required when using --sample")

    distributed_settings: dict[str, Any] | None = None
    if "distributed" in set(mcts_modes):
        if distributed_agents is None or distributed_inflight is None:
            raise ValueError(
                "--distributed-agents and --distributed-inflight are required when running "
                "distributed MCTS"
            )
        distributed_settings = {"agents": distributed_agents, "inflight": distributed_inflight}

    logs_dir = resolve_logs_dir()
    if sweep_root is None:
        ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        sweep_root_path = logs_dir / f"{ts}-capability" / _slug(corpus_ref)
        sweep_root_path.mkdir(parents=True, exist_ok=True)
    else:
        sweep_root_path = Path(os.path.expanduser(sweep_root)).resolve()
        try:
            sweep_root_path.relative_to(logs_dir)
        except ValueError as e:
            raise ValueError(
                f"--sweep-root must be under {logs_dir}, got: {sweep_root_path}"
            ) from e
        sweep_root_path.mkdir(parents=True, exist_ok=True)

    runs: list[Path] = []
    for provider in providers:
        for mode in mcts_modes:
            shard = ""
            if sample is not None:
                shard = f"sample={sample}/seed={seed}/offset={offset}/"
            run_rel = (
                Path(sweep_root_path.relative_to(logs_dir))
                / shard
                / f"provider={provider}"
                / f"mcts={mode}"
            )
            run_id = _normalize_run_id_for_logs(run_rel.as_posix())
            run_dir = logs_dir / run_id
            run_status_path = run_dir / "run_status.json"
            if run_status_path.exists():
                try:
                    run_status = json.loads(run_status_path.read_text(encoding="utf-8"))
                except Exception:
                    run_status = None
                if isinstance(run_status, dict) and run_status.get("status") == "completed":
                    runs.append(run_dir)
                    continue
                if not resume:
                    status = run_status.get("status") if isinstance(run_status, dict) else "unknown"
                    raise RuntimeError(
                        f"Capability run already exists but is not completed: {run_dir} "
                        f"(status={status}); re-run with --resume to continue"
                    )
            ds = distributed_settings if mode == "distributed" else None
            asyncio.run(
                run_corpus(
                    str(DOSSIER_ROOT / "lean_project"),
                    budget_tiers=budget_tiers,
                    budget_label=budget,
                    provider_name=provider,
                    device=None,
                    use_sampling=False,
                    debug=False,
                    skip_interventions=True,
                    block_easy=False,
                    corpus=corpus_ref,
                    limit=None,
                    offset=offset,
                    sample=sample,
                    seed=seed,
                    run_id=run_id,
                    num_workers=1,
                    theorem_name=None,
                    plain=True,
                    basin_seeds=basin_seeds,
                    goal_sig_scheme="ast",
                    run_analysis=False,
                    trace_mcts=False,
                    mcts_mode=mode,
                    distributed_settings=ds,
                    provider_label=None,
                    mode="capability_sweep",
                    mode_defaults={
                        "budget": budget,
                        "limit": None,
                        "corpus": corpus_ref,
                        "wild_only": True,
                    },
                    cli_args={
                        "corpus_ref": corpus_ref,
                        "sweep_root": str(sweep_root_path),
                        "provider": provider,
                        "mcts_mode": mode,
                        "basin_seeds": basin_seeds,
                        "budget": budget,
                        "offset": offset,
                        "sample": sample,
                        "seed": seed,
                        "resume": resume,
                    },
                    deepseek_num_samples=deepseek_num_samples,
                    bfs_num_samples=bfs_num_samples,
                    internlm_num_samples=internlm_num_samples,
                    resume=resume,
                    write_latest_run=False,
                )
            )
            runs.append(run_dir)

    per_item: dict[str, dict[str, Any]] = {}
    config_summaries: dict[str, dict[str, Any]] = {}
    selection: dict[str, Any] | None = None
    for run_dir in runs:
        run_config_path = run_dir / "run_config.json"
        run_status_path = run_dir / "run_status.json"
        if not run_config_path.exists():
            raise FileNotFoundError(f"Missing run_config.json: {run_config_path}")
        if not run_status_path.exists():
            raise FileNotFoundError(f"Missing run_status.json: {run_status_path}")
        run_cfg = json.loads(run_config_path.read_text(encoding="utf-8"))
        run_status = json.loads(run_status_path.read_text(encoding="utf-8"))
        if not isinstance(run_cfg, dict) or not isinstance(run_status, dict):
            raise ValueError(f"Invalid run_config/run_status in {run_dir}")
        if run_status.get("status") != "completed":
            status = run_status.get("status")
            raise RuntimeError(f"Capability run not completed: {run_dir} (status={status})")
        if run_status.get("partial_results") and not allow_partial:
            raise RuntimeError(
                f"Capability run has partial results: {run_dir} "
                "(set --allow-partial to reduce anyway)"
            )
        provider = str(run_cfg.get("provider") or "")
        mcts_mode = str(run_cfg.get("mcts_mode") or "centralized")
        config_key = f"{provider}:{mcts_mode}"
        config_summaries[config_key] = {
            "provider": provider,
            "mcts_mode": mcts_mode,
            "run_dir": str(run_dir),
            "budget_tiers": run_cfg.get("budget_tiers"),
            "basin_seeds": run_cfg.get("basin_seeds"),
        }
        sel = run_cfg.get("theorem_selection")
        if isinstance(sel, dict):
            if selection is None:
                selection = sel
            else:
                if (
                    selection.get("method") != sel.get("method")
                    or selection.get("seed") != sel.get("seed")
                    or selection.get("sample") != sel.get("sample")
                    or selection.get("offset") != sel.get("offset")
                    or selection.get("selected_count") != sel.get("selected_count")
                ):
                    raise RuntimeError(
                        "Selection mismatch across matrix runs; expected all points to use the "
                        "same theorem_selection"
                    )

        theorem_dirs = [d for d in run_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
        for theorem_dir in sorted(theorem_dirs):
            basin_path = theorem_dir / "basin_analysis.json"
            if not basin_path.exists():
                if allow_partial:
                    continue
                raise FileNotFoundError(f"Missing basin_analysis.json: {basin_path}")
            data = json.loads(basin_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"Invalid basin_analysis.json: {basin_path}")
            item_id = str(data.get("theorem_name") or theorem_dir.name)
            solve_rate = float(data.get("solve_rate") or 0.0)
            unique_structures = int(data.get("unique_structures") or 0)
            dominant_freq = float(data.get("dominant_structure_frequency") or 0.0)
            seed_results_raw = data.get("seed_results")
            seed_results = seed_results_raw if isinstance(seed_results_raw, list) else []
            iters = []
            for r in seed_results:
                if not isinstance(r, dict):
                    continue
                if r.get("solved") is True and isinstance(r.get("iterations_to_solve"), int):
                    iters.append(int(r["iterations_to_solve"]))
            entry = {
                "solve_rate": solve_rate,
                "unique_structures": unique_structures,
                "dominant_structure_frequency": dominant_freq,
                "median_iterations_to_solve": _median_or_none(iters),
            }
            per_item.setdefault(item_id, {})[config_key] = entry

    # Use the run's explicit selection list as the source of truth for item_id ordering, so
    # capability sweeps can run on deterministic samples/shards without requiring basin outputs
    # for the full corpus.
    item_ids = None
    if isinstance(selection, dict):
        selected = selection.get("selected_theorems")
        if isinstance(selected, list) and all(isinstance(x, str) and x for x in selected):
            item_ids = list(selected)
    if item_ids is None:
        items_path = items_build_dir / str(manifest.get("items_file") or "items.jsonl")
        item_ids = [
            row["item_id"] for row in iter_jsonl(items_path) if isinstance(row.get("item_id"), str)
        ]
    missing = [i for i in item_ids if i not in per_item]
    if missing and not allow_partial:
        raise RuntimeError(
            f"Capability reduction missing {len(missing)} item(s); first={missing[0]}"
        )

    capability_rows: list[dict[str, Any]] = []
    reachable_ids: set[str] = set()
    for item_id in item_ids:
        configs = per_item.get(item_id, {})
        best_key = None
        best_solve = -1.0
        best_median = float("inf")
        for key, stats in configs.items():
            sr = float(stats.get("solve_rate") or 0.0)
            med = stats.get("median_iterations_to_solve")
            med_v = float(med) if isinstance(med, (int, float)) else float("inf")
            if sr > best_solve or (sr == best_solve and med_v < best_median):
                best_key = key
                best_solve = sr
                best_median = med_v
        reachable = any(
            float(s.get("solve_rate") or 0.0) >= reachable_threshold for s in configs.values()
        )
        if reachable:
            reachable_ids.add(item_id)
        capability_rows.append(
            {
                "item_id": item_id,
                "reachable": reachable,
                "reachable_threshold": reachable_threshold,
                "best_config": best_key,
                "per_config": configs,
            }
        )

    capability_path = items_build_dir / "capability.jsonl"
    write_jsonl(capability_path, capability_rows)

    total = len(item_ids)
    reachable_count = len(reachable_ids)
    reachable_rate = (reachable_count / total) if total else 0.0
    if reachable_rate < min_feasible_rate and not allow_low_feasible:
        raise RuntimeError(
            f"Feasible fraction too low for {corpus_ref}: {reachable_rate:.1%} "
            f"({reachable_count}/{total}); set --allow-low-feasible to override."
        )

    derived_feasible_dir = _derive_feasible_slice(
        output_build_dir=base_build_dir,
        items_build_dir=items_build_dir,
        backend="lean",
        corpus_id=corpus_id,
        parent_build_id=parent_build_id,
        parent_manifest=manifest,
        capability_path=capability_path,
        reachable_ids=reachable_ids,
        reachable_threshold=reachable_threshold,
    )

    sweep_index = {
        "corpus_ref": corpus_ref,
        "build_dir": str(items_build_dir),
        "sweep_root": str(sweep_root_path),
        "runs": [str(p) for p in runs],
        "theorem_selection": selection,
        "selection_sha256": hashlib.sha256(
            ("\n".join(item_ids) + "\n").encode("utf-8", errors="strict")
        ).hexdigest(),
        "configs": config_summaries,
        "capability_path": str(capability_path),
        "derived_feasible_dir": str(derived_feasible_dir),
        "reachable_threshold": reachable_threshold,
        "reachable_count": reachable_count,
        "total_count": total,
        "reachable_rate": reachable_rate,
    }
    write_json_atomic(sweep_root_path / "sweep_index.json", sweep_index)

    return CapabilitySweepResult(
        corpus_ref=corpus_ref,
        build_dir=items_build_dir,
        sweep_root=sweep_root_path,
        runs=runs,
        capability_path=capability_path,
        derived_feasible_dir=derived_feasible_dir,
        reachable_count=reachable_count,
        total_count=total,
        reachable_rate=reachable_rate,
    )
