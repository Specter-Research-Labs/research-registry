from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

EXPLICIT_AXIOMS = {"propext", "funext", "Quot.sound", "Classical.choice"}


@dataclass
class ExprNode:
    kind: str
    name: str | None = None
    levels: list[str] | None = None
    fn: str | None = None
    arg: str | None = None
    binder_name: str | None = None
    binder_type: str | None = None
    body: str | None = None
    binder_info: str | None = None
    value: str | None = None
    de_bruijn_idx: int | None = None
    fvar_id: str | None = None
    lit_val: str | None = None
    struct_name: str | None = None
    proj_idx: int | None = None
    proj_expr: str | None = None
    level_val: str | None = None

    @classmethod
    def from_json(cls, data: dict) -> ExprNode:
        return cls(
            kind=data["kind"],
            name=data.get("name"),
            levels=data.get("levels"),
            fn=data.get("fn"),
            arg=data.get("arg"),
            binder_name=data.get("binderName"),
            binder_type=data.get("binderType"),
            body=data.get("body"),
            binder_info=data.get("binderInfo"),
            value=data.get("value"),
            de_bruijn_idx=data.get("deBruijnIdx"),
            fvar_id=data.get("fvarId"),
            lit_val=data.get("litVal"),
            struct_name=data.get("structName"),
            proj_idx=data.get("projIdx"),
            proj_expr=data.get("projExpr"),
            level_val=data.get("levelVal"),
        )

    def canonical_repr(self) -> str:
        parts = [self.kind]
        if self.name:
            parts.append(f"name={self.name}")
        if self.levels:
            parts.append(f"levels={','.join(self.levels)}")
        if self.binder_info:
            parts.append(f"bi={self.binder_info}")
        if self.de_bruijn_idx is not None:
            parts.append(f"idx={self.de_bruijn_idx}")
        if self.fvar_id:
            parts.append(f"fvar={self.fvar_id}")
        if self.lit_val:
            parts.append(f"lit={self.lit_val}")
        if self.struct_name:
            parts.append(f"struct={self.struct_name}")
        if self.proj_idx is not None:
            parts.append(f"proj={self.proj_idx}")
        if self.level_val:
            parts.append(f"level={self.level_val}")
        return "|".join(parts)


@dataclass
class ExprDAG:
    root_id: str
    nodes: dict[str, ExprNode] = field(default_factory=dict)
    _hash_cache: str | None = field(default=None, repr=False)

    @classmethod
    def from_json(cls, data: dict) -> ExprDAG:
        nodes = {}
        for node_id, node_data in data["nodes"]:
            nodes[node_id] = ExprNode.from_json(node_data)
        return cls(root_id=data["rootId"], nodes=nodes)

    def structural_hash(self) -> str:
        if self._hash_cache is not None:
            return self._hash_cache

        visited: dict[str, str] = {}

        # Iterative post-order: deep proof terms exceed Python's stack limit
        stack: list[tuple[str, bool]] = [(self.root_id, False)]
        in_progress: set[str] = set()
        while stack:
            node_id, children_done = stack[-1]
            if node_id in visited:
                stack.pop()
                continue
            if node_id in in_progress and not children_done:
                visited[node_id] = f"cycle:{node_id}"
                stack.pop()
                continue

            node = self.nodes.get(node_id)
            if node is None:
                visited[node_id] = f"missing:{node_id}"
                stack.pop()
                continue

            child_ids = [c for c in (node.fn, node.arg, node.binder_type,
                                     node.body, node.value, node.proj_expr) if c]

            if not children_done:
                unvisited = [c for c in child_ids if c not in visited]
                if unvisited:
                    in_progress.add(node_id)
                    stack[-1] = (node_id, True)
                    for c in reversed(unvisited):
                        stack.append((c, False))
                    continue

            in_progress.discard(node_id)
            parts = [node.canonical_repr()]
            label_map = {node.fn: "fn", node.arg: "arg", node.binder_type: "ty",
                         node.body: "body", node.value: "val", node.proj_expr: "proj"}
            for c in child_ids:
                lbl = label_map[c]
                parts.append(f"{lbl}:{visited.get(c, 'missing')}")

            combined = ";".join(parts)
            visited[node_id] = hashlib.sha256(combined.encode()).hexdigest()[:16]
            stack.pop()

        self._hash_cache = visited.get(self.root_id, "empty")
        return self._hash_cache

    def is_equivalent(self, other: ExprDAG) -> bool:
        return self.structural_hash() == other.structural_hash()

    def node_count(self) -> int:
        return len(self.nodes)

    def metrics(self) -> dict:
        depth = self._compute_depth()
        app_count = sum(1 for n in self.nodes.values() if n.kind == "app")
        lam_count = sum(1 for n in self.nodes.values() if n.kind == "lam")
        forall_count = sum(1 for n in self.nodes.values() if n.kind == "forallE")
        const_names = self._const_names()

        return {
            "node_count": len(self.nodes),
            "depth": depth,
            "app_count": app_count,
            "lam_count": lam_count,
            "forall_count": forall_count,
            "const_names": sorted(const_names),
            "unique_consts": len(const_names),
        }

    def _compute_depth(self) -> int:
        if not self.nodes or self.root_id not in self.nodes:
            return 0

        depths: dict[str, int] = {}

        # Iterative post-order: deep proof terms exceed Python's stack limit
        stack: list[tuple[str, bool]] = [(self.root_id, False)]
        in_progress: set[str] = set()
        while stack:
            node_id, children_done = stack[-1]
            if node_id in depths:
                stack.pop()
                continue
            if node_id in in_progress and not children_done:
                depths[node_id] = 0  # back-edge in malformed DAG
                stack.pop()
                continue

            node = self.nodes.get(node_id)
            if node is None:
                depths[node_id] = 0
                stack.pop()
                continue

            child_ids = [c for c in (node.fn, node.arg, node.binder_type,
                                     node.body, node.value, node.proj_expr) if c]

            if not children_done:
                unvisited = [c for c in child_ids if c not in depths]
                if unvisited:
                    in_progress.add(node_id)
                    stack[-1] = (node_id, True)
                    for c in reversed(unvisited):
                        stack.append((c, False))
                    continue

            in_progress.discard(node_id)
            if not child_ids:
                depths[node_id] = 1
            else:
                depths[node_id] = 1 + max(depths.get(c, 0) for c in child_ids)
            stack.pop()

        return depths.get(self.root_id, 0)

    def _const_names(self) -> set[str]:
        return {n.name for n in self.nodes.values() if n.kind == "const" and n.name}

    def axiom_fingerprint(self) -> dict:
        consts = self._const_names()
        classical = {c for c in consts if c.startswith("Classical.")}
        explicit = {c for c in consts if c in EXPLICIT_AXIOMS}
        all_axioms = classical | explicit
        return {
            "classical": sorted(classical),
            "explicit": sorted(explicit),
            "all": sorted(all_axioms),
        }

    def _node_kind_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self.nodes.values():
            counts[node.kind] = counts.get(node.kind, 0) + 1
        return counts

    def _depth_profile(self) -> dict[int, int]:
        if not self.nodes or self.root_id not in self.nodes:
            return {}

        depths: dict[str, int] = {self.root_id: 0}
        queue: list[str] = [self.root_id]

        while queue:
            node_id = queue.pop(0)
            node = self.nodes.get(node_id)
            if node is None:
                continue
            base_depth = depths[node_id]
            children = [node.fn, node.arg, node.binder_type, node.body, node.value, node.proj_expr]
            for child_id in children:
                if not child_id:
                    continue
                next_depth = base_depth + 1
                if child_id not in depths or next_depth < depths[child_id]:
                    depths[child_id] = next_depth
                    queue.append(child_id)

        profile: dict[int, int] = {}
        for depth in depths.values():
            profile[depth] = profile.get(depth, 0) + 1
        return profile

    def to_networkx(self):
        import networkx as nx

        g = nx.DiGraph()
        for node_id, node in self.nodes.items():
            g.add_node(node_id, **{"kind": node.kind, "name": node.name or ""})

            if node.fn:
                g.add_edge(node_id, node.fn, label="fn")
            if node.arg:
                g.add_edge(node_id, node.arg, label="arg")
            if node.binder_type:
                g.add_edge(node_id, node.binder_type, label="type")
            if node.body:
                g.add_edge(node_id, node.body, label="body")
            if node.value:
                g.add_edge(node_id, node.value, label="value")
            if node.proj_expr:
                g.add_edge(node_id, node.proj_expr, label="proj")

        return g

    def serialize(self) -> dict:
        return {
            "rootId": self.root_id,
            "nodes": [
                (
                    node_id,
                    {
                        "kind": node.kind,
                        "name": node.name,
                        "levels": node.levels,
                        "fn": node.fn,
                        "arg": node.arg,
                        "binderName": node.binder_name,
                        "binderType": node.binder_type,
                        "body": node.body,
                        "binderInfo": node.binder_info,
                        "value": node.value,
                        "deBruijnIdx": node.de_bruijn_idx,
                        "fvarId": node.fvar_id,
                        "litVal": node.lit_val,
                        "structName": node.struct_name,
                        "projIdx": node.proj_idx,
                        "projExpr": node.proj_expr,
                        "levelVal": node.level_val,
                    },
                )
                for node_id, node in self.nodes.items()
            ],
        }

    def pretty_print(self, indent: int = 0) -> str:
        lines = []
        visited = set()

        def visit(node_id: str, depth: int):
            if node_id in visited:
                lines.append("  " * depth + f"[ref: {node_id}]")
                return
            visited.add(node_id)

            node = self.nodes.get(node_id)
            if node is None:
                lines.append("  " * depth + f"[missing: {node_id}]")
                return

            label = node.kind
            if node.name:
                label += f" {node.name}"
            if node.binder_name:
                label += f" ({node.binder_name})"
            if node.lit_val:
                label += f" = {node.lit_val}"
            if node.de_bruijn_idx is not None:
                label += f" #{node.de_bruijn_idx}"

            lines.append("  " * depth + label)

            if node.fn:
                lines.append("  " * (depth + 1) + "fn:")
                visit(node.fn, depth + 2)
            if node.arg:
                lines.append("  " * (depth + 1) + "arg:")
                visit(node.arg, depth + 2)
            if node.binder_type:
                lines.append("  " * (depth + 1) + "type:")
                visit(node.binder_type, depth + 2)
            if node.body:
                lines.append("  " * (depth + 1) + "body:")
                visit(node.body, depth + 2)

        visit(self.root_id, indent)
        return "\n".join(lines)

    def to_lean_string(self, max_depth: int = 50) -> str:
        visited: set[str] = set()

        def visit(node_id: str, depth: int = 0) -> str:
            if depth > max_depth:
                return "..."
            if node_id in visited:
                return f"[cycle:{node_id[:8]}]"
            visited.add(node_id)

            node = self.nodes.get(node_id)
            if node is None:
                return f"[missing:{node_id[:8]}]"

            if node.kind == "const":
                return node.name or "[anon]"

            if node.kind == "app":
                fn = visit(node.fn, depth + 1) if node.fn else "_"
                arg = visit(node.arg, depth + 1) if node.arg else "_"
                return f"({fn} {arg})"

            if node.kind == "lam":
                body = visit(node.body, depth + 1) if node.body else "_"
                name = node.binder_name or "_"
                return f"(fun {name} => {body})"

            if node.kind == "forallE":
                body = visit(node.body, depth + 1) if node.body else "_"
                name = node.binder_name or "_"
                ty = visit(node.binder_type, depth + 1) if node.binder_type else "_"
                return f"(forall {name} : {ty}, {body})"

            if node.kind == "bvar":
                return f"#{node.de_bruijn_idx}" if node.de_bruijn_idx is not None else "#?"

            if node.kind == "fvar":
                return node.fvar_id or "[fvar]"

            if node.kind == "mvar":
                return f"?{node.name or 'mvar'}"

            if node.kind == "lit":
                if node.lit_val:
                    parts = node.lit_val.split(":")
                    return parts[1] if len(parts) > 1 else node.lit_val
                return "[lit]"

            if node.kind == "sort":
                return node.level_val or "Sort"

            if node.kind == "proj":
                expr = visit(node.proj_expr, depth + 1) if node.proj_expr else "_"
                return f"{node.struct_name or 'proj'}.{node.proj_idx or '?'}({expr})"

            if node.kind == "letE":
                val = visit(node.value, depth + 1) if node.value else "_"
                body = visit(node.body, depth + 1) if node.body else "_"
                name = node.binder_name or "_"
                return f"(let {name} := {val}; {body})"

            return f"[{node.kind}]"

        return visit(self.root_id)

    def structural_diff(self, other: "ExprDAG") -> dict:
        if self.structural_hash() == other.structural_hash():
            return {
                "identical": True,
                "divergence_depth": None,
                "divergence_path": None,
                "self_at_divergence": None,
                "other_at_divergence": None,
                "self_subtree_size": len(self.nodes),
                "other_subtree_size": len(other.nodes),
            }

        divergence_info: dict = {
            "identical": False,
            "divergence_depth": 0,
            "divergence_path": [],
            "self_at_divergence": None,
            "other_at_divergence": None,
            "self_subtree_size": len(self.nodes),
            "other_subtree_size": len(other.nodes),
        }

        def count_subtree(dag: "ExprDAG", node_id: str, visited: set[str]) -> int:
            if node_id in visited:
                return 0
            visited.add(node_id)
            node = dag.nodes.get(node_id)
            if node is None:
                return 0
            count = 1
            child_ids = [node.fn, node.arg, node.binder_type, node.body, node.value, node.proj_expr]
            for child_id in child_ids:
                if child_id:
                    count += count_subtree(dag, child_id, visited)
            return count

        visited_pairs: set[tuple[str, str]] = set()

        def compare(self_id: str, other_id: str, path: list[str], depth: int) -> bool:
            pair = (self_id, other_id)
            if pair in visited_pairs:
                return True  # already compared or cycle; treat as equal
            visited_pairs.add(pair)

            self_node = self.nodes.get(self_id)
            other_node = other.nodes.get(other_id)

            if self_node is None and other_node is None:
                return True
            if self_node is None or other_node is None:
                divergence_info["divergence_depth"] = depth
                divergence_info["divergence_path"] = " -> ".join(path) if path else "root"
                self_kind = self_node.kind if self_node else "[missing]"
                other_kind = other_node.kind if other_node else "[missing]"
                divergence_info["self_at_divergence"] = self_kind
                divergence_info["other_at_divergence"] = other_kind
                return False

            if self_node.kind != other_node.kind:
                divergence_info["divergence_depth"] = depth
                divergence_info["divergence_path"] = " -> ".join(path) if path else "root"
                divergence_info["self_at_divergence"] = f"{self_node.kind}"
                if self_node.name:
                    divergence_info["self_at_divergence"] += f":{self_node.name}"
                divergence_info["other_at_divergence"] = f"{other_node.kind}"
                if other_node.name:
                    divergence_info["other_at_divergence"] += f":{other_node.name}"
                divergence_info["self_subtree_size"] = count_subtree(self, self_id, set())
                divergence_info["other_subtree_size"] = count_subtree(other, other_id, set())
                return False

            if self_node.kind == "const" and self_node.name != other_node.name:
                divergence_info["divergence_depth"] = depth
                divergence_info["divergence_path"] = " -> ".join(path) if path else "root"
                divergence_info["self_at_divergence"] = f"const:{self_node.name}"
                divergence_info["other_at_divergence"] = f"const:{other_node.name}"
                divergence_info["self_subtree_size"] = 1
                divergence_info["other_subtree_size"] = 1
                return False

            if self_node.kind == "bvar" and self_node.de_bruijn_idx != other_node.de_bruijn_idx:
                divergence_info["divergence_depth"] = depth
                divergence_info["divergence_path"] = " -> ".join(path) if path else "root"
                divergence_info["self_at_divergence"] = f"bvar:#{self_node.de_bruijn_idx}"
                divergence_info["other_at_divergence"] = f"bvar:#{other_node.de_bruijn_idx}"
                return False

            if self_node.kind == "lit" and self_node.lit_val != other_node.lit_val:
                divergence_info["divergence_depth"] = depth
                divergence_info["divergence_path"] = " -> ".join(path) if path else "root"
                divergence_info["self_at_divergence"] = f"lit:{self_node.lit_val}"
                divergence_info["other_at_divergence"] = f"lit:{other_node.lit_val}"
                return False

            child_pairs = [
                ("fn", self_node.fn, other_node.fn),
                ("arg", self_node.arg, other_node.arg),
                ("type", self_node.binder_type, other_node.binder_type),
                ("body", self_node.body, other_node.body),
                ("value", self_node.value, other_node.value),
                ("proj", self_node.proj_expr, other_node.proj_expr),
            ]

            for label, self_child, other_child in child_pairs:
                if self_child is None and other_child is None:
                    continue
                if self_child is None or other_child is None:
                    divergence_info["divergence_depth"] = depth + 1
                    divergence_info["divergence_path"] = " -> ".join(path + [label])
                    if self_child is None:
                        self_div = "[missing]"
                    else:
                        self_div = self.nodes.get(self_child, ExprNode(kind="?")).kind
                    if other_child is None:
                        other_div = "[missing]"
                    else:
                        other_div = other.nodes.get(other_child, ExprNode(kind="?")).kind
                    divergence_info["self_at_divergence"] = self_div
                    divergence_info["other_at_divergence"] = other_div
                    return False
                if not compare(self_child, other_child, path + [label], depth + 1):
                    return False

            return True

        compare(self.root_id, other.root_id, [], 0)

        self_consts = self._const_names()
        other_consts = other._const_names()
        divergence_info["consts_only_in_self"] = sorted(self_consts - other_consts)
        divergence_info["consts_only_in_other"] = sorted(other_consts - self_consts)
        divergence_info["consts_in_common"] = sorted(self_consts & other_consts)
        divergence_info["constant_diff"] = {
            "only_in_self": divergence_info["consts_only_in_self"],
            "only_in_other": divergence_info["consts_only_in_other"],
            "shared": divergence_info["consts_in_common"],
        }

        self_kind_counts = self._node_kind_counts()
        other_kind_counts = other._node_kind_counts()
        all_kinds = sorted(set(self_kind_counts) | set(other_kind_counts))
        divergence_info["node_type_diff"] = {
            "self": self_kind_counts,
            "other": other_kind_counts,
            "delta": {
                kind: self_kind_counts.get(kind, 0) - other_kind_counts.get(kind, 0)
                for kind in all_kinds
            },
        }

        self_profile = self._depth_profile()
        other_profile = other._depth_profile()
        all_depths = sorted(set(self_profile) | set(other_profile))
        divergence_info["depth_profile_diff"] = {
            "self": self_profile,
            "other": other_profile,
            "delta": {
                depth: self_profile.get(depth, 0) - other_profile.get(depth, 0)
                for depth in all_depths
            },
        }

        return divergence_info


@dataclass
class MvarHole:
    mvar_id: str
    type_str: str

    @classmethod
    def from_json(cls, data: dict) -> MvarHole:
        return cls(
            mvar_id=data["mvarId"],
            type_str=data["type"],
        )

    def serialize(self) -> dict:
        return {"mvarId": self.mvar_id, "type": self.type_str}


@dataclass
class PartialProofTerm:
    proof_dag: ExprDAG
    open_mvars: list[MvarHole]
    is_complete: bool

    @classmethod
    def from_json(cls, data: dict) -> PartialProofTerm:
        return cls(
            proof_dag=ExprDAG.from_json(data["proofTerm"]),
            open_mvars=[MvarHole.from_json(m) for m in data["openMvars"]],
            is_complete=data["isComplete"],
        )

    def serialize(self) -> dict:
        return {
            "proofTerm": self.proof_dag.serialize(),
            "openMvars": [m.serialize() for m in self.open_mvars],
            "isComplete": self.is_complete,
        }

    def structural_hash(self) -> str:
        return self.proof_dag.structural_hash()

    def is_equivalent(self, other: PartialProofTerm) -> bool:
        return self.proof_dag.is_equivalent(other.proof_dag)
