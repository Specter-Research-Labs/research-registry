from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from prover.proof import ProofGraph


def normalize_rule(rule: str) -> str:
    return " ".join(rule.strip().split())


@dataclass
class ProofObjectNode:
    node_id: str
    goal_sig: str
    goal_type: str = ""
    depth: int = 0
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_attrs(self) -> dict[str, Any]:
        return {
            "goal_type": self.goal_type,
            "depth": self.depth,
            "goal_sig": self.goal_sig,
            "node_kind": self.attrs.get("node_kind", "proof_step"),
            **self.attrs,
        }


@dataclass
class ProofObjectEdge:
    source: str
    target: str
    rule: str
    order: int | None = None
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_attrs(self) -> dict[str, Any]:
        data = {
            "tactic": self.rule,
            "tactic_norm": normalize_rule(self.rule),
            "edge_role": self.attrs.get("edge_role", normalize_rule(self.rule)),
            "action_kind": self.attrs.get("action_kind", "proof_rule"),
            **self.attrs,
        }
        if self.order is not None:
            data["order"] = self.order
        return data


@dataclass
class ProofObjectGraph:
    nodes: list[ProofObjectNode] = field(default_factory=list)
    edges: list[ProofObjectEdge] = field(default_factory=list)

    def to_proof_graph(self) -> ProofGraph:
        graph = ProofGraph.for_external_proof(backend="unknown", provenance="proof_object")
        for node in self.nodes:
            graph.add_node(node.node_id, **node.to_attrs())

        max_order = 0
        for edge in self.edges:
            if edge.source not in graph.graph:
                raise ValueError(f"Missing source node: {edge.source}")
            if edge.target not in graph.graph:
                raise ValueError(f"Missing target node: {edge.target}")
            graph.graph.add_edge(edge.source, edge.target, **edge.to_attrs())
            if edge.order is not None:
                max_order = max(max_order, edge.order)

        graph.expansion_count = max(graph.expansion_count, max_order)
        return graph
