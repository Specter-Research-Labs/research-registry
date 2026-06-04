from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from prover.providers.base import normalize_tactic, tactic_family

GRAPH_FAMILY_SEARCH_TRACE = "search_trace"
GRAPH_FAMILY_EXTERNAL_PROOF = "external_proof"
GRAPH_FAMILY_PROOF_TERM_DAG = "proof_term_dag"
GRAPH_FAMILY_UNKNOWN = "unknown"

_GRAPH_FAMILY_BY_KIND = {
    "search_graph": GRAPH_FAMILY_SEARCH_TRACE,
    "search_trace": GRAPH_FAMILY_SEARCH_TRACE,
    "trace_graph": GRAPH_FAMILY_SEARCH_TRACE,
    "search_trace_graph": GRAPH_FAMILY_SEARCH_TRACE,
    "proof_graph": GRAPH_FAMILY_EXTERNAL_PROOF,
    "external_proof": GRAPH_FAMILY_EXTERNAL_PROOF,
    "term_dag": GRAPH_FAMILY_PROOF_TERM_DAG,
    "proof_term_dag": GRAPH_FAMILY_PROOF_TERM_DAG,
    "unknown": GRAPH_FAMILY_UNKNOWN,
}
_LEGACY_GRAPH_KIND_BY_FAMILY = {
    GRAPH_FAMILY_SEARCH_TRACE: "search_graph",
    GRAPH_FAMILY_EXTERNAL_PROOF: "proof_graph",
    GRAPH_FAMILY_PROOF_TERM_DAG: "proof_term_dag",
    GRAPH_FAMILY_UNKNOWN: "unknown",
}


def normalize_graph_family(raw: str | None) -> str:
    if raw is None:
        return GRAPH_FAMILY_UNKNOWN
    norm = raw.strip().lower().replace("-", "_")
    if not norm:
        return GRAPH_FAMILY_UNKNOWN
    return _GRAPH_FAMILY_BY_KIND.get(norm, norm)


def legacy_graph_kind_for_family(graph_family: str) -> str:
    return _LEGACY_GRAPH_KIND_BY_FAMILY.get(
        normalize_graph_family(graph_family),
        normalize_graph_family(graph_family),
    )


def canonical_node_match(n1: dict, n2: dict) -> bool:
    if "goal_sig" not in n1 or "goal_sig" not in n2:
        raise ValueError("Missing goal_sig on node; canonical matching requires goal_sig")
    if n1["goal_sig"] is None or n2["goal_sig"] is None:
        raise ValueError("goal_sig is None; canonical matching requires goal_sig")
    return n1["goal_sig"] == n2["goal_sig"]


def canonical_edge_match(e1: dict, e2: dict) -> bool:
    if "tactic_norm" not in e1 or "tactic_norm" not in e2:
        raise ValueError("Missing tactic_norm on edge; canonical matching requires tactic_norm")
    if e1["tactic_norm"] is None or e2["tactic_norm"] is None:
        raise ValueError("tactic_norm is None; canonical matching requires tactic_norm")
    t1 = e1["tactic_norm"]
    t2 = e2["tactic_norm"]
    return tactic_family(t1) == tactic_family(t2)


@dataclass
class ProofGraph:
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    expansion_count: int = 0
    graph_family: str = GRAPH_FAMILY_UNKNOWN
    graph_backend: str = "unknown"
    graph_provenance: str = "unknown"
    graph_schema_version: int = 1

    @classmethod
    def for_search_trace(
        cls,
        *,
        backend: str,
        provenance: str = "mcts",
    ) -> "ProofGraph":
        return cls(
            graph_family=GRAPH_FAMILY_SEARCH_TRACE,
            graph_backend=backend,
            graph_provenance=provenance,
        )

    @classmethod
    def for_external_proof(
        cls,
        *,
        backend: str,
        provenance: str = "proof_object",
    ) -> "ProofGraph":
        return cls(
            graph_family=GRAPH_FAMILY_EXTERNAL_PROOF,
            graph_backend=backend,
            graph_provenance=provenance,
        )

    @classmethod
    def for_proof_term_dag(
        cls,
        *,
        backend: str,
        provenance: str = "proof_term",
    ) -> "ProofGraph":
        return cls(
            graph_family=GRAPH_FAMILY_PROOF_TERM_DAG,
            graph_backend=backend,
            graph_provenance=provenance,
        )

    def add_node(
        self,
        mvar_id: str,
        goal_type: str = "",
        depth: int = 0,
        goal_sig: str | None = None,
        **attrs: Any,
    ):
        self.graph.add_node(
            mvar_id,
            goal_type=goal_type,
            depth=depth,
            goal_sig=goal_sig,
            node_kind=attrs.pop("node_kind", "goal"),
            **attrs,
        )

    def add_expansion(
        self,
        parent_mvar: str,
        tactic: str,
        child_mvars: list[str],
        child_goal_types: list[str],
        child_goal_sigs: list[str | None],
        *,
        action_attrs: dict[str, Any] | None = None,
    ):
        self.expansion_count += 1

        if parent_mvar not in self.graph:
            self.add_node(parent_mvar)

        tactic_norm = normalize_tactic(tactic)
        fam = tactic_family(tactic_norm)
        edge_role = f"fam:{fam}" if fam else "fam:other"
        base_action_attrs: dict[str, Any] = {
            "action_kind": "tactic_step",
            "branch_arity": len(child_mvars),
            "expanded_child_count": len(child_mvars),
        }
        if action_attrs:
            base_action_attrs.update(action_attrs)

        if not child_mvars:
            terminal_attrs = {
                "is_terminal": True,
                "terminal_tactic": tactic,
                "terminal_tactic_norm": tactic_norm,
                "terminal_edge_role": edge_role,
                "terminal_action_kind": "tactic_step",
                "terminal_branch_arity": 0,
                "terminal_expanded_child_count": 0,
            }
            for key, value in base_action_attrs.items():
                terminal_attrs[f"terminal_{key}"] = deepcopy(value)
            self.graph.nodes[parent_mvar].update(terminal_attrs)

        for i, (child_mvar, goal_type) in enumerate(zip(child_mvars, child_goal_types)):
            if child_mvar not in self.graph:
                parent_depth = self.graph.nodes[parent_mvar].get("depth", 0)
                self.add_node(
                    child_mvar,
                    goal_type=goal_type,
                    depth=parent_depth + 1,
                    goal_sig=child_goal_sigs[i],
                )

            edge_payload = {
                "tactic": tactic,
                "tactic_norm": tactic_norm,
                "edge_role": edge_role,
                "action_kind": "tactic_step",
                "order": self.expansion_count,
            }
            for key, value in base_action_attrs.items():
                edge_payload[key] = deepcopy(value)
            self.graph.add_edge(
                parent_mvar,
                child_mvar,
                **edge_payload,
            )

    def update_node(self, mvar_id: str, **attrs: Any):
        if mvar_id in self.graph:
            self.graph.nodes[mvar_id].update(attrs)

    def to_networkx(self) -> nx.DiGraph:
        return self.graph

    def to_canonical(self) -> nx.DiGraph:
        canonical = nx.DiGraph()
        topo_order = {n: i for i, n in enumerate(nx.topological_sort(self.graph))}

        mvar_to_canonical = {}
        for mvar in self.graph.nodes:
            attrs = self.graph.nodes[mvar]
            goal_sig = attrs.get("goal_sig")
            if goal_sig is None:
                raise ValueError(f"Node {mvar} missing goal_sig - cannot canonicalize")
            depth = attrs.get("depth", 0)
            order = topo_order.get(mvar, 0)
            canonical_id = f"{goal_sig}_{depth}_{order}"
            mvar_to_canonical[mvar] = canonical_id

        for mvar, canonical_id in mvar_to_canonical.items():
            canonical.add_node(canonical_id, **self.graph.nodes[mvar])

        for u, v in self.graph.edges:
            canonical.add_edge(
                mvar_to_canonical[u],
                mvar_to_canonical[v],
                **self.graph.edges[u, v],
            )

        return canonical

    def extract_subgraph(self, mvar_ids: set[str]) -> "ProofGraph":
        subgraph = self.graph.subgraph(mvar_ids).copy()
        return ProofGraph(
            graph=subgraph,
            expansion_count=self.expansion_count,
            graph_family=self.graph_family,
            graph_backend=self.graph_backend,
            graph_provenance=self.graph_provenance,
            graph_schema_version=self.graph_schema_version,
        )

    def get_ancestors(self, mvar_id: str) -> set[str]:
        return nx.ancestors(self.graph, mvar_id)

    def get_descendants(self, mvar_id: str) -> set[str]:
        return nx.descendants(self.graph, mvar_id)

    def serialize(self) -> dict:
        return {
            "graph_schema_version": self.graph_schema_version,
            "graph_family": self.graph_family,
            "graph_backend": self.graph_backend,
            "graph_provenance": self.graph_provenance,
            "graph_kind": legacy_graph_kind_for_family(self.graph_family),
            "nodes": [{"id": n, **self.graph.nodes[n]} for n in self.graph.nodes],
            "edges": [
                {"source": u, "target": v, **self.graph.edges[u, v]} for u, v in self.graph.edges
            ],
        }

    @classmethod
    def deserialize(cls, data: dict) -> "ProofGraph":
        graph = nx.DiGraph()
        raw_family = data.get("graph_family")
        raw_kind = data.get("graph_kind")
        raw_backend = data.get("graph_backend")
        raw_provenance = data.get("graph_provenance")
        raw_schema_version = data.get("graph_schema_version")
        for node_data in data["nodes"]:
            node_payload = dict(node_data)
            node_id = node_payload.pop("id")
            graph.add_node(node_id, **node_payload)
        max_order = 0
        for edge_data in data["edges"]:
            edge_payload = dict(edge_data)
            source = edge_payload.pop("source")
            target = edge_payload.pop("target")
            order = edge_payload.get("order")
            if isinstance(order, int):
                max_order = max(max_order, order)
            graph.add_edge(source, target, **edge_payload)
        return cls(
            graph=graph,
            expansion_count=max_order,
            graph_family=normalize_graph_family(
                raw_family
                if isinstance(raw_family, str)
                else raw_kind if isinstance(raw_kind, str) else None
            ),
            graph_backend=raw_backend if isinstance(raw_backend, str) else "unknown",
            graph_provenance=raw_provenance if isinstance(raw_provenance, str) else "unknown",
            graph_schema_version=raw_schema_version if isinstance(raw_schema_version, int) else 0,
        )

    def is_isomorphic(
        self,
        other: "ProofGraph",
        node_match: Any = None,
        edge_match: Any = None,
    ) -> bool:
        if node_match is None:
            node_match = canonical_node_match
        if edge_match is None:
            edge_match = canonical_edge_match

        return nx.is_isomorphic(
            self.graph,
            other.graph,
            node_match=node_match,
            edge_match=edge_match,
        )

    def stats(self) -> dict:
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "expansions": self.expansion_count,
            "max_depth": max(
                (self.graph.nodes[n].get("depth", 0) for n in self.graph.nodes),
                default=0,
            ),
            "terminal_nodes": sum(
                1 for n in self.graph.nodes if self.graph.nodes[n].get("is_terminal", False)
            ),
        }

    def extract_solution_path(self) -> list[dict] | None:
        roots = [n for n in self.graph.nodes if self.graph.in_degree(n) == 0]
        if not roots:
            return None

        terminals = {
            n for n in self.graph.nodes if self.graph.nodes[n].get("is_terminal", False)
        }
        if not terminals:
            return None

        terminal_reachable = set(terminals)
        stack = list(terminals)
        while stack:
            node_id = stack.pop()
            for pred in self.graph.predecessors(node_id):
                if pred not in terminal_reachable:
                    terminal_reachable.add(pred)
                    stack.append(pred)

        result: list[dict] = []
        active: set[str] = set()

        def visit(node_id: str) -> bool:
            if node_id in active or node_id not in terminal_reachable:
                return False

            node_data = self.graph.nodes[node_id]
            if node_data.get("is_terminal", False):
                result.append({
                    "goal": node_data.get("goal_type", ""),
                    "tactic": node_data.get("terminal_tactic", ""),
                    "mvar_id": node_id,
                })
                return True

            active.add(node_id)
            try:
                for succ in self.graph.successors(node_id):
                    if succ not in terminal_reachable:
                        continue
                    edge_data = self.graph.edges[node_id, succ]
                    if visit(succ):
                        result.append({
                            "goal": node_data.get("goal_type", ""),
                            "tactic": edge_data.get("tactic", ""),
                            "mvar_id": node_id,
                        })
                        return True
            finally:
                active.remove(node_id)

            return False

        for root in roots:
            if visit(root):
                break

        result.reverse()
        return result if result else None
