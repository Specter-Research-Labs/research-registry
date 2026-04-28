from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Callable, Iterable

from atp.compare_hash import hash_shape
from prover.proof import (
    GRAPH_FAMILY_EXTERNAL_PROOF,
    GRAPH_FAMILY_PROOF_TERM_DAG,
    GRAPH_FAMILY_SEARCH_TRACE,
    GRAPH_FAMILY_UNKNOWN,
    ProofGraph,
)
from prover.providers.base import normalize_tactic, tactic_family
from prover.tactic_ir import (
    ACTION_KIND_TERM_CONSTRUCTOR,
    EFFECT_BUILDS_TERM,
    GOAL_COUPLING_COUPLED,
    GOAL_COUPLING_INDEPENDENT,
    GOAL_COUPLING_NONE,
    TacticActionIR,
    default_effect_flags_for_role,
    explicit_effect_flags,
    normalize_action_kind,
    normalize_continuation_kind,
    normalize_goal_coupling,
    role_semantics,
)

TERM_EDGE_ROLES = frozenset({"fn", "arg", "binder_type", "body", "value"})
TERM_NODE_HINTS = frozenset({"app", "const", "lam", "bvar", "fvar", "forallE", "sort", "letE"})
TERM_BIND_NODE_HINTS = frozenset({"lam", "forallE", "letE"})
TERM_VALUE_NODE_HINTS = frozenset({"const", "bvar", "fvar", "sort"})
TERM_CONST_BRANCH_NAMES = frozenset({"Case"})
TERM_CONST_BIND_NAMES = frozenset({"Prod"})
TERM_CONST_REWRITE_NAMES = frozenset({"Cast", "DEFAULTcast"})


@dataclass(frozen=True)
class ProofGraphIR:
    graph_family: str
    node_count: int
    edge_count: int
    max_depth: int
    root_count: int
    leaf_ratio: float
    branching_ratio: float
    mean_branch_factor: float
    edge_role_profile: dict[str, float]
    action_kind_profile: dict[str, float]
    operator_profile: dict[str, float]
    motif_profile: dict[str, float]
    effect_profile: dict[str, float]
    continuation_profile: dict[str, float]
    coupling_profile: dict[str, float]
    shape_hash: str


@dataclass(frozen=True)
class RelativeGraphFeatures:
    node_rank: float = 0.5
    edge_rank: float = 0.5
    depth_rank: float = 0.5
    leaf_rank: float = 0.5
    branching_rank: float = 0.5


def _normalize_profile(counts: dict[str, int], total: int) -> dict[str, float]:
    if total <= 0:
        return {}
    return {key: value / total for key, value in sorted(counts.items())}


def _edge_label(edge_data: dict[str, object]) -> str:
    edge_role = edge_data.get("edge_role")
    if isinstance(edge_role, str) and edge_role.strip():
        return edge_role.strip()
    tactic_norm = edge_data.get("tactic_norm")
    if isinstance(tactic_norm, str) and tactic_norm.strip():
        return normalize_tactic(tactic_norm)
    tactic = edge_data.get("tactic")
    if isinstance(tactic, str) and tactic.strip():
        return normalize_tactic(tactic)
    return ""


def _edge_role(edge_data: dict[str, object]) -> str:
    label = _edge_label(edge_data)
    if label in TERM_EDGE_ROLES:
        return label
    if label.startswith("fam:"):
        return label
    if not label:
        return "fam:other"
    family = tactic_family(label)
    if family in TERM_EDGE_ROLES:
        return family
    if not family:
        return "fam:other"
    return f"fam:{family}"


def _legacy_infer_graph_family(
    graph: ProofGraph,
    *,
    edge_roles: list[str],
    backend_hint: str | None,
) -> str:
    g = graph.graph
    edge_count = g.number_of_edges()
    if edge_count <= 0:
        if backend_hint == "lean":
            return GRAPH_FAMILY_SEARCH_TRACE
        return GRAPH_FAMILY_UNKNOWN

    term_edge_count = sum(1 for role in edge_roles if role in TERM_EDGE_ROLES)
    term_edge_fraction = term_edge_count / edge_count

    order_edge_count = sum(
        1 for _, _, data in g.edges(data=True) if isinstance(data.get("order"), int)
    )
    order_edge_fraction = order_edge_count / edge_count

    node_types = [
        goal_type
        for _, node_data in g.nodes(data=True)
        if isinstance((goal_type := node_data.get("goal_type")), str) and goal_type
    ]
    term_node_hints = sum(1 for goal_type in node_types if goal_type in TERM_NODE_HINTS)
    term_node_fraction = (term_node_hints / len(node_types)) if node_types else 0.0

    if term_edge_fraction >= 0.65 and term_node_fraction >= 0.20:
        return GRAPH_FAMILY_PROOF_TERM_DAG
    if order_edge_fraction >= 0.20 and term_edge_fraction < 0.50:
        return GRAPH_FAMILY_SEARCH_TRACE
    if backend_hint == "lean":
        return GRAPH_FAMILY_SEARCH_TRACE
    if backend_hint == "coq" and term_edge_fraction >= 0.35:
        return GRAPH_FAMILY_PROOF_TERM_DAG
    if term_edge_fraction >= 0.85:
        return GRAPH_FAMILY_PROOF_TERM_DAG
    return GRAPH_FAMILY_UNKNOWN


def _node_kind(node_data: dict[str, object]) -> str:
    explicit = node_data.get("node_kind")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    goal_type = node_data.get("goal_type")
    if isinstance(goal_type, str) and goal_type.strip():
        return goal_type.strip()
    return "unknown"


def _term_graph_evidence(
    graph: ProofGraph,
    *,
    edge_roles: list[str],
) -> tuple[float, float, float]:
    g = graph.graph
    edge_count = g.number_of_edges()
    if edge_count <= 0:
        return 0.0, 0.0, 0.0
    term_edge_count = sum(1 for role in edge_roles if role in TERM_EDGE_ROLES)
    order_edge_count = sum(
        1 for _, _, data in g.edges(data=True) if isinstance(data.get("order"), int)
    )
    node_types = [_node_kind(node_data) for _, node_data in g.nodes(data=True)]
    term_node_hints = sum(1 for node_kind in node_types if node_kind in TERM_NODE_HINTS)
    term_edge_fraction = term_edge_count / edge_count
    order_edge_fraction = order_edge_count / edge_count
    term_node_fraction = (term_node_hints / len(node_types)) if node_types else 0.0
    return term_edge_fraction, term_node_fraction, order_edge_fraction


def _is_term_structural_graph(
    graph: ProofGraph,
    *,
    edge_roles: list[str],
    graph_family: str,
    backend_hint: str | None,
) -> bool:
    if graph_family == GRAPH_FAMILY_PROOF_TERM_DAG:
        return True
    term_edge_fraction, term_node_fraction, order_edge_fraction = _term_graph_evidence(
        graph,
        edge_roles=edge_roles,
    )
    if term_edge_fraction >= 0.65 and term_node_fraction >= 0.20:
        return True
    if order_edge_fraction > 0.0:
        return False
    if graph_family == GRAPH_FAMILY_EXTERNAL_PROOF and graph.graph_schema_version <= 0:
        if term_edge_fraction >= 0.55 and term_node_fraction >= 0.20:
            return True
        if backend_hint == "coq" and term_edge_fraction >= 0.35:
            return True
    return False


def _resolve_graph_family(
    graph: ProofGraph,
    *,
    edge_roles: list[str],
    backend_hint: str | None,
) -> str:
    graph_family = graph.graph_family
    if graph_family == GRAPH_FAMILY_UNKNOWN:
        inferred = _legacy_infer_graph_family(
            graph,
            edge_roles=edge_roles,
            backend_hint=backend_hint,
        )
        return inferred
    if _is_term_structural_graph(
        graph,
        edge_roles=edge_roles,
        graph_family=graph_family,
        backend_hint=backend_hint,
    ):
        return GRAPH_FAMILY_PROOF_TERM_DAG
    return graph_family


def _action_kind(edge_data: dict[str, object]) -> str:
    return normalize_action_kind(edge_data.get("action_kind"))


def _effect_flags_for_role(
    role: str,
    *,
    action_kind: str,
    edge_data: dict[str, object],
) -> frozenset[str]:
    return default_effect_flags_for_role(role, action_kind=action_kind) | explicit_effect_flags(
        edge_data.get("effect_flags")
    )


def _continuation_kind(edge_data: dict[str, object], *, action_kind: str, branch_arity: int) -> str:
    return normalize_continuation_kind(
        edge_data.get("continuation_kind"),
        action_kind=action_kind,
        branch_arity=branch_arity,
    )


def _goal_coupling(
    edge_batch: list[dict[str, object]],
    *,
    action_kind: str,
    branch_arity: int,
) -> str:
    saw_shared_count = False
    for edge_data in edge_batch:
        explicit = edge_data.get("goal_coupling")
        if isinstance(explicit, str) and explicit.strip():
            return normalize_goal_coupling(
                explicit,
                action_kind=action_kind,
                branch_arity=branch_arity,
            )
        explicit_bool = edge_data.get("has_goal_coupling")
        if isinstance(explicit_bool, bool):
            if explicit_bool:
                return GOAL_COUPLING_COUPLED
            if branch_arity > 1:
                return GOAL_COUPLING_INDEPENDENT
            return GOAL_COUPLING_NONE
        shared_count = edge_data.get("shared_mvar_count")
        if isinstance(shared_count, int):
            saw_shared_count = True
            if shared_count > 0:
                return GOAL_COUPLING_COUPLED
    if saw_shared_count and branch_arity > 1:
        return GOAL_COUPLING_INDEPENDENT
    return normalize_goal_coupling(
        None,
        action_kind=action_kind,
        branch_arity=branch_arity,
    )


def _action_from_role(
    role: str,
    *,
    edge_data: dict[str, object],
    action_kind: str,
    branch_arity: int,
    goal_coupling: str,
) -> TacticActionIR:
    semantics = role_semantics(role)
    return TacticActionIR(
        action_kind=action_kind,
        operator_kind=semantics.operator_kind,
        motif_kind=semantics.motif_kind,
        effect_flags=_effect_flags_for_role(role, action_kind=action_kind, edge_data=edge_data),
        branch_arity=branch_arity,
        continuation_kind=_continuation_kind(
            edge_data,
            action_kind=action_kind,
            branch_arity=branch_arity,
        ),
        goal_coupling=goal_coupling,
    )


def _branch_arity(edge_data: dict[str, object], *, fallback: int) -> int:
    raw = edge_data.get("branch_arity")
    if isinstance(raw, int) and raw >= 0:
        return raw
    return fallback


def _terminal_action_data(node_data: dict[str, object]) -> dict[str, object]:
    action_data: dict[str, object] = {
        "tactic": node_data.get("terminal_tactic"),
        "tactic_norm": node_data.get("terminal_tactic_norm"),
        "edge_role": node_data.get("terminal_edge_role"),
        "action_kind": node_data.get("terminal_action_kind", "tactic_step"),
        "branch_arity": node_data.get("terminal_branch_arity", 0),
        "expanded_child_count": node_data.get("terminal_expanded_child_count", 0),
    }
    for key, value in node_data.items():
        if not key.startswith("terminal_"):
            continue
        bare_key = key[len("terminal_") :]
        if bare_key in {
            "tactic",
            "tactic_norm",
            "edge_role",
            "action_kind",
            "branch_arity",
            "expanded_child_count",
        }:
            continue
        action_data[bare_key] = value
    return action_data


def _term_action_operator_and_motif(
    node_data: dict[str, object],
    roles: frozenset[str],
) -> tuple[str, str]:
    node_kind = _node_kind(node_data)
    const_name = node_data.get("const_name")
    if isinstance(const_name, str):
        if const_name in TERM_CONST_BRANCH_NAMES:
            semantics = role_semantics("fam:cases")
            return semantics.operator_kind, semantics.motif_kind
        if const_name in TERM_CONST_REWRITE_NAMES:
            semantics = role_semantics("fam:rewrite")
            return semantics.operator_kind, semantics.motif_kind
        if const_name in TERM_CONST_BIND_NAMES:
            semantics = role_semantics("binder_type")
            return semantics.operator_kind, semantics.motif_kind
    if node_kind == "app" or {"fn", "arg"} & roles:
        semantics = role_semantics("fn")
        return semantics.operator_kind, semantics.motif_kind
    if node_kind in TERM_BIND_NODE_HINTS or {"binder_type", "body", "value"} & roles:
        semantics = role_semantics("binder_type")
        return semantics.operator_kind, semantics.motif_kind
    if node_kind in TERM_VALUE_NODE_HINTS or not roles:
        semantics = role_semantics("value")
        return semantics.operator_kind, semantics.motif_kind
    exemplar = next(iter(sorted(roles)), "")
    semantics = role_semantics(exemplar)
    return semantics.operator_kind, semantics.motif_kind


def _term_action_effect_flags(
    node_data: dict[str, object],
    *,
    roles: frozenset[str],
    edge_batch: list[dict[str, object]],
) -> frozenset[str]:
    node_kind = _node_kind(node_data)
    const_name = node_data.get("const_name")
    flags = {EFFECT_BUILDS_TERM}
    if isinstance(const_name, str) and const_name in TERM_CONST_BRANCH_NAMES:
        flags.add("branches_goals")
        flags.add("opens_goals")
    elif isinstance(const_name, str) and const_name in TERM_CONST_BIND_NAMES:
        flags.add("opens_binder")
        flags.add("refines_term")
    elif isinstance(const_name, str) and const_name in TERM_CONST_REWRITE_NAMES:
        flags.add("rewrites_target")
        flags.add("refines_term")
    elif node_kind in TERM_BIND_NODE_HINTS or {"binder_type", "body"} & roles:
        flags.add("opens_binder")
        flags.add("refines_term")
    elif node_kind == "app" or {"fn", "arg"} & roles:
        flags.add("refines_term")
    for edge_data in edge_batch:
        flags.update(explicit_effect_flags(edge_data.get("effect_flags")))
    return frozenset(sorted(flags))


def _build_term_constructor_actions(graph: ProofGraph) -> list[TacticActionIR]:
    g = graph.graph
    actions: list[TacticActionIR] = []
    for node_id, node_data in sorted(g.nodes(data=True), key=lambda item: str(item[0])):
        outgoing = list(g.out_edges(node_id, data=True))
        roles = frozenset(_edge_role(edge_data) for _, _, edge_data in outgoing)
        operator_kind, motif_kind = _term_action_operator_and_motif(node_data, roles)
        branch_arity = len(outgoing)
        edge_batch = [edge_data for _, _, edge_data in outgoing]
        actions.append(
            TacticActionIR(
                action_kind=ACTION_KIND_TERM_CONSTRUCTOR,
                operator_kind=operator_kind,
                motif_kind=motif_kind,
                effect_flags=_term_action_effect_flags(
                    node_data,
                    roles=roles,
                    edge_batch=edge_batch,
                ),
                branch_arity=branch_arity,
                continuation_kind=normalize_continuation_kind(
                    None,
                    action_kind=ACTION_KIND_TERM_CONSTRUCTOR,
                    branch_arity=branch_arity,
                ),
                goal_coupling=normalize_goal_coupling(
                    None,
                    action_kind=ACTION_KIND_TERM_CONSTRUCTOR,
                    branch_arity=branch_arity,
                ),
            )
        )
    return actions


def build_tactic_action_ir(
    graph: ProofGraph,
    *,
    graph_family: str | None = None,
) -> list[TacticActionIR]:
    g = graph.graph
    resolved_graph_family = graph_family if graph_family is not None else graph.graph_family
    actions: list[TacticActionIR] = []

    if resolved_graph_family == GRAPH_FAMILY_SEARCH_TRACE:
        grouped_edges: dict[tuple[str, int | str], list[dict[str, object]]] = defaultdict(list)
        for source, target, edge_data in g.edges(data=True):
            order = edge_data.get("order")
            key: tuple[str, int | str]
            if isinstance(order, int):
                key = (source, order)
            else:
                key = (source, f"edge:{target}")
            grouped_edges[key].append(edge_data)
        for key in sorted(grouped_edges.keys(), key=lambda item: (item[0], str(item[1]))):
            edge_batch = grouped_edges[key]
            exemplar = edge_batch[0]
            role = _edge_role(exemplar)
            action_kind = _action_kind(exemplar)
            branch_arity = _branch_arity(exemplar, fallback=len(edge_batch))
            actions.append(
                _action_from_role(
                    role,
                    edge_data=exemplar,
                    action_kind=action_kind,
                    branch_arity=branch_arity,
                    goal_coupling=_goal_coupling(
                        edge_batch,
                        action_kind=action_kind,
                        branch_arity=branch_arity,
                    ),
                )
            )
        for _, node_data in sorted(g.nodes(data=True), key=lambda item: str(item[0])):
            tactic = node_data.get("terminal_tactic")
            if not isinstance(tactic, str) or not tactic.strip():
                continue
            edge_data = _terminal_action_data(node_data)
            actions.append(
                _action_from_role(
                    _edge_role(edge_data),
                    edge_data=edge_data,
                    action_kind=_action_kind(edge_data),
                    branch_arity=_branch_arity(edge_data, fallback=0),
                    goal_coupling=_goal_coupling(
                        [edge_data],
                        action_kind=_action_kind(edge_data),
                        branch_arity=_branch_arity(edge_data, fallback=0),
                    ),
                )
            )
        return actions

    edge_roles = [_edge_role(edge_data) for _, _, edge_data in g.edges(data=True)]
    if _is_term_structural_graph(
        graph,
        edge_roles=edge_roles,
        graph_family=resolved_graph_family,
        backend_hint=graph.graph_backend,
    ):
        return _build_term_constructor_actions(graph)

    for _, _, edge_data in sorted(
        g.edges(data=True),
        key=lambda item: (str(item[0]), str(item[1]), _edge_label(item[2])),
    ):
        role = _edge_role(edge_data)
        action_kind = _action_kind(edge_data)
        actions.append(
            _action_from_role(
                role,
                edge_data=edge_data,
                action_kind=action_kind,
                branch_arity=_branch_arity(edge_data, fallback=1),
                goal_coupling=GOAL_COUPLING_NONE,
            )
        )
    return actions


def build_proof_graph_ir(
    graph: ProofGraph,
    *,
    backend_hint: str | None = None,
) -> ProofGraphIR:
    g = graph.graph
    node_count = g.number_of_nodes()
    edge_count = g.number_of_edges()

    max_depth = 0
    for _, node_data in g.nodes(data=True):
        depth = node_data.get("depth")
        if isinstance(depth, int):
            max_depth = max(max_depth, depth)

    edge_roles: list[str] = []
    for _, _, edge_data in g.edges(data=True):
        edge_roles.append(_edge_role(edge_data))
    role_counts: dict[str, int] = {}
    for role in edge_roles:
        role_counts[role] = role_counts.get(role, 0) + 1
    edge_role_profile = _normalize_profile(role_counts, edge_count)
    root_count = sum(1 for node in g.nodes if g.in_degree(node) == 0)
    leaf_count = sum(1 for node in g.nodes if g.out_degree(node) == 0)
    branching_nodes = [node for node in g.nodes if g.out_degree(node) > 1]
    non_leaf_nodes = [node for node in g.nodes if g.out_degree(node) > 0]
    leaf_ratio = (leaf_count / node_count) if node_count > 0 else 0.0
    branching_ratio = (len(branching_nodes) / node_count) if node_count > 0 else 0.0
    if non_leaf_nodes:
        mean_branch_factor = (
            sum(g.out_degree(node) for node in non_leaf_nodes) / len(non_leaf_nodes)
        )
    else:
        mean_branch_factor = 0.0

    graph_family = _resolve_graph_family(
        graph,
        edge_roles=edge_roles,
        backend_hint=backend_hint,
    )
    action_items = build_tactic_action_ir(graph, graph_family=graph_family)
    action_count = len(action_items)
    action_kind_counts: dict[str, int] = {}
    operator_counts: dict[str, int] = {}
    motif_counts: dict[str, int] = {}
    effect_counts: dict[str, int] = {}
    continuation_counts: dict[str, int] = {}
    coupling_counts: dict[str, int] = {}
    for action in action_items:
        action_kind_counts[action.action_kind] = action_kind_counts.get(action.action_kind, 0) + 1
        operator_counts[action.operator_kind] = operator_counts.get(action.operator_kind, 0) + 1
        motif_counts[action.motif_kind] = motif_counts.get(action.motif_kind, 0) + 1
        continuation_counts[action.continuation_kind] = (
            continuation_counts.get(action.continuation_kind, 0) + 1
        )
        coupling_counts[action.goal_coupling] = coupling_counts.get(action.goal_coupling, 0) + 1
        for effect_flag in action.effect_flags:
            effect_counts[effect_flag] = effect_counts.get(effect_flag, 0) + 1
    return ProofGraphIR(
        graph_family=graph_family,
        node_count=node_count,
        edge_count=edge_count,
        max_depth=max_depth,
        root_count=root_count,
        leaf_ratio=leaf_ratio,
        branching_ratio=branching_ratio,
        mean_branch_factor=mean_branch_factor,
        edge_role_profile=edge_role_profile,
        action_kind_profile=_normalize_profile(action_kind_counts, action_count),
        operator_profile=_normalize_profile(operator_counts, action_count),
        motif_profile=_normalize_profile(motif_counts, action_count),
        effect_profile=_normalize_profile(effect_counts, action_count),
        continuation_profile=_normalize_profile(continuation_counts, action_count),
        coupling_profile=_normalize_profile(coupling_counts, action_count),
        shape_hash=hash_shape(graph),
    )


def _rank_normalized(values: list[float]) -> list[float]:
    n = len(values)
    if n <= 0:
        return []
    if n == 1:
        return [0.5]

    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * n
    cursor = 0
    while cursor < n:
        end = cursor + 1
        while end < n and indexed[end][1] == indexed[cursor][1]:
            end += 1
        avg_rank = ((cursor + end - 1) / 2.0) / (n - 1)
        for slot in range(cursor, end):
            original_idx = indexed[slot][0]
            ranks[original_idx] = avg_rank
        cursor = end
    return ranks


def _assign_rank(
    features: list[RelativeGraphFeatures],
    items: list[ProofGraphIR],
    indices: list[int],
    *,
    field_name: str,
    value_fn: Callable[[ProofGraphIR], float],
) -> None:
    values = [value_fn(items[idx]) for idx in indices]
    ranks = _rank_normalized(values)
    for pos, idx in enumerate(indices):
        features[idx] = replace(features[idx], **{field_name: ranks[pos]})


def apply_relative_ranks(ir_items: list[ProofGraphIR]) -> list[RelativeGraphFeatures]:
    if not ir_items:
        return []
    ranked = [RelativeGraphFeatures() for _ in ir_items]
    by_kind: dict[str, list[int]] = defaultdict(list)
    for idx, ir in enumerate(ir_items):
        by_kind[ir.graph_family].append(idx)

    for indices in by_kind.values():
        _assign_rank(
            ranked,
            ir_items,
            indices,
            field_name="node_rank",
            value_fn=lambda ir: math.log(ir.node_count + 1),
        )
        _assign_rank(
            ranked,
            ir_items,
            indices,
            field_name="edge_rank",
            value_fn=lambda ir: math.log(ir.edge_count + 1),
        )
        _assign_rank(
            ranked,
            ir_items,
            indices,
            field_name="depth_rank",
            value_fn=lambda ir: float(ir.max_depth),
        )
        _assign_rank(
            ranked,
            ir_items,
            indices,
            field_name="leaf_rank",
            value_fn=lambda ir: ir.leaf_ratio,
        )
        _assign_rank(
            ranked,
            ir_items,
            indices,
            field_name="branching_rank",
            value_fn=lambda ir: ir.branching_ratio,
        )
    return ranked


def graph_kind_distribution(ir_items: Iterable[ProofGraphIR]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ir in ir_items:
        counts[ir.graph_family] = counts.get(ir.graph_family, 0) + 1
    return {kind: counts[kind] for kind in sorted(counts.keys())}
