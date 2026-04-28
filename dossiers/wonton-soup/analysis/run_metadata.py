from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from .logs import read_json_auto


class RunSnapshot(NamedTuple):
    config: dict[str, Any] | None
    status: dict[str, Any] | None
    aggregates: dict[str, Any] | None
    theorem_count: int | None


def load_json_mapping(path: Path) -> dict[str, Any]:
    data = read_json_auto(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return data


def load_optional_json_mapping(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json_mapping(path)


def load_run_config(run_dir: Path) -> dict[str, Any] | None:
    return load_optional_json_mapping(run_dir / "run_config.json")


def load_run_status(run_dir: Path) -> dict[str, Any] | None:
    return load_optional_json_mapping(run_dir / "run_status.json")


def load_summary_aggregates(run_dir: Path) -> dict[str, Any] | None:
    summary_path = run_dir / "summary.json.gz"
    if not summary_path.exists():
        return None
    summary = load_json_mapping(summary_path)
    aggregates = summary.get("aggregates")
    if not isinstance(aggregates, dict):
        return None
    return aggregates


def load_run_snapshot(
    run_dir: Path,
    *,
    include_run_config: bool = True,
    include_summary_aggregates: bool = True,
) -> RunSnapshot:
    run_config = load_run_config(run_dir) if include_run_config else None
    return RunSnapshot(
        config=run_config,
        status=load_run_status(run_dir),
        aggregates=load_summary_aggregates(run_dir) if include_summary_aggregates else None,
        theorem_count=selected_theorem_count(run_config) if run_config else None,
    )


def selected_theorem_count(run_config: Mapping[str, Any]) -> int | None:
    selection = run_config.get("theorem_selection")
    if not isinstance(selection, dict):
        return None
    selected_count = selection.get("selected_count")
    if isinstance(selected_count, int):
        return selected_count
    selected_theorems = selection.get("selected_theorems")
    if isinstance(selected_theorems, list):
        return sum(1 for theorem in selected_theorems if isinstance(theorem, str))
    return None


def providers_from_config(run_config: Mapping[str, Any]) -> list[str]:
    providers = run_config.get("providers")
    if isinstance(providers, list) and providers:
        return [provider for provider in providers if isinstance(provider, str)]

    meta = run_config.get("providers_meta", {})
    if isinstance(meta, dict):
        names = meta.get("names")
        if isinstance(names, list) and names:
            return [provider for provider in names if isinstance(provider, str)]

    provider = run_config.get("provider")
    if isinstance(provider, str):
        return [provider]
    return []


def settings_summary(run_config: Mapping[str, Any]) -> str | None:
    parts: list[str] = []

    tiers = run_config.get("budget_tiers")
    if isinstance(tiers, list) and tiers:
        tier_values = [str(tier) for tier in tiers if isinstance(tier, (int, float, str))]
        if tier_values:
            parts.append(f"tiers {','.join(tier_values)}")

    workers = run_config.get("workers")
    if isinstance(workers, int):
        parts.append(f"wk {workers}")

    mcts_mode = run_config.get("mcts_mode")
    if isinstance(mcts_mode, str) and mcts_mode:
        parts.append(f"mcts {mcts_mode}")

    timeout = run_config.get("timeout_sec")
    if isinstance(timeout, (int, float)):
        parts.append(f"timeout {timeout:g}s")

    extra_args = run_config.get("extra_args")
    if isinstance(extra_args, list) and extra_args:
        parts.append("args " + " ".join(str(arg) for arg in extra_args[:3]))

    return " | ".join(parts) if parts else None


def status_tag_from_run_status(run_status: Mapping[str, Any] | None) -> str | None:
    if not run_status:
        return None
    status = run_status.get("status")
    partial = run_status.get("partial_results", False)
    if isinstance(status, str) and status and status != "completed":
        return status.upper()
    if partial is True:
        return "PARTIAL"
    return None


def _provider_label(run_config: Mapping[str, Any], *, style: str) -> str | None:
    if style == "meta":
        provider_label = run_config.get("provider_label")
        if isinstance(provider_label, str) and provider_label:
            return provider_label
        providers_meta = run_config.get("providers_meta", {})
        if isinstance(providers_meta, dict):
            label = providers_meta.get("label")
            if isinstance(label, str) and label:
                return label

    providers = providers_from_config(run_config)
    if len(providers) == 1:
        return providers[0]
    if len(providers) > 1:
        return f"{len(providers)} providers"
    if style == "viz":
        return None

    provider_label = run_config.get("provider_label")
    if isinstance(provider_label, str) and provider_label:
        return provider_label

    provider = run_config.get("provider")
    if isinstance(provider, str) and provider:
        return provider
    return None


def _tiers_label(
    run_config: Mapping[str, Any], *, default: str | None = None
) -> str | None:
    tiers = run_config.get("budget_tiers")
    if isinstance(tiers, list) and tiers:
        tier_values = [str(tier) for tier in tiers if isinstance(tier, (int, float, str))]
        if tier_values:
            return ",".join(tier_values)
    return default


def build_run_label(
    run_name: str,
    run_config: Mapping[str, Any] | None,
    run_status: Mapping[str, Any] | None,
    *,
    theorem_count: int | None = None,
    style: str = "dashboard",
    extra_parts: Sequence[str] | None = None,
) -> str:
    parts = [run_name]
    if run_config:
        if style == "viz":
            mode = run_config.get("mode") or "run"
            corpus = run_config.get("corpus") or "corpus"
            parts.append(str(mode))
            parts.append(str(corpus))
            if theorem_count is not None:
                parts.append(f"{theorem_count} thm")
            parts.append(f"tiers {_tiers_label(run_config, default='-')}")
            provider_label = _provider_label(run_config, style="viz")
            if provider_label:
                parts.append(provider_label)
        elif style == "dashboard":
            provider_label = _provider_label(run_config, style="dashboard")
            if provider_label:
                parts.append(provider_label)
            corpus = run_config.get("corpus")
            if isinstance(corpus, str) and corpus:
                parts.append(corpus)
            tiers_label = _tiers_label(run_config)
            if tiers_label:
                parts.append(f"tiers {tiers_label}")
            if theorem_count is not None:
                parts.append(f"{theorem_count} thm")
        else:
            raise ValueError(f"Unknown run label style: {style}")
    elif theorem_count is not None:
        parts.append(f"{theorem_count} thm")
    if extra_parts:
        parts.extend(part for part in extra_parts if part)
    status_tag = status_tag_from_run_status(run_status)
    if status_tag:
        parts.append(status_tag)
    return " | ".join(parts)


def build_run_meta(
    summary_aggregates: Mapping[str, Any] | None,
    run_config: Mapping[str, Any] | None,
    run_status: Mapping[str, Any] | None,
    *,
    theorem_count: int | None = None,
) -> dict[str, Any] | None:
    meta: dict[str, Any] = {}

    if summary_aggregates is not None:
        theorem_total = summary_aggregates.get("theorem_count")
        if isinstance(theorem_total, int):
            meta["theorem_count"] = theorem_total
        crashed_count = summary_aggregates.get("crashed_count")
        if isinstance(crashed_count, int):
            meta["crashed_count"] = crashed_count
        wild_rate = summary_aggregates.get("wild_type_solve_rate")
        if isinstance(wild_rate, (int, float)):
            meta["wild_type_solve_rate"] = float(wild_rate)
        intervention_rate = summary_aggregates.get("intervention_solve_rate")
        if isinstance(intervention_rate, (int, float)):
            meta["intervention_solve_rate"] = float(intervention_rate)

    if theorem_count is not None:
        meta["theorem_count"] = theorem_count

    if run_config:
        created_at = run_config.get("created_at")
        if isinstance(created_at, str):
            meta["created_at"] = created_at
        mode = run_config.get("mode")
        if isinstance(mode, str):
            meta["mode"] = mode
        corpus = run_config.get("corpus")
        if isinstance(corpus, str):
            meta["corpus"] = corpus
        budget_label = run_config.get("budget_label")
        if isinstance(budget_label, str):
            meta["budget_label"] = budget_label

        providers = providers_from_config(run_config)
        if providers:
            meta["providers"] = providers

        provider_label = _provider_label(run_config, style="meta")
        if provider_label:
            meta["provider_label"] = provider_label

        summary = settings_summary(run_config)
        if summary:
            meta["settings_summary"] = summary

    if run_status:
        status = run_status.get("status")
        if isinstance(status, str):
            meta["status"] = status
        partial = run_status.get("partial_results")
        if isinstance(partial, bool):
            meta["partial_results"] = partial
        goal_id_scheme = run_status.get("goal_id_scheme")
        if isinstance(goal_id_scheme, str):
            meta["goal_id_scheme"] = goal_id_scheme
        capabilities = run_status.get("capabilities")
        if isinstance(capabilities, dict):
            meta["capabilities"] = capabilities

    return meta or None
