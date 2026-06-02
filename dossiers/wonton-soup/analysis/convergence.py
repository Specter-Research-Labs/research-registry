#!/usr/bin/env python3
"""
Measure goal convergence in proof graphs.

Both graph kinds (search_graph from the Lean MCTS search, proof_graph from
external-prover reconstruction) are serialized as trees: edges = nodes - 1,
so a goal re-derived along distinct paths becomes distinct nodes sharing one
goal_sig. Quotienting nodes on goal_sig turns the tree into a DAG whose
in-degree counts how many distinct ways the proof arrived at a goal. That is
the basin / history-erasure signal: many predecessors funneling into one
goal, with the path forgotten downstream.

The two kinds quotient on different things, so the metric means different
things and is never comparable across kinds:
  search_graph.goal_sig = sha1 over the alpha-normalized goal AST plus
    sorted hypothesis hashes. Quotient convergence = the same proof
    obligation reached by distinct tactic paths (the basin signal).
  proof_graph.goal_sig = structural hash of the subterm rooted at the node
    (the graph IS the proof-term DAG, unfolded to a tree). Quotient
    convergence = the same sub-expression reused in many term positions
    (term self-similarity), NOT subgoal convergence.

Neither distinguishes the proof term filling a goal; this measures
convergence only, not the monodromy of the term fiber over a goal.

Usage:
    python -m analysis.convergence [LOGS_DIR] [--kind K] [--min-nodes N] [--top K] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from analysis.logs import read_json_auto


@dataclass
class GoalConvergence:
    goal_sig: str
    instances: int
    in_edges: int
    parents: int
    tactics: int


@dataclass
class GraphConvergence:
    name: str
    path: str
    kind: str
    nodes: int
    unique_sigs: int
    redundancy: float
    convergent_goals: int
    merge_goals: int
    max_in_edges: int
    has_cycle: bool
    top: list[GoalConvergence] = field(default_factory=list)


KINDS = ("search_graph", "proof_graph")


def _load_graph(path: Path, kind: str | None) -> dict | None:
    data = read_json_auto(path)
    if not isinstance(data, dict):
        return None
    gk = data.get("graph_kind")
    if gk not in KINDS or (kind is not None and gk != kind):
        return None
    if any("goal_sig" not in n for n in data.get("nodes", [])):
        return None
    return data


def _has_cycle(succ: dict[str, set[str]]) -> bool:
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def visit(start: str) -> bool:
        stack = [(start, iter(succ.get(start, ())))]
        color[start] = GREY
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                c = color.get(nxt, WHITE)
                if c == GREY:
                    return True
                if c == WHITE:
                    color[nxt] = GREY
                    stack.append((nxt, iter(succ.get(nxt, ()))))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()
        return False

    for sig in succ:
        if color.get(sig, WHITE) == WHITE and visit(sig):
            return True
    return False


def analyze(data: dict, name: str, path: Path, top_k: int) -> GraphConvergence:
    nodes = data["nodes"]
    edges = data.get("edges", [])

    id2sig = {n["id"]: n["goal_sig"] for n in nodes}
    instances: dict[str, int] = {}
    for n in nodes:
        instances[n["goal_sig"]] = instances.get(n["goal_sig"], 0) + 1

    preds: dict[str, set[tuple[str, str]]] = {}
    parent_sigs: dict[str, set[str]] = {}
    tactics: dict[str, set[str]] = {}
    succ: dict[str, set[str]] = {}
    for e in edges:
        s = id2sig[e["source"]]
        t = id2sig[e["target"]]
        tac = e.get("tactic_norm") or e.get("tactic", "")
        preds.setdefault(t, set()).add((s, tac))
        parent_sigs.setdefault(t, set()).add(s)
        tactics.setdefault(t, set()).add(tac)
        succ.setdefault(s, set()).add(t)

    goals = [
        GoalConvergence(
            goal_sig=sig,
            instances=instances[sig],
            in_edges=len(preds.get(sig, ())),
            parents=len(parent_sigs.get(sig, ())),
            tactics=len(tactics.get(sig, ())),
        )
        for sig in instances
    ]
    convergent = [g for g in goals if g.in_edges > 1]
    merge = [g for g in goals if g.parents > 1]
    unique = len(instances)
    top = sorted(convergent, key=lambda g: (g.in_edges, g.instances), reverse=True)[:top_k]

    return GraphConvergence(
        name=name,
        path=str(path),
        kind=data["graph_kind"],
        nodes=len(nodes),
        unique_sigs=unique,
        redundancy=len(nodes) / unique if unique else 0.0,
        convergent_goals=len(convergent),
        merge_goals=len(merge),
        max_in_edges=max((g.in_edges for g in goals), default=0),
        has_cycle=_has_cycle(succ),
        top=top,
    )


def scan(logs_dir: Path, kind: str | None, min_nodes: int, top_k: int) -> list[GraphConvergence]:
    results: list[GraphConvergence] = []
    for path in sorted(logs_dir.rglob("*_graph.json")):
        data = _load_graph(path, kind)
        if data is None or len(data["nodes"]) < min_nodes:
            continue
        results.append(analyze(data, path.parent.name, path, top_k))
    return results


def _print_kind(kind: str, results: list[GraphConvergence]) -> None:
    converging = [r for r in results if r.convergent_goals > 0]
    cyclic = [r for r in results if r.has_cycle]
    total_nodes = sum(r.nodes for r in results)
    total_unique = sum(r.unique_sigs for r in results)
    sizes = sorted(r.nodes for r in results)
    median = sizes[len(sizes) // 2]

    print(f"\n=== {kind} ===")
    print(f"graphs analyzed        : {len(results)}")
    print(f"  with convergence     : {len(converging)} ({len(converging) / len(results):.0%})")
    print(f"  with quotient cycles : {len(cyclic)} ({len(cyclic) / len(results):.0%})")
    print(f"node count             : median {median}, max {sizes[-1]}")
    print(f"aggregate redundancy   : {total_nodes / total_unique:.2f}x")

    by_merge = sorted(results, key=lambda r: (r.merge_goals, r.redundancy), reverse=True)[:12]
    print("top by merge goals (distinct predecessor goals into one goal):")
    cols = f"{'nodes':>6} {'uniq':>6} {'redund':>7} {'merge':>6} {'maxin':>6} {'cyc':>4}"
    print(f"  {'theorem':45} {cols}")
    for r in by_merge:
        print(
            f"  {r.name[:45]:45} {r.nodes:>6} {r.unique_sigs:>6} "
            f"{r.redundancy:>6.2f}x {r.merge_goals:>6} {r.max_in_edges:>6} "
            f"{'Y' if r.has_cycle else '':>4}"
        )


def print_report(results: list[GraphConvergence]) -> None:
    if not results:
        print("no graphs found")
        return
    for kind in KINDS:
        subset = [r for r in results if r.kind == kind]
        if subset:
            _print_kind(kind, subset)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs_dir", nargs="?", default="logs", type=Path)
    parser.add_argument("--kind", choices=KINDS, default=None)
    parser.add_argument("--min-nodes", type=int, default=2)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    logs_dir = args.logs_dir.resolve()
    if not logs_dir.is_dir():
        raise SystemExit(f"logs dir not found: {logs_dir}")

    results = scan(logs_dir, args.kind, args.min_nodes, args.top)
    print_report(results)

    if args.json is not None:
        args.json.write_text(json.dumps([asdict(r) for r in results], indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
