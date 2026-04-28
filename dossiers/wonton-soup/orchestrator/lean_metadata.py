from __future__ import annotations

import inspect
import json
import math
import os
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from experiments.distributed_mcts import (
    DistributedBlockPolicy,
    DistributedDelayPolicy,
    DistributedMCTSConfig,
    DistributedReroutePolicy,
)
from prover import FilteredTacticProvider, mcts_search
from prover.mcts import BackpropStrategy
from prover.providers import DeepSeekTacticProvider, ReProverTacticProvider, TacticProvider
from prover.providers.base import GoalAwareTacticProvider
from prover.providers.reprover_client import ReProverModel
from run_capabilities import build_lean_run_capabilities


def build_run_capabilities(
    results: list[Any],
    *,
    has_goal_cache: bool,
    has_mcts_trace: bool,
) -> dict[str, bool]:
    return build_lean_run_capabilities(
        results,
        has_goal_cache=has_goal_cache,
        has_mcts_trace=has_mcts_trace,
    )


def _enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def mcts_defaults() -> dict[str, Any]:
    signature = inspect.signature(mcts_search)
    defaults: dict[str, Any] = {}
    for key in ("max_iterations", "c", "backprop_strategy"):
        param = signature.parameters.get(key)
        if param is not None:
            defaults[key] = _enum_value(param.default)
    return defaults


def _distributed_defaults() -> tuple[float, BackpropStrategy]:
    defaults = mcts_defaults()
    c_value = defaults.get("c", math.sqrt(2))
    try:
        c = float(c_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid MCTS default for c: {c_value}") from exc
    backprop_value = defaults.get("backprop_strategy", BackpropStrategy.UNIFORM)
    if isinstance(backprop_value, BackpropStrategy):
        backprop = backprop_value
    else:
        backprop = BackpropStrategy(backprop_value)
    return c, backprop


def distributed_settings_snapshot(
    settings: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if settings is None:
        return None
    return dict(settings)


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def guidance_snapshot(cli_args: dict[str, Any] | None) -> dict[str, Any] | None:
    if cli_args is None:
        return None
    ranker = cli_args.get("tactic_ranker")
    model_path = cli_args.get("tactic_ranker_model")
    alpha = cli_args.get("tactic_ranker_alpha")
    if not isinstance(ranker, str) or ranker in {"", "none"}:
        return None
    snapshot: dict[str, Any] = {"tactic_ranker": ranker, "tactic_ranker_alpha": alpha}
    if isinstance(model_path, str) and model_path.strip():
        model = Path(model_path)
        snapshot["tactic_ranker_model_name"] = model.name
        snapshot["tactic_ranker_model_sha256"] = _sha256_file(model) if model.exists() else None
    else:
        snapshot["tactic_ranker_model_name"] = None
        snapshot["tactic_ranker_model_sha256"] = None
    return snapshot


def build_distributed_config(
    settings: dict[str, Any],
    budget: int,
) -> DistributedMCTSConfig:
    c, backprop = _distributed_defaults()
    block_policy = None
    if settings.get("block_fraction") is not None:
        block_policy = DistributedBlockPolicy(
            fraction=settings["block_fraction"],
            duration=settings["block_duration"],
            seed=settings["block_seed"],
            immovable_fraction=settings.get("block_immovable_fraction"),
            unfreeze_after=settings.get("block_unfreeze_after"),
            unfreeze_prob=settings.get("block_unfreeze_prob"),
        )
    reroute_policy = None
    if settings.get("reroute_max_attempts") is not None:
        reroute_policy = DistributedReroutePolicy(max_attempts=settings["reroute_max_attempts"])
    delay_policy = None
    if settings.get("delay_probability") is not None:
        delay_policy = DistributedDelayPolicy(
            probability=settings["delay_probability"],
            duration=settings["delay_duration"],
            seed=settings["delay_seed"],
        )
    return DistributedMCTSConfig(
        agents=settings["agents"],
        max_iterations=budget,
        max_inflight_expansions=settings["inflight"],
        c=c,
        backprop_strategy=backprop,
        virtual_loss=settings.get("virtual_loss", 0),
        adapter_mode="single",
        block_policy=block_policy,
        reroute_policy=reroute_policy,
        delay_policy=delay_policy,
        depth_bias=settings.get("depth_bias", 0.0),
        path_bias=settings.get("path_bias", 0.0),
        history_cache=settings.get("history_cache", False),
        deterministic_inference=settings.get("deterministic_inference", False),
    )


def _peg_rule_config(rule: Any) -> dict[str, Any]:
    return {
        "peg_id": rule.peg_id,
        "kind": rule.kind.value,
        "blocked_tactics": sorted(rule.blocked_tactics),
        "blocked_families": sorted(rule.blocked_families),
        "condition": rule.condition,
    }


def provider_config(provider: TacticProvider) -> dict[str, Any]:
    config: dict[str, Any] = {
        "class": provider.__class__.__name__,
        "describe": provider.describe(),
    }

    if isinstance(provider, FilteredTacticProvider):
        config.update(
            {
                "provider": "filtered",
                "blocked_tactics": sorted(provider.blocked),
                "blocked_families": sorted(provider.blocked_families),
                "peg_rules": [_peg_rule_config(rule) for rule in provider.peg_rules],
                "peg_budget": (
                    {
                        "peg_id": provider.peg_budget.peg_id,
                        "max_total_attempts": provider.peg_budget.max_total_attempts,
                        "max_family_attempts": provider.peg_budget.max_family_attempts,
                    }
                    if provider.peg_budget is not None
                    else None
                ),
                "provider_id": provider.provider_id,
                "goal_sig_scheme": provider.goal_sig_config.scheme,
                "base": provider_config(provider.base),
            }
        )
        return config

    if isinstance(provider, ReProverTacticProvider):
        config.update(
            {
                "provider": "reprover",
                "device": provider.model.device,
                "cache_size": provider._cache_size,
                "use_sampling": provider._use_sampling,
                "temperature": provider._temperature,
                "top_p": provider._top_p,
                "num_runs": provider._num_runs,
                "use_retrieval": provider.retriever is not None,
                "model_id": ReProverModel.MODEL_ID,
                "max_input_length": ReProverModel.DEFAULT_MAX_INPUT_LENGTH,
                "max_length": ReProverModel.DEFAULT_MAX_LENGTH,
                "beam_limit": ReProverModel.DEFAULT_BEAM_LIMIT,
            }
        )
        return config

    if isinstance(provider, DeepSeekTacticProvider):
        config.update(
            {
                "provider": "deepseek",
                "model_path": provider._model_path,
                "cache_size": provider._cache_size,
                "num_samples": provider._num_samples,
                "model_id": provider.MODEL_ID,
                "max_input_length": provider.MAX_INPUT_LENGTH,
                "max_new_tokens": provider.MAX_NEW_TOKENS,
                "stop_sequences": provider.STOP_SEQUENCES,
                "system_prompt": provider.SYSTEM_PROMPT,
                "backend": "mlx",
            }
        )
        return config

    if isinstance(provider, GoalAwareTacticProvider):
        include_slow = any(tactic in provider.base_tactics for tactic in provider.SLOW_TACTICS)
        config.update(
            {
                "provider": "heuristic",
                "include_slow": include_slow,
                "base_tactics": list(provider.base_tactics),
            }
        )
        return config

    config["provider"] = "unknown"
    return config


def build_resolved_config(
    *,
    corpus: str,
    corpus_spec: str,
    budget_label: str | None,
    budget_tiers: list[int],
    limit: int | None,
    offset: int,
    sample: int | None,
    selection_seed: int | None,
    search_seed: int | None,
    wild_only: bool,
    trace_mcts: bool,
    analysis: bool,
    device: str | None,
    workers: int,
    goal_sig_scheme: str,
    allow_easy: bool,
    sampling: bool,
    theorem: str | None,
    debug: bool,
    plain: bool,
    basin_seeds: int | None,
    basin_blind: bool,
    project_path: str,
    mcts_mode: str,
    distributed_mcts: dict[str, Any] | None,
    solution_artifacts: bool | None = None,
    corpus_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = {
        "corpus": corpus,
        "corpus_spec": corpus_spec,
        "budget_label": budget_label,
        "budget_tiers": budget_tiers,
        "budget_total": sum(budget_tiers),
        "limit": limit,
        "offset": offset,
        "sample": sample,
        "selection_seed": selection_seed,
        "seed": selection_seed,
        "search_seed": search_seed,
        "wild_only": wild_only,
        "trace_mcts": trace_mcts,
        "analysis": analysis,
        "device": device,
        "workers": workers,
        "goal_sig_scheme": goal_sig_scheme,
        "allow_easy": allow_easy,
        "sampling": sampling,
        "theorem": theorem,
        "debug": debug,
        "plain": plain,
        "basin_seeds": basin_seeds,
        "basin_blind": basin_blind,
        "project_path": project_path,
        "mcts_mode": mcts_mode,
        "distributed_mcts": distributed_mcts,
    }
    if solution_artifacts is not None:
        resolved["solution_artifacts"] = solution_artifacts
    if corpus_artifact is not None:
        resolved["corpus_artifact"] = corpus_artifact
    return resolved


def build_theorem_selection(
    *,
    method: str,
    limit: int | None,
    offset: int,
    sample: int | None,
    selection_seed: int | None,
    selected_theorems: list[str],
    error: str | None,
) -> dict[str, Any]:
    return {
        "method": method,
        "limit": limit,
        "offset": offset,
        "sample": sample,
        "selection_seed": selection_seed,
        "seed": selection_seed,
        "selected_count": len(selected_theorems),
        "selected_theorems": selected_theorems,
        "error": error,
    }


def build_mcts_metadata(
    *,
    mcts_mode: str,
    distributed_mcts: dict[str, Any] | None,
    budget_tiers: list[int],
    trace_mcts: bool,
    goal_sig_scheme: str,
) -> dict[str, Any]:
    return {
        "defaults": mcts_defaults(),
        "mode": mcts_mode,
        "distributed": distributed_mcts,
        "budget_tiers": budget_tiers,
        "budget_total": sum(budget_tiers),
        "warmstart_between_tiers": True,
        "trace_mcts": trace_mcts,
        "trace_context_fields": ["tier", "budget"],
        "goal_sig_scheme": goal_sig_scheme,
    }


def build_intervention_metadata(
    *,
    wild_only: bool,
    block_easy: bool,
    blocked_tactics: list[str],
    requested_names: list[str],
    extra: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "wild_only": wild_only,
        "block_easy": block_easy,
        "blocked_tactics": blocked_tactics,
        "requested_names": requested_names,
        "extra": extra,
    }


def build_runtime_metadata(*, include_executable: bool, include_uv_python: bool) -> dict[str, Any]:
    runtime = {
        "python": sys.version.split(" ")[0],
        "platform": sys.platform,
        "pid": os.getpid(),
    }
    if include_executable:
        runtime["python_executable"] = sys.executable
    if include_uv_python:
        runtime["uv_python"] = os.environ.get("UV_PYTHON")
    return runtime


def _build_problem_space_metadata(
    *,
    goal_sig_scheme: str,
    blocked_tactics: list[str],
    budget_tiers: list[int],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "P": {
            "S": {
                "repr": "goal_sig",
                "goal_id_scheme": "checkpoint",
                "goal_sig_scheme": goal_sig_scheme,
            },
            "O": {
                "repr": "tactic_candidate",
                "normalize": "normalize_tactic",
                "family": "tactic_family",
            },
            "C": {
                "interventions": {
                    "blocked_tactics": blocked_tactics,
                },
                "invalid_move": "preview_tactic_failure",
                "budget": {
                    "tiers": budget_tiers,
                    "total": sum(budget_tiers),
                },
            },
            "E": {
                "goal": "proof_complete",
            },
            "H": {
                "budget_tiers": budget_tiers,
                "budget_total": sum(budget_tiers),
            },
        },
        "K": {
            "tau_agent": "detour_metrics.total_attempts",
            "w_unit": "tactic_attempt",
            "null_models": [
                "blind_uniform_candidate",
                "blind_uniform_family",
            ],
            "primary": {
                "metric": "any_success",
                "null_model": "blind_uniform_candidate",
            },
            "requires": {
                "goal_cache": True,
                "trace_mcts_for_candidate": True,
            },
        },
    }


def _build_shared_run_config(
    *,
    resolved_run_id: str,
    logs_dir: Path,
    log_dir: Path,
    mode: str | None,
    corpus_label: str,
    corpus_spec: str,
    budget_label: str | None,
    budget_tiers: list[int],
    limit: int | None,
    offset: int,
    sample: int | None,
    selection_seed: int | None,
    search_seed: int | None,
    wild_only: bool,
    trace_mcts: bool,
    run_analysis: bool,
    device: str | None,
    num_workers: int,
    goal_sig_scheme: str,
    cli_args: dict[str, Any] | None,
    allow_easy: bool,
    use_sampling: bool,
    theorem_name: str | None,
    debug: bool,
    plain: bool,
    basin_seeds: int | None,
    basin_blind: bool,
    mode_defaults: dict[str, Any] | None,
    project_path: str,
    corpus_artifact_ref: dict[str, Any] | None,
    corpus_meta: dict[str, Any],
    mcts_mode: str,
    distributed_snapshot: dict[str, Any] | None,
    selection_method: str,
    selected_theorems: list[str],
    selection_error: str | None,
    blocked_tactics: list[str],
    requested_interventions: list[str],
    extra_intervention_payloads: list[dict[str, Any]],
    providers_meta: dict[str, Any],
    runtime_include_executable: bool,
    runtime_include_uv_python: bool,
    solution_artifacts: bool | None = None,
    include_corpus_artifact_key: bool = False,
    include_problem_space: bool = False,
) -> dict[str, Any]:
    config = {
        "format_version": 2,
        "run_id": resolved_run_id,
        "log_dir": str(log_dir.relative_to(logs_dir)),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "corpus": corpus_label,
        "corpus_spec": corpus_spec,
        "budget_label": budget_label,
        "budget_tiers": budget_tiers,
        "limit": limit,
        "offset": offset,
        "sample": sample,
        "selection_seed": selection_seed,
        "seed": selection_seed,
        "search_seed": search_seed,
        "wild_only": wild_only,
        "trace_mcts": trace_mcts,
        "analysis": run_analysis,
        "device": device,
        "workers": num_workers,
        "goal_sig_scheme": goal_sig_scheme,
        "guidance": guidance_snapshot(cli_args),
        "allow_easy": allow_easy,
        "sampling": use_sampling,
        "theorem": theorem_name,
        "debug": debug,
        "plain": plain,
        "basin_seeds": basin_seeds,
        "basin_blind": basin_blind,
        "mode_defaults": mode_defaults or {},
        "cli_args": cli_args or {},
        "mcts_mode": mcts_mode,
        "distributed_mcts": distributed_snapshot,
        "resolved": build_resolved_config(
            corpus=corpus_label,
            corpus_spec=corpus_spec,
            budget_label=budget_label,
            budget_tiers=budget_tiers,
            limit=limit,
            offset=offset,
            sample=sample,
            selection_seed=selection_seed,
            search_seed=search_seed,
            wild_only=wild_only,
            trace_mcts=trace_mcts,
            analysis=run_analysis,
            device=device,
            workers=num_workers,
            goal_sig_scheme=goal_sig_scheme,
            allow_easy=allow_easy,
            sampling=use_sampling,
            theorem=theorem_name,
            debug=debug,
            plain=plain,
            basin_seeds=basin_seeds,
            basin_blind=basin_blind,
            project_path=project_path,
            mcts_mode=mcts_mode,
            distributed_mcts=distributed_snapshot,
            solution_artifacts=solution_artifacts,
            corpus_artifact=corpus_artifact_ref,
        ),
        "corpus_meta": corpus_meta,
        "theorem_selection": build_theorem_selection(
            method=selection_method,
            limit=limit,
            offset=offset,
            sample=sample,
            selection_seed=selection_seed,
            selected_theorems=selected_theorems,
            error=selection_error,
        ),
        "providers_meta": providers_meta,
        "mcts": build_mcts_metadata(
            mcts_mode=mcts_mode,
            distributed_mcts=distributed_snapshot,
            budget_tiers=budget_tiers,
            trace_mcts=trace_mcts,
            goal_sig_scheme=goal_sig_scheme,
        ),
        "interventions": build_intervention_metadata(
            wild_only=wild_only,
            block_easy=not allow_easy,
            blocked_tactics=blocked_tactics,
            requested_names=requested_interventions,
            extra=extra_intervention_payloads,
        ),
        "runtime": build_runtime_metadata(
            include_executable=runtime_include_executable,
            include_uv_python=runtime_include_uv_python,
        ),
    }
    if include_corpus_artifact_key or corpus_artifact_ref is not None:
        config["corpus_artifact"] = corpus_artifact_ref
    if solution_artifacts is not None:
        config["solution_artifacts"] = solution_artifacts
        config["artifacts"] = {
            "solution_artifacts": solution_artifacts,
        }
    if include_problem_space:
        config["problem_space"] = _build_problem_space_metadata(
            goal_sig_scheme=goal_sig_scheme,
            blocked_tactics=blocked_tactics,
            budget_tiers=budget_tiers,
        )
    return config


def build_run_config(
    *,
    resolved_run_id: str,
    logs_dir: Path,
    log_dir: Path,
    provider_name: str,
    provider_label: str,
    provider: TacticProvider,
    mode: str | None,
    corpus_label: str,
    corpus_spec: str,
    budget_label: str | None,
    budget_tiers: list[int],
    limit: int | None,
    offset: int,
    sample: int | None,
    selection_seed: int | None,
    search_seed: int | None,
    skip_interventions: bool,
    trace_mcts: bool,
    collect_solution_artifacts: bool,
    run_analysis: bool,
    device: str | None,
    num_workers: int,
    goal_sig_scheme: str,
    cli_args: dict[str, Any] | None,
    block_easy: bool,
    use_sampling: bool,
    theorem_name: str | None,
    debug: bool,
    plain: bool,
    basin_seeds: int | None,
    basin_blind: bool,
    mode_defaults: dict[str, Any] | None,
    project_path: str,
    corpus_artifact_ref: dict[str, Any] | None,
    corpus_meta: dict[str, Any],
    mcts_mode: str,
    distributed_snapshot: dict[str, Any] | None,
    selection_method: str,
    selected_theorems: list[str],
    selection_error: str | None,
    blocked_tactics: list[str],
    requested_interventions: list[str],
    extra_intervention_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    provider_desc = provider.describe()
    config = _build_shared_run_config(
        resolved_run_id=resolved_run_id,
        logs_dir=logs_dir,
        log_dir=log_dir,
        mode=mode,
        corpus_label=corpus_label,
        corpus_spec=corpus_spec,
        budget_label=budget_label,
        budget_tiers=budget_tiers,
        limit=limit,
        offset=offset,
        sample=sample,
        selection_seed=selection_seed,
        search_seed=search_seed,
        wild_only=skip_interventions,
        trace_mcts=trace_mcts,
        run_analysis=run_analysis,
        device=device,
        num_workers=num_workers,
        goal_sig_scheme=goal_sig_scheme,
        cli_args=cli_args,
        allow_easy=not block_easy,
        use_sampling=use_sampling,
        theorem_name=theorem_name,
        debug=debug,
        plain=plain,
        basin_seeds=basin_seeds,
        basin_blind=basin_blind,
        mode_defaults=mode_defaults,
        project_path=project_path,
        corpus_artifact_ref=corpus_artifact_ref,
        corpus_meta=corpus_meta,
        mcts_mode=mcts_mode,
        distributed_snapshot=distributed_snapshot,
        selection_method=selection_method,
        selected_theorems=selected_theorems,
        selection_error=selection_error,
        blocked_tactics=blocked_tactics,
        requested_interventions=requested_interventions,
        extra_intervention_payloads=extra_intervention_payloads,
        providers_meta={
            "names": [provider_name],
            "primary": provider_name,
            "label": provider_label,
            "description": provider_desc,
            "config": provider_config(provider),
        },
        runtime_include_executable=True,
        runtime_include_uv_python=True,
        solution_artifacts=collect_solution_artifacts,
        include_corpus_artifact_key=True,
        include_problem_space=True,
    )
    config.update(
        {
            "providers": [provider_name],
            "provider": provider_name,
            "provider_label": provider_label,
            "provider_desc": provider_desc,
            "backend": "lean",
        }
    )
    return config


def build_multi_provider_run_config(
    *,
    resolved_run_id: str,
    logs_dir: Path,
    log_dir: Path,
    providers: list[str],
    mode: str | None,
    corpus_label: str,
    corpus_spec: str,
    budget_label: str | None,
    budget_tiers: list[int],
    limit: int | None,
    offset: int,
    sample: int | None,
    selection_seed: int | None,
    search_seed: int | None,
    wild_only: bool,
    trace_mcts: bool,
    run_analysis: bool,
    device: str | None,
    num_workers: int,
    goal_sig_scheme: str,
    cli_args: dict[str, Any] | None,
    allow_easy: bool,
    use_sampling: bool,
    theorem_name: str | None,
    debug: bool,
    plain: bool,
    basin_seeds: int | None,
    basin_blind: bool,
    mode_defaults: dict[str, Any] | None,
    project_path: str,
    corpus_artifact_ref: dict[str, Any] | None,
    corpus_meta: dict[str, Any],
    mcts_mode: str,
    distributed_snapshot: dict[str, Any] | None,
    selection_method: str,
    selected_theorems: list[str],
    selection_error: str | None,
    blocked_tactics: list[str],
    requested_interventions: list[str],
    extra_intervention_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    config = _build_shared_run_config(
        resolved_run_id=resolved_run_id,
        logs_dir=logs_dir,
        log_dir=log_dir,
        mode=mode,
        corpus_label=corpus_label,
        corpus_spec=corpus_spec,
        budget_label=budget_label,
        budget_tiers=budget_tiers,
        limit=limit,
        offset=offset,
        sample=sample,
        selection_seed=selection_seed,
        search_seed=search_seed,
        wild_only=wild_only,
        trace_mcts=trace_mcts,
        run_analysis=run_analysis,
        device=device,
        num_workers=num_workers,
        goal_sig_scheme=goal_sig_scheme,
        cli_args=cli_args,
        allow_easy=allow_easy,
        use_sampling=use_sampling,
        theorem_name=theorem_name,
        debug=debug,
        plain=plain,
        basin_seeds=basin_seeds,
        basin_blind=basin_blind,
        mode_defaults=mode_defaults,
        project_path=project_path,
        corpus_artifact_ref=corpus_artifact_ref,
        corpus_meta=corpus_meta,
        mcts_mode=mcts_mode,
        distributed_snapshot=distributed_snapshot,
        selection_method=selection_method,
        selected_theorems=selected_theorems,
        selection_error=selection_error,
        blocked_tactics=blocked_tactics,
        requested_interventions=requested_interventions,
        extra_intervention_payloads=extra_intervention_payloads,
        providers_meta={
            "names": providers,
            "multi_provider": True,
        },
        runtime_include_executable=False,
        runtime_include_uv_python=False,
    )
    config.update(
        {
            "providers": providers,
            "provider": None,
            "multi_provider": True,
        }
    )
    return config


def write_run_config(log_dir: Path, config: dict[str, Any]) -> None:
    tmp_path = log_dir / "run_config.json.tmp"
    with open(tmp_path, "w") as handle:
        json.dump(config, handle, indent=2)
    tmp_path.replace(log_dir / "run_config.json")
    if not (log_dir / "run_config.json").exists():
        raise RuntimeError(f"run_config.json missing after write in {log_dir}")


def load_existing_run_config(log_dir: Path) -> dict[str, Any] | None:
    path = log_dir / "run_config.json"
    if not path.exists():
        return None
    with open(path) as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None
