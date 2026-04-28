from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analysis.cross_assistant_alignment import (
    GraphSignature,
    LexicalAblationConfig,
    NameObfuscationConfig,
    _load_signature_graph,
    _normalize_graph_source,
    load_run_signatures,
    pair_distance,
)
from analysis.logs import ProviderRun, iter_provider_runs
from analysis.proof_graph_ir import build_tactic_action_ir
from prover.tactic_ir import TacticActionIR


@dataclass(frozen=True)
class TheoremIRInspection:
    signature: GraphSignature
    actions: list[TacticActionIR]
    payload: dict[str, Any]


def _resolve_provider_run(run_dir: Path, provider: str | None) -> ProviderRun:
    provider_runs = iter_provider_runs(run_dir)
    if provider is None:
        if len(provider_runs) == 1:
            return provider_runs[0]
        available = [item.provider for item in provider_runs if item.provider]
        raise ValueError(
            "multiple provider runs found; pass --provider to disambiguate"
            f" ({', '.join(sorted(available))})"
        )
    for item in provider_runs:
        if item.provider == provider:
            return item
    raise ValueError(f"provider not found under {run_dir}: {provider}")


def _select_signature(
    signatures: list[GraphSignature],
    *,
    theorem: str,
    variant: str,
) -> GraphSignature:
    matches = [sig for sig in signatures if sig.theorem == theorem and sig.variant == variant]
    if not matches:
        raise ValueError(f"theorem/variant not found: {theorem} ({variant})")
    if len(matches) > 1:
        raise ValueError(f"theorem/variant is ambiguous: {theorem} ({variant})")
    return matches[0]


def inspect_theorem_ir(
    run_dir: Path,
    *,
    theorem: str,
    variant: str = "wild_type",
    provider: str | None = None,
    graph_source: str = "wild_type_graph",
    name_obfuscation: NameObfuscationConfig | None = None,
    lexical_ablation: LexicalAblationConfig | None = None,
) -> TheoremIRInspection:
    resolved = _resolve_provider_run(run_dir.resolve(), provider)
    normalized_graph_source = _normalize_graph_source(graph_source)
    signatures = load_run_signatures(
        resolved.run_dir,
        name_obfuscation=name_obfuscation,
        lexical_ablation=lexical_ablation,
        graph_source=normalized_graph_source,
        include_interventions=True,
    )
    signature = _select_signature(signatures, theorem=theorem, variant=variant)
    graph = _load_signature_graph(
        resolved.run_dir,
        theorem,
        graph_source=normalized_graph_source,
        variant=variant,
    )
    actions = build_tactic_action_ir(graph, graph_family=signature.proof_ir.graph_family)
    payload = {
        "run_dir": str(run_dir.resolve()),
        "resolved_run_dir": str(resolved.run_dir.resolve()),
        "provider": resolved.provider,
        "theorem": signature.theorem,
        "variant": signature.variant,
        "proof_id": signature.proof_id,
        "graph_source": normalized_graph_source,
        "solved": signature.solved,
        "graph": {
            "family": signature.graph_kind,
            "node_count": signature.node_count,
            "edge_count": signature.edge_count,
            "max_depth": signature.max_depth,
            "shape_hash": signature.shape_hash,
        },
        "relative_graph_features": {
            "node_rank": round(signature.relative_graph_features.node_rank, 6),
            "edge_rank": round(signature.relative_graph_features.edge_rank, 6),
            "depth_rank": round(signature.relative_graph_features.depth_rank, 6),
            "leaf_rank": round(signature.relative_graph_features.leaf_rank, 6),
            "branching_rank": round(signature.relative_graph_features.branching_rank, 6),
        },
        "lexical": {
            "token_count": len(signature.lexical_tokens),
            "tokens": sorted(signature.lexical_tokens),
            "connective_profile": signature.connective_profile,
            "has_statement_text": signature.has_statement_text,
        },
        "proof_ir": {
            "edge_role_profile": signature.proof_ir.edge_role_profile,
            "action_kind_profile": signature.proof_ir.action_kind_profile,
            "operator_profile": signature.proof_ir.operator_profile,
            "motif_profile": signature.proof_ir.motif_profile,
            "effect_profile": signature.proof_ir.effect_profile,
            "continuation_profile": signature.proof_ir.continuation_profile,
            "coupling_profile": signature.proof_ir.coupling_profile,
        },
        "actions": [
            {
                "index": idx + 1,
                "action_kind": action.action_kind,
                "operator_kind": action.operator_kind,
                "motif_kind": action.motif_kind,
                "branch_arity": action.branch_arity,
                "continuation_kind": action.continuation_kind,
                "goal_coupling": action.goal_coupling,
                "effect_flags": sorted(action.effect_flags),
            }
            for idx, action in enumerate(actions)
        ],
    }
    return TheoremIRInspection(signature=signature, actions=actions, payload=payload)


def inspect_theorem_ir_pair(
    run_a_dir: Path,
    *,
    theorem_a: str,
    variant_a: str = "wild_type",
    provider_a: str | None = None,
    graph_source_a: str = "wild_type_graph",
    run_b_dir: Path,
    theorem_b: str,
    variant_b: str = "wild_type",
    provider_b: str | None = None,
    graph_source_b: str = "wild_type_graph",
    name_obfuscation: NameObfuscationConfig | None = None,
    lexical_ablation: LexicalAblationConfig | None = None,
) -> dict[str, Any]:
    left = inspect_theorem_ir(
        run_a_dir,
        theorem=theorem_a,
        variant=variant_a,
        provider=provider_a,
        graph_source=graph_source_a,
        name_obfuscation=name_obfuscation,
        lexical_ablation=lexical_ablation,
    )
    right = inspect_theorem_ir(
        run_b_dir,
        theorem=theorem_b,
        variant=variant_b,
        provider=provider_b,
        graph_source=graph_source_b,
        name_obfuscation=name_obfuscation,
        lexical_ablation=lexical_ablation,
    )
    pair = pair_distance(left.signature, right.signature)
    return {
        "left": left.payload,
        "right": right.payload,
        "distance": {
            "total": round(pair.distance, 6),
            "graph": round(pair.graph_distance, 6),
            "lexical": round(pair.lexical_distance, 6),
            "connective": round(pair.connective_distance, 6),
            "lexical_overlap": round(pair.lexical_overlap, 6),
            "cross_kind": pair.cross_kind,
            "graph_kind_a": pair.graph_kind_a,
            "graph_kind_b": pair.graph_kind_b,
        },
    }
