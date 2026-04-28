#!/usr/bin/env python3
"""
Analyze all proof graphs from corpus runs and build a problem registry.

Scans logs/corpus-*/*/wild_type_graph.json to find theorems with interesting
proof graphs (2+ nodes), tags them by provider and source corpus.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from runtime_paths import resolve_logs_root as _resolve_runtime_logs_root


@dataclass
class TheoremEntry:
    name: str
    corpus: str
    nodes: int
    edges: int
    max_depth: int
    reprover: bool
    deepseek: bool

    def complexity_score(self) -> float:
        return self.nodes + self.edges * 0.5 + self.max_depth * 0.3


def detect_corpus(theorem_name: str) -> str:
    if theorem_name.startswith("f2f_"):
        return "minif2f"
    elif theorem_name.startswith("ml_"):
        return "mathlib"
    elif theorem_name.startswith("pb_"):
        return "proverbench"
    elif theorem_name.startswith("ds_"):
        return "deepseek"
    else:
        return "easy"


def detect_provider(log_dir: Path) -> str | None:
    corpus_log = log_dir / "corpus.log"
    if not corpus_log.exists():
        return None

    content = corpus_log.read_text()
    if "ReProverTacticProvider" in content:
        return "reprover"
    elif "DeepSeekTacticProvider" in content:
        return "deepseek"
    elif "GoalAwareTacticProvider" in content or "heuristic" in content.lower():
        return "heuristic"
    return None


def analyze_graph(graph_file: Path) -> dict | None:
    try:
        data = json.loads(graph_file.read_text())
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        max_depth = 0
        for node in nodes:
            depth = node.get("depth", 0)
            if depth > max_depth:
                max_depth = depth

        return {
            "nodes": len(nodes),
            "edges": len(edges),
            "max_depth": max_depth,
        }
    except Exception:
        return None


def resolve_logs_dir(logs_dir: str | None) -> Path:
    if logs_dir is None or logs_dir == "logs":
        return _resolve_runtime_logs_root().resolve()
    return Path(logs_dir).resolve()


def scan_logs(logs_dir: Path) -> dict[str, TheoremEntry]:
    theorems: dict[str, TheoremEntry] = {}
    invalid_graphs = 0
    invalid_examples: list[str] = []

    for run_dir in sorted(logs_dir.glob("corpus-*")):
        if not run_dir.is_dir():
            continue

        provider = detect_provider(run_dir)

        for theorem_dir in run_dir.iterdir():
            if not theorem_dir.is_dir():
                continue

            graph_file = theorem_dir / "wild_type_graph.json"
            if not graph_file.exists():
                continue

            stats = analyze_graph(graph_file)
            if stats is None or stats["nodes"] < 1:
                if stats is None:
                    invalid_graphs += 1
                    if len(invalid_examples) < 5:
                        invalid_examples.append(str(graph_file))
                continue

            name = theorem_dir.name
            corpus = detect_corpus(name)

            if name not in theorems:
                theorems[name] = TheoremEntry(
                    name=name,
                    corpus=corpus,
                    nodes=stats["nodes"],
                    edges=stats["edges"],
                    max_depth=stats["max_depth"],
                    reprover=False,
                    deepseek=False,
                )

            entry = theorems[name]
            if stats["nodes"] > entry.nodes:
                entry.nodes = stats["nodes"]
                entry.edges = stats["edges"]
                entry.max_depth = stats["max_depth"]

            if provider == "reprover":
                entry.reprover = True
            elif provider == "deepseek":
                entry.deepseek = True

    if invalid_graphs:
        print(
            f"Warning: skipped {invalid_graphs} graphs due to read/parse errors; "
            f"examples={invalid_examples}",
            file=sys.stderr,
        )

    return theorems


def build_registry(theorems: dict[str, TheoremEntry], min_nodes: int = 2) -> dict:
    multi_node = [t for t in theorems.values() if t.nodes >= min_nodes]
    multi_node.sort(key=lambda t: -t.complexity_score())

    reprover_fast = [t for t in multi_node if t.reprover]
    reprover_fast.sort(key=lambda t: -t.complexity_score())

    short_tier = reprover_fast[:15]
    mid_tier = reprover_fast[:35]
    long_tier = multi_node[:120]

    return {
        "metadata": {
            "total_theorems": len(theorems),
            "multi_node_theorems": len(multi_node),
            "reprover_solvable": len([t for t in multi_node if t.reprover]),
            "deepseek_solvable": len([t for t in multi_node if t.deepseek]),
            "min_nodes": min_nodes,
        },
        "short": [asdict(t) for t in short_tier],
        "mid": [asdict(t) for t in mid_tier],
        "long": [asdict(t) for t in long_tier],
        "all_multi_node": [asdict(t) for t in multi_node],
    }


def print_summary(registry: dict):
    meta = registry["metadata"]
    print("\n=== Proof Graph Analysis ===")
    print(f"Total theorems scanned: {meta['total_theorems']}")
    print(f"Multi-node (2+): {meta['multi_node_theorems']}")
    print(f"ReProver solvable: {meta['reprover_solvable']}")
    print(f"DeepSeek solvable: {meta['deepseek_solvable']}")

    print("\n=== Tier Sizes ===")
    print(f"Short tier: {len(registry['short'])} theorems")
    print(f"Mid tier: {len(registry['mid'])} theorems")
    print(f"Long tier: {len(registry['long'])} theorems")

    print("\n=== Top 10 by Complexity ===")
    for t in registry["all_multi_node"][:10]:
        providers = []
        if t["reprover"]:
            providers.append("reprover")
        if t["deepseek"]:
            providers.append("deepseek")
        provider_str = ", ".join(providers) if providers else "unknown"
        summary = (
            f"  {t['name']}: {t['nodes']} nodes, {t['edges']} edges, "
            f"depth {t['max_depth']} [{provider_str}]"
        )
        print(summary)

    print("\n=== Short Tier (ReProver fast) ===")
    for t in registry["short"]:
        print(f"  {t['name']}: {t['nodes']} nodes [{t['corpus']}]")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Analyze proof graphs and build registry")
    parser.add_argument("--logs", type=str, default="logs", help="Logs directory")
    parser.add_argument(
        "--output",
        type=str,
        default="corpus/lean/problem_registry.json",
        help="Output file",
    )
    parser.add_argument("--min-nodes", type=int, default=2, help="Minimum nodes for inclusion")
    args = parser.parse_args()

    logs_dir = resolve_logs_dir(args.logs)
    if not logs_dir.exists():
        print(f"Logs directory not found: {logs_dir}")
        return

    print(f"Scanning {logs_dir}...")
    theorems = scan_logs(logs_dir)
    print(f"Found {len(theorems)} unique theorems")

    registry = build_registry(theorems, min_nodes=args.min_nodes)
    print_summary(registry)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(registry, indent=2))
    print(f"\nRegistry saved to {output_path}")


if __name__ == "__main__":
    main()
