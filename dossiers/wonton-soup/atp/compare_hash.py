from __future__ import annotations

import networkx as nx

from prover.proof import ProofGraph
from prover.providers.base import tactic_family


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

