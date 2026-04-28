from __future__ import annotations

import hashlib

import networkx as nx

from atp.tptp.parser import canonicalize_tptp_formula
from prover.proof import ProofGraph
from prover.providers.base import tactic_family


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def hash_goal_sig(graph: ProofGraph) -> str:
    canonical = graph.to_canonical()
    for node in canonical.nodes:
        if canonical.nodes[node].get("goal_sig") is None:
            canonical.nodes[node]["goal_sig"] = ""
    for _, _, data in canonical.edges(data=True):
        tactic_norm = data.get("tactic_norm", "")
        data["tactic_family"] = tactic_family(tactic_norm) if tactic_norm else ""
    return nx.weisfeiler_lehman_graph_hash(
        canonical,
        node_attr="goal_sig",
        edge_attr="tactic_family",
    )[:16]


def hash_shape(graph: ProofGraph) -> str:
    canonical = graph.to_canonical()
    return nx.weisfeiler_lehman_graph_hash(canonical)[:16]


def hash_clause(graph: ProofGraph) -> str:
    canonical = graph.to_canonical()
    for node in canonical.nodes:
        formula = canonical.nodes[node].get("goal_type", "")
        canon = canonicalize_tptp_formula(formula) if formula else ""
        canonical.nodes[node]["goal_sig"] = _hash_text(canon)
    return nx.weisfeiler_lehman_graph_hash(canonical, node_attr="goal_sig")[:16]


def hash_deps(graph: ProofGraph) -> str:
    g = graph.graph
    node_sig: dict[str, str] = {}
    for node, data in g.nodes(data=True):
        formula = data.get("goal_type", "")
        canon = canonicalize_tptp_formula(formula) if formula else ""
        node_sig[node] = _hash_text(canon)

    base_roles = {
        "axiom",
        "hypothesis",
        "negated_conjecture",
        "conjecture",
        "lemma",
        "theorem",
        "definition",
    }
    base_nodes = [
        n
        for n, data in g.nodes(data=True)
        if g.in_degree(n) == 0 or data.get("role") in base_roles
    ]
    base_sig = {n: node_sig[n] for n in base_nodes}
    memo: dict[str, frozenset[str]] = {}

    def deps(n: str) -> frozenset[str]:
        if n in memo:
            return memo[n]
        parents = list(g.predecessors(n))
        if not parents:
            memo[n] = frozenset({base_sig.get(n, node_sig[n])})
            return memo[n]
        collected: set[str] = set()
        for parent in parents:
            collected.update(deps(parent))
        memo[n] = frozenset(collected)
        return memo[n]

    dep_sets = ["|".join(sorted(deps(n))) for n in g.nodes]
    dep_sets.sort()
    return _hash_text("||".join(dep_sets))
