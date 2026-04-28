from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, NoReturn, cast

from corpus.lean.theorems import Intervention
from orchestrator import lean as runtime
from orchestrator import lean_inputs, lean_metadata
from orchestrator import lean_reporting as _lean_reporting
from orchestrator.lean_options import (
    LEAN_PARSER_PREFIX_OPTION_NAMES,
    LEAN_PARSER_SUFFIX_OPTION_NAMES,
    MODE_DEFAULTS,
    ModeDefaults,
    add_argparse_options,
    parse_budget,
    parse_provider_list,
    validate_providers,
)
from prover.providers.base import normalize_tactic


def _error(message: str, parser_error: Callable[[str], NoReturn] | None) -> NoReturn:
    if parser_error is not None:
        parser_error(message)
    raise SystemExit(message)


def _is_explicit_cli_value(value: Any) -> bool:
    return value is not None and value is not False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run proof search experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  dev       5 theorems, wild-only, quick budget, MCTS tracing on
  research  40 curated theorems, interventions on, MCTS tracing on, standard budget

Budget presets:
  quick     10,50 (60 total)
  standard  10,50,200,1000 (1260 total)
  deep      10,50,200,1000,3000 (4260 total)

Providers:
  reprover, deepseek, bfs, internlm, heuristic

Multi-provider runs:
  --all-providers or --providers reprover,deepseek
  -p can also take a comma list or 'all'
  Sequential by default; logs go under logs/<run_id>/provider=<name>

Examples:
  uv run python wonton.py lean              # dev mode
  uv run python wonton.py lean -m research  # research mode
  uv run python wonton.py lean -m research -b deep --all-providers  # multi-provider
""",
    )
    add_argparse_options(parser, LEAN_PARSER_PREFIX_OPTION_NAMES)
    intervention_group = parser.add_mutually_exclusive_group()
    intervention_group.add_argument(
        "--wild-only",
        action="store_true",
        dest="wild_only",
        default=None,
        help="Skip intervention runs (dev default)",
    )
    intervention_group.add_argument(
        "--with-interventions",
        action="store_false",
        dest="wild_only",
        help="Run intervention comparisons (research default)",
    )
    trace_group = parser.add_mutually_exclusive_group()
    trace_group.add_argument(
        "--trace-mcts",
        action="store_true",
        dest="trace_mcts",
        default=None,
        help="Write per-iteration MCTS trace JSONL (research default)",
    )
    trace_group.add_argument(
        "--no-trace-mcts",
        action="store_false",
        dest="trace_mcts",
        help="Disable MCTS tracing",
    )
    add_argparse_options(parser, LEAN_PARSER_SUFFIX_OPTION_NAMES)
    return parser


def run_from_args(args: Any, *, parser_error: Callable[[str], NoReturn] | None = None) -> None:
    project_path = cast(str | None, args.lean_project) or os.environ.get("LEAN_PROJECT_PATH")
    if project_path is None:
        print("ERROR: LEAN_PROJECT_PATH not set")
        print("Run: export LEAN_PROJECT_PATH=./lean_project")
        raise SystemExit(1)
    project_path = str(runtime._assert_lean_project_ready(project_path))

    mode = cast(str, args.mode)
    mode_defaults = cast(ModeDefaults, MODE_DEFAULTS[mode])
    budget_value = cast(str | None, args.budget)
    budget = budget_value if budget_value is not None else mode_defaults["budget"]
    limit_value = cast(int | None, args.limit)
    limit = limit_value if limit_value is not None else mode_defaults["limit"]
    sample = cast(int | None, args.sample)
    seed = cast(int | None, args.seed)
    if sample is not None:
        if seed is None:
            _error("--seed is required when --sample is set", parser_error)
        if limit_value is not None:
            _error("Use --sample or --limit, not both", parser_error)
        limit = None
    search_seed = cast(int | None, args.search_seed)
    if search_seed is not None and search_seed < 0:
        _error("--search-seed must be >= 0", parser_error)
    wild_only_value = cast(bool | None, args.wild_only)
    wild_only = wild_only_value if wild_only_value is not None else mode_defaults["wild_only"]
    corpus_value = cast(str | None, args.corpus)
    corpus = corpus_value if corpus_value is not None else mode_defaults["corpus"]
    trace_mcts_value = cast(bool | None, args.trace_mcts)
    trace_mcts = trace_mcts_value if trace_mcts_value is not None else mode_defaults["trace_mcts"]
    mcts_mode = cast(str, args.mcts_mode)
    distributed_settings: dict[str, Any] | None = None
    if mcts_mode == "distributed":
        if args.mcts_agents is None or args.mcts_inflight is None:
            _error(
                "--mcts-agents and --mcts-inflight are required for distributed MCTS",
                parser_error,
            )
        block_fraction = args.mcts_block_fraction
        block_duration = args.mcts_block_duration
        block_seed = args.mcts_block_seed
        block_immovable_fraction = args.mcts_block_immovable_fraction
        block_unfreeze_after = args.mcts_unfreeze_after
        block_unfreeze_prob = args.mcts_unfreeze_prob
        reroute_blocked = bool(args.mcts_reroute_blocked)
        reroute_max = args.mcts_reroute_max
        delay_prob = args.mcts_delay_prob
        delay_duration = args.mcts_delay_duration
        delay_seed = args.mcts_delay_seed
        virtual_loss = args.mcts_virtual_loss
        depth_bias = args.mcts_depth_bias
        path_bias = args.mcts_path_bias
        history_cache = bool(args.mcts_history_cache)
        deterministic_inference = bool(args.mcts_deterministic_inference)
        if block_fraction is None:
            if block_duration is not None or block_seed is not None:
                _error("--mcts-block-* options require --mcts-block-fraction", parser_error)
            if block_immovable_fraction is not None:
                _error(
                    "--mcts-block-immovable-fraction requires --mcts-block-fraction",
                    parser_error,
                )
            if block_unfreeze_after is not None or block_unfreeze_prob is not None:
                _error("--mcts-unfreeze-* options require --mcts-block-fraction", parser_error)
        else:
            if not (0.0 < block_fraction < 1.0):
                _error(
                    "--mcts-block-fraction must be between 0 and 1 (exclusive)",
                    parser_error,
                )
            if block_duration is None:
                _error(
                    "--mcts-block-duration is required when --mcts-block-fraction is set",
                    parser_error,
                )
            if block_duration == 0:
                _error("--mcts-block-duration must be non-zero", parser_error)
            if block_seed is None:
                _error(
                    "--mcts-block-seed is required when --mcts-block-fraction is set",
                    parser_error,
                )
            if block_immovable_fraction is not None:
                if not (0.0 <= block_immovable_fraction <= 1.0):
                    _error(
                        "--mcts-block-immovable-fraction must be between 0 and 1",
                        parser_error,
                    )
                if block_duration < 0:
                    _error(
                        "--mcts-block-immovable-fraction requires a positive --mcts-block-duration",
                        parser_error,
                    )
            if block_unfreeze_after is not None and block_unfreeze_after < 1:
                _error("--mcts-unfreeze-after must be >= 1", parser_error)
            if block_unfreeze_prob is not None and not (0.0 < block_unfreeze_prob <= 1.0):
                _error("--mcts-unfreeze-prob must be in (0, 1]", parser_error)
        if reroute_blocked and reroute_max is None:
            _error(
                "--mcts-reroute-max is required when --mcts-reroute-blocked is set",
                parser_error,
            )
        if reroute_max is not None and not reroute_blocked:
            _error("--mcts-reroute-max requires --mcts-reroute-blocked", parser_error)
        if reroute_max is not None and reroute_max < 1:
            _error("--mcts-reroute-max must be >= 1", parser_error)
        if any(value is not None for value in (delay_prob, delay_duration, delay_seed)):
            if delay_prob is None or delay_duration is None or delay_seed is None:
                _error(
                    (
                        "--mcts-delay-prob, --mcts-delay-duration, and "
                        "--mcts-delay-seed must be set together"
                    ),
                    parser_error,
                )
            if not (0.0 < delay_prob < 1.0):
                _error("--mcts-delay-prob must be between 0 and 1 (exclusive)", parser_error)
            if delay_duration < 1:
                _error("--mcts-delay-duration must be >= 1", parser_error)
            if delay_seed < 0:
                _error("--mcts-delay-seed must be >= 0", parser_error)
        validated_values: list[int | float] = []
        for flag, value, default in (
            ("mcts-virtual-loss", virtual_loss, 0),
            ("mcts-depth-bias", depth_bias, 0.0),
            ("mcts-path-bias", path_bias, 0.0),
        ):
            if value is None:
                validated_values.append(default)
            elif value < 0:
                _error(f"--{flag} must be >= 0", parser_error)
            else:
                validated_values.append(value)
        virtual_loss_value, depth_bias_value, path_bias_value = validated_values
        distributed_settings = {
            "agents": args.mcts_agents,
            "inflight": args.mcts_inflight,
            "block_fraction": block_fraction,
            "block_duration": block_duration,
            "block_seed": block_seed,
            "block_immovable_fraction": block_immovable_fraction,
            "block_unfreeze_after": block_unfreeze_after,
            "block_unfreeze_prob": block_unfreeze_prob,
            "reroute_max_attempts": reroute_max if reroute_blocked else None,
            "delay_probability": delay_prob,
            "delay_duration": delay_duration,
            "delay_seed": delay_seed,
            "virtual_loss": virtual_loss_value,
            "depth_bias": depth_bias_value,
            "path_bias": path_bias_value,
            "history_cache": history_cache,
            "deterministic_inference": deterministic_inference,
        }
    else:
        if any(
            _is_explicit_cli_value(value)
            for value in (
                args.mcts_agents,
                args.mcts_inflight,
                args.mcts_block_fraction,
                args.mcts_block_duration,
                args.mcts_block_seed,
                args.mcts_block_immovable_fraction,
                args.mcts_unfreeze_after,
                args.mcts_unfreeze_prob,
                args.mcts_reroute_blocked,
                args.mcts_reroute_max,
                args.mcts_delay_prob,
                args.mcts_delay_duration,
                args.mcts_delay_seed,
                args.mcts_virtual_loss,
                args.mcts_depth_bias,
                args.mcts_path_bias,
                args.mcts_history_cache,
                args.mcts_deterministic_inference,
            )
        ):
            _error("distributed options require --mcts-mode distributed", parser_error)

    basin_seeds = cast(int | None, args.basin_seeds)
    basin_blind = bool(args.basin_blind)
    if basin_blind and basin_seeds is None:
        _error("--basin-blind requires --basin-seeds", parser_error)
    if basin_blind and mcts_mode != "centralized":
        _error("--basin-blind currently requires --mcts-mode centralized", parser_error)
    if basin_seeds is not None and search_seed is not None:
        _error("--search-seed is not supported with --basin-seeds", parser_error)
    intervention_names = cast(list[str] | None, args.intervention_name)
    extra_intervention_specs = cast(list[str] | None, args.extra_intervention)
    if basin_seeds is not None and (
        intervention_names is not None or extra_intervention_specs is not None
    ):
        _error(
            "--intervention-name and --extra-intervention are not supported with --basin-seeds",
            parser_error,
        )
    if wild_only and (intervention_names is not None or extra_intervention_specs is not None):
        _error("--intervention-name and --extra-intervention require interventions", parser_error)

    budget_tiers = parse_budget(budget)

    if args.all_providers and args.providers is not None:
        _error("Use --all-providers or --providers, not both", parser_error)

    if args.all_providers:
        providers = list(lean_inputs.PROVIDER_CHOICES)
    else:
        default_provider = cast(str, args.provider)
        raw = args.providers if args.providers is not None else default_provider
        providers = parse_provider_list(raw, choices=lean_inputs.PROVIDER_CHOICES)
        if not providers:
            providers = [default_provider]
    try:
        providers = validate_providers(providers, choices=lean_inputs.PROVIDER_CHOICES)
    except ValueError as exc:
        _error(str(exc), parser_error)
    if len(providers) > 1 and basin_seeds is not None:
        _error("Multi-provider runs do not support --basin-seeds", parser_error)

    extra_interventions: list[Intervention] = []
    if extra_intervention_specs is not None:
        for spec in extra_intervention_specs:
            name, sep, raw_blocked = spec.partition("=")
            if not sep:
                _error(
                    f"Invalid --extra-intervention spec {spec!r}; expected NAME=t1,t2",
                    parser_error,
                )
            name = name.strip()
            blocked = {normalize_tactic(item) for item in raw_blocked.split(",") if item.strip()}
            if not name or not blocked:
                _error(
                    f"Invalid --extra-intervention spec {spec!r}; expected NAME=t1,t2",
                    parser_error,
                )
            extra_interventions.append(Intervention(name=name, blocked=blocked))

    deepseek_num_samples = cast(int | None, args.deepseek_num_samples)
    bfs_num_samples = cast(int | None, args.bfs_num_samples)
    internlm_num_samples = cast(int | None, args.internlm_num_samples)
    for flag, value in (
        ("deepseek-samples", deepseek_num_samples),
        ("bfs-samples", bfs_num_samples),
        ("internlm-samples", internlm_num_samples),
    ):
        if value is not None and value < 1:
            _error(f"--{flag} must be >= 1", parser_error)
    deepseek_model_path = cast(str | None, args.deepseek_model_path)
    if deepseek_model_path is not None:
        model_path = Path(deepseek_model_path)
        if not model_path.exists():
            _error(f"DeepSeek model not found: {model_path}", parser_error)

    tactic_ranker = None
    tactic_ranker_name = cast(str, args.tactic_ranker)
    tactic_ranker_model = cast(str | None, args.tactic_ranker_model)
    tactic_ranker_alpha = cast(float, args.tactic_ranker_alpha)
    if tactic_ranker_name != "none":
        if tactic_ranker_model is None:
            _error("--tactic-ranker-model is required when --tactic-ranker is set", parser_error)
        if not (0.0 <= tactic_ranker_alpha <= 1.0):
            _error("--tactic-ranker-alpha must be in [0,1]", parser_error)
        model_path = Path(tactic_ranker_model)
        if not model_path.exists():
            _error(f"Ranker model not found: {model_path}", parser_error)
        if tactic_ranker_name == "family_prior":
            from prover.rankers import FamilyPriorModel, family_prior_ranker

            model = FamilyPriorModel.load(model_path)
            tactic_ranker = family_prior_ranker(model, alpha=float(tactic_ranker_alpha))
        else:
            _error(f"Unknown tactic ranker: {tactic_ranker_name}", parser_error)

    cli_args = vars(args)
    goal_sig = cast(str, args.goal_sig)
    allow_easy = bool(args.allow_easy)
    run_id = cast(str | None, args.run_id)
    device = args.device
    use_sampling = bool(args.sampling)
    debug = bool(args.debug)
    plain = bool(args.plain)
    resume = bool(args.resume)
    run_analysis = bool(args.analysis)
    num_workers = cast(int, args.workers)
    no_sync = bool(args.no_sync)
    collect_solution_artifacts = not bool(args.no_solution_artifacts)
    common_run_kwargs: dict[str, Any] = {
        "project_path": project_path,
        "budget_tiers": budget_tiers,
        "budget_label": budget,
        "device": device,
        "use_sampling": use_sampling,
        "debug": debug,
        "skip_interventions": wild_only,
        "block_easy": not allow_easy,
        "corpus": corpus,
        "limit": limit,
        "offset": cast(int, args.offset),
        "sample": sample,
        "seed": seed,
        "search_seed": search_seed,
        "resume": resume,
        "num_workers": num_workers,
        "theorem_name": cast(str | None, args.theorem),
        "intervention_names": intervention_names,
        "extra_interventions": extra_interventions,
        "plain": plain,
        "basin_seeds": basin_seeds,
        "basin_blind": basin_blind,
        "goal_sig_scheme": goal_sig,
        "run_analysis": run_analysis,
        "trace_mcts": trace_mcts,
        "collect_solution_artifacts": collect_solution_artifacts,
        "mcts_mode": mcts_mode,
        "distributed_settings": distributed_settings,
        "mode": mode,
        "mode_defaults": cast(dict[str, Any], mode_defaults),
        "cli_args": cli_args,
        "tactic_ranker": tactic_ranker,
        "deepseek_num_samples": deepseek_num_samples,
        "deepseek_model_path": deepseek_model_path,
        "bfs_num_samples": bfs_num_samples,
        "internlm_num_samples": internlm_num_samples,
        "no_sync": no_sync,
    }
    if len(providers) == 1:
        asyncio.run(
            runtime.run_corpus(
                provider_name=providers[0],
                run_id=run_id,
                **common_run_kwargs,
            )
        )
        return

    if run_id:
        base_id = run_id
        if not base_id.startswith("corpus-"):
            base_id = runtime._prefix_run_id_with_ymd(base_id)
    else:
        base_id = f"corpus-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}"
    logs_dir = runtime.resolve_logs_dir()
    top_log_dir = logs_dir / base_id
    top_log_dir.mkdir(parents=True, exist_ok=True)

    theorem_source, corpus_meta, corpus_artifact = lean_inputs.load_corpus(corpus)
    corpus_label = cast(str, corpus_meta.get("name", corpus))
    theorem_name = cast(str | None, args.theorem)
    offset = cast(int, args.offset)
    selection_theorems, selection_error, selection_method, selection_seed = (
        runtime._select_theorems_for_run(
            theorem_source,
            theorem_name=theorem_name,
            corpus_label=corpus_label,
            logger=logging.getLogger(__name__),
            resume=resume,
            log_dir=top_log_dir,
            corpus=corpus,
            offset=offset,
            limit=limit,
            sample=sample,
            seed=seed,
        )
    )

    distributed_snapshot = lean_metadata.distributed_settings_snapshot(distributed_settings)
    blocked_tactics = sorted(lean_inputs.EASY_TACTICS) if not allow_easy else []
    extra_intervention_payloads = [
        {
            "name": intervention.name,
            "blocked": sorted(intervention.blocked),
            "is_control": intervention.is_control,
        }
        for intervention in extra_interventions
    ]
    run_config = lean_metadata.build_multi_provider_run_config(
        resolved_run_id=base_id,
        logs_dir=logs_dir,
        log_dir=top_log_dir,
        providers=providers,
        mode=mode,
        corpus_label=corpus_label,
        corpus_spec=corpus,
        budget_label=budget,
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
        goal_sig_scheme=goal_sig,
        cli_args=cli_args,
        allow_easy=allow_easy,
        use_sampling=use_sampling,
        theorem_name=theorem_name,
        debug=debug,
        plain=plain,
        basin_seeds=basin_seeds,
        basin_blind=basin_blind,
        mode_defaults=cast(dict[str, Any], mode_defaults),
        project_path=project_path,
        corpus_artifact_ref=corpus_artifact,
        corpus_meta=corpus_meta,
        mcts_mode=mcts_mode,
        distributed_snapshot=distributed_snapshot,
        selection_method=selection_method,
        selected_theorems=[theorem.name for theorem in selection_theorems],
        selection_error=selection_error,
        blocked_tactics=blocked_tactics,
        requested_interventions=list(intervention_names or []),
        extra_intervention_payloads=extra_intervention_payloads,
    )
    lean_metadata.write_run_config(top_log_dir, run_config)
    runtime._write_latest_run(top_log_dir, providers, None, True)

    print(f"Multi-provider run: {', '.join(providers)}")
    print(f"  corpus: {corpus} | budget: {runtime._format_budget_tiers(budget_tiers)}")
    print(
        f"  interventions: {'off' if wild_only else 'on'} | "
        f"trace: {'on' if trace_mcts else 'off'}"
    )
    print(f"  logs: {top_log_dir}")

    provider_rows: list[dict[str, Any]] = []
    total_providers = len(providers)
    for idx, provider in enumerate(providers, 1):
        label = f"{provider} ({idx}/{total_providers})"
        provider_run_id = f"{base_id}/provider={provider}"
        print(f"\n=== Provider {idx}/{total_providers}: {provider} ===")
        asyncio.run(
            runtime.run_corpus(
                provider_name=provider,
                provider_label=label,
                run_id=provider_run_id,
                **common_run_kwargs,
            )
        )

        provider_dir = top_log_dir / f"provider={provider}"
        summary = _lean_reporting._load_summary(provider_dir)
        stats = _lean_reporting._summarize_from_summary(summary)
        stats["provider"] = provider
        stats["report_path"] = str(provider_dir / "report.md")
        provider_rows.append(stats)
        runtime._cleanup_torch_memory()

    with open(top_log_dir / "providers_summary.json", "w") as handle:
        json.dump({"run_id": base_id, "providers": provider_rows}, handle, indent=2)

    providers_theorem_summary = _lean_reporting._build_providers_theorem_summary(
        top_log_dir,
        run_config,
        providers,
    )
    with open(top_log_dir / "providers_theorem_summary.json", "w") as handle:
        json.dump(providers_theorem_summary, handle, indent=2)

    multi_report = _lean_reporting._format_multi_provider_summary(
        base_id,
        provider_rows,
        top_log_dir,
    )
    with open(top_log_dir / "providers_report.md", "w") as handle:
        handle.write(multi_report)

    runtime._sync_run_dir_to_remote(
        local_log_dir=top_log_dir,
        logger=logging.getLogger(__name__),
        reason="multi-provider-completed",
    )
    print("\n" + multi_report)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    run_from_args(args, parser_error=parser.error)
