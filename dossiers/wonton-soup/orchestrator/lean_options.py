from __future__ import annotations

from typing import Any, TypedDict

import typer

BUDGET_PRESETS = {
    "quick": [10, 50],
    "standard": [10, 50, 200, 1000],
    "deep": [10, 50, 200, 1000, 3000],
}

MODE_DEFAULTS = {
    "dev": {
        "budget": "quick",
        "corpus": "easy",
        "limit": 5,
        "wild_only": True,
        "trace_mcts": True,
    },
    "research": {
        "budget": "standard",
        "corpus": "research",
        "limit": None,
        "wild_only": False,
        "trace_mcts": True,
    },
}


class ModeDefaults(TypedDict):
    budget: str
    corpus: str
    limit: int | None
    wild_only: bool
    trace_mcts: bool


LEAN_PARSER_PREFIX_OPTION_NAMES = (
    "mode",
    "corpus",
    "provider",
    "tactic_ranker",
    "tactic_ranker_model",
    "tactic_ranker_alpha",
    "providers",
    "all_providers",
    "budget",
    "limit",
    "theorem",
    "lean_project",
)

LEAN_SHARED_OPTION_NAMES = LEAN_PARSER_PREFIX_OPTION_NAMES + (
    "mcts_mode",
    "mcts_agents",
    "mcts_inflight",
    "mcts_block_fraction",
    "mcts_block_duration",
    "mcts_block_seed",
    "mcts_block_immovable_fraction",
    "mcts_unfreeze_after",
    "mcts_unfreeze_prob",
    "mcts_reroute_blocked",
    "mcts_reroute_max",
    "mcts_delay_prob",
    "mcts_delay_duration",
    "mcts_delay_seed",
    "mcts_virtual_loss",
    "mcts_depth_bias",
    "mcts_path_bias",
    "mcts_history_cache",
    "mcts_deterministic_inference",
    "allow_easy",
    "debug",
    "plain",
    "sampling",
    "deepseek_num_samples",
    "deepseek_model_path",
    "bfs_num_samples",
    "internlm_num_samples",
    "device",
    "workers",
    "offset",
    "sample",
    "seed",
    "search_seed",
    "goal_sig",
    "run_id",
    "resume",
    "analysis",
    "no_solution_artifacts",
    "intervention_name",
    "extra_intervention",
)

LEAN_PARSER_SUFFIX_OPTION_NAMES = tuple(
    name
    for name in (
        *LEAN_SHARED_OPTION_NAMES[12:],
        "basin_seeds",
        "basin_blind",
        "no_sync",
    )
)

_SHORT_FLAGS = {
    "mode": "-m",
    "corpus": "-c",
    "provider": "-p",
    "budget": "-b",
    "limit": "-n",
    "theorem": "-t",
}

_LONG_FLAG_OVERRIDES = {
    "deepseek_num_samples": "--deepseek-samples",
    "bfs_num_samples": "--bfs-samples",
    "internlm_num_samples": "--internlm-samples",
}

_DEFAULTS = {
    "mode": "dev",
    "provider": "reprover",
    "tactic_ranker": "none",
    "tactic_ranker_alpha": 1.0,
    "mcts_mode": "centralized",
    "workers": 1,
    "offset": 0,
    "goal_sig": "ast",
}

_HELP = {
    "mode": "Mode profile",
    "corpus": "Theorem corpus",
    "provider": "Tactic provider",
    "tactic_ranker": "Reorder tactic candidates using a learned ranker",
    "tactic_ranker_model": "Path to ranker model",
    "tactic_ranker_alpha": "Blend model score with provider score (alpha in [0,1])",
    "providers": "Provider list",
    "all_providers": "Run all providers sequentially",
    "budget": "Budget preset",
    "limit": "Max theorems",
    "theorem": "Theorem name",
    "lean_project": "Lean project path",
    "mcts_mode": "MCTS mode",
}

_CHOICES = {
    "mode": tuple(sorted(MODE_DEFAULTS)),
    "tactic_ranker": ("none", "family_prior"),
    "mcts_mode": ("centralized", "distributed"),
    "goal_sig": ("ast", "text"),
}

_INT_OPTIONS = {
    "mcts_agents",
    "mcts_inflight",
    "mcts_block_duration",
    "mcts_block_seed",
    "mcts_unfreeze_after",
    "mcts_reroute_max",
    "mcts_delay_duration",
    "mcts_delay_seed",
    "mcts_virtual_loss",
    "deepseek_num_samples",
    "bfs_num_samples",
    "internlm_num_samples",
    "workers",
    "offset",
    "sample",
    "seed",
    "search_seed",
    "basin_seeds",
}

_FLOAT_OPTIONS = {
    "tactic_ranker_alpha",
    "mcts_block_fraction",
    "mcts_block_immovable_fraction",
    "mcts_unfreeze_prob",
    "mcts_delay_prob",
    "mcts_depth_bias",
    "mcts_path_bias",
}

_FLAG_OPTIONS = {
    "all_providers",
    "mcts_reroute_blocked",
    "mcts_history_cache",
    "mcts_deterministic_inference",
    "allow_easy",
    "debug",
    "plain",
    "sampling",
    "resume",
    "basin_blind",
    "analysis",
    "no_solution_artifacts",
    "no_sync",
}

_APPEND_OPTIONS = {"intervention_name", "extra_intervention"}


def _option_flags(name: str) -> tuple[str, ...]:
    long_flag = _LONG_FLAG_OVERRIDES.get(name, f"--{name.replace('_', '-')}")
    short_flag = _SHORT_FLAGS.get(name)
    return (short_flag, long_flag) if short_flag is not None else (long_flag,)


def _option_default(name: str) -> Any:
    if name in _FLAG_OPTIONS:
        return False
    return _DEFAULTS.get(name)


def _option_type(name: str) -> Any | None:
    if name in _INT_OPTIONS:
        return int
    if name in _FLOAT_OPTIONS:
        return float
    return None


def _option_action(name: str) -> str | None:
    if name in _FLAG_OPTIONS:
        return "store_true"
    if name in _APPEND_OPTIONS:
        return "append"
    return None


def add_argparse_option(container: Any, name: str) -> None:
    kwargs: dict[str, Any] = {"default": _option_default(name), "dest": name}
    help_text = _HELP.get(name)
    option_type = _option_type(name)
    action = _option_action(name)
    choices = _CHOICES.get(name)
    if help_text is not None:
        kwargs["help"] = help_text
    if option_type is not None:
        kwargs["type"] = option_type
    if action is not None:
        kwargs["action"] = action
    if choices is not None:
        kwargs["choices"] = choices
    container.add_argument(*_option_flags(name), **kwargs)


def add_argparse_options(container: Any, names: tuple[str, ...]) -> None:
    for name in names:
        add_argparse_option(container, name)


def typer_option(name: str) -> Any:
    return typer.Option(_option_default(name), *_option_flags(name), help=_HELP.get(name))


def option_default(name: str) -> Any:
    return _option_default(name)


def parse_budget(value: str) -> list[int]:
    if value in BUDGET_PRESETS:
        return BUDGET_PRESETS[value]
    return [int(tier) for tier in value.split(",")]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def parse_provider_list(raw: str | None, *, choices: tuple[str, ...]) -> list[str]:
    if raw is None:
        return []
    value = raw.strip()
    if not value:
        return []
    if value == "all":
        return list(choices)
    parts = [part.strip() for part in value.split(",")]
    return _dedupe([part for part in parts if part])


def validate_providers(providers: list[str], *, choices: tuple[str, ...]) -> list[str]:
    invalid = [provider for provider in providers if provider not in choices]
    if invalid:
        raise ValueError(
            f"Unknown provider(s): {', '.join(invalid)}. "
            f"Valid providers: {', '.join(choices)}."
        )
    return providers
