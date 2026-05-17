#!/usr/bin/env python3
"""Render a real Wonton Soup baseline/intervention pair as a deterministic SVG.

The solid graph is the final MCTS tree. Pale side branches are proposed,
failed, or blocked tactics pulled from the trace, so the diagram keeps the
exploration texture without inventing proof states.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import textwrap
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


INK = "#17202a"
MUTED = "#65727f"
PANEL = "#f7f9fb"
PANEL_STROKE = "#d7dee6"
REAL = "#2f3d4a"
PATH = "#16837a"
GHOST = "#b9c2cb"
FAIL = "#c07c4a"
BLOCK = "#d14b40"
TERM = "#1f8f5b"


@dataclass(frozen=True)
class Ghost:
    tactic: str
    outcome: str
    score: float | None = None
    block_reason: str | None = None


def read_json(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


def maybe_read_checkpoint_statement(pair_dir: Path) -> str | None:
    path = pair_dir / "theorem_result.checkpoint.json.gz"
    if not path.exists() or path.stat().st_size > 2_000_000:
        return None
    with gzip.open(path, "rt") as f:
        data = json.load(f)
    theorem = data.get("theorem") if isinstance(data, dict) else None
    if isinstance(theorem, dict):
        return theorem.get("statement")
    return None


def theorem_id_from_text(text: str, fallback: str) -> str:
    match = re.search(r"hf_deepseek_prover_v1_train_\d+", text)
    return match.group(0) if match else fallback


def clean_theorem(pair_dir: Path, intervention: str, fallback_id: str) -> str:
    hist_path = pair_dir / "wild_type_history.json"
    text = None
    if hist_path.exists():
        text = read_json(hist_path).get("theorem")
    text = maybe_read_checkpoint_statement(pair_dir) or text
    if not text:
        tree = read_json(pair_dir / "wild_type_mcts_tree.json")
        root = tree["nodes"][tree["root_mvar_id"]]["goal_type"]
        text = f"theorem {fallback_id} :\n  {root} := by\n  sorry"

    theorem_id = theorem_id_from_text(text, fallback_id)
    text = text.replace("{name}", theorem_id)
    text = re.sub(r"theorem\s+\S+", f"theorem {theorem_id}", text, count=1)
    text = re.sub(r"\s*:=\s*by\s*\n\s*sorry\s*$", "", text.strip())
    return text


def norm_tactic(tactic: str) -> str:
    return re.sub(r"\s+", " ", tactic.strip())


def truncate(text: str, width: int) -> str:
    text = norm_tactic(text)
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)].rstrip() + "…"


def wrap_lines(text: str, width: int) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        if raw == "":
            out.append("")
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        prefix = " " * indent
        chunks = textwrap.wrap(
            raw,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
            subsequent_indent=prefix + "  ",
        )
        out.extend(chunks or [raw])
    return out


def svg_text(
    lines: list[str],
    x: float,
    y: float,
    size: int = 18,
    fill: str = INK,
    family: str = "Inter, Helvetica, Arial, sans-serif",
    weight: str = "400",
    line_height: float = 1.25,
    anchor: str = "start",
) -> str:
    tspans = []
    dy0 = 0
    for i, line in enumerate(lines):
        dy = dy0 if i == 0 else size * line_height
        tspans.append(
            f'<tspan x="{x:.1f}" dy="{dy:.1f}">{escape(line)}</tspan>'
        )
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-family="{family}" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}">'
        + "".join(tspans)
        + f"</text>"
    )


def tree_edges(tree: dict[str, Any]) -> list[tuple[str, str, str]]:
    edges = []
    for parent, node in tree["nodes"].items():
        for tactic, children in (node.get("children") or {}).items():
            for child in children:
                edges.append((parent, child, tactic))
    return edges


def child_map(edges: list[tuple[str, str, str]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for parent, child, _ in edges:
        out[parent].append(child)
    return out


def collect_path_edges(
    tree: dict[str, Any], metrics: dict[str, Any] | None
) -> set[tuple[str, str]]:
    if not metrics:
        return set()
    by_parent_tactic: dict[tuple[str, str], list[str]] = defaultdict(list)
    for parent, child, tactic in tree_edges(tree):
        by_parent_tactic[(parent, norm_tactic(tactic))].append(child)
    path_edges: set[tuple[str, str]] = set()
    for step in metrics.get("solution_path") or []:
        parent = step.get("mvar_id")
        tactic = step.get("tactic")
        if not parent or not tactic:
            continue
        children = by_parent_tactic.get((parent, norm_tactic(tactic))) or []
        for child in children:
            path_edges.add((parent, child))
    return path_edges


def collect_ghosts(
    trace_path: Path,
    tree: dict[str, Any],
    ghosts_per_node: int,
) -> dict[str, list[Ghost]]:
    edge_tactics: dict[str, set[str]] = defaultdict(set)
    for parent, _, tactic in tree_edges(tree):
        edge_tactics[parent].add(norm_tactic(tactic))

    ghosts: dict[str, list[Ghost]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)
    if not trace_path.exists():
        return ghosts

    for line in trace_path.open():
        event = json.loads(line)
        if event.get("event") != "iteration":
            continue
        node_id = (event.get("node") or {}).get("mvar_id")
        if not node_id or node_id not in tree["nodes"]:
            continue

        attempts = {}
        for attempt in event.get("attempts") or []:
            tactic = attempt.get("tactic") or attempt.get("tactic_norm")
            if tactic:
                attempts[norm_tactic(tactic)] = attempt

        candidates: list[tuple[str, float | None]] = []
        for t in event.get("tactics") or []:
            tactic = t.get("tactic")
            if tactic:
                candidates.append((tactic, t.get("score")))
        for attempt in event.get("attempts") or []:
            tactic = attempt.get("tactic") or attempt.get("tactic_norm")
            if tactic and all(norm_tactic(tactic) != norm_tactic(c[0]) for c in candidates):
                candidates.append((tactic, None))

        for tactic, score in candidates:
            key = norm_tactic(tactic)
            if key in edge_tactics.get(node_id, set()):
                continue
            if key in seen[node_id]:
                continue
            attempt = attempts.get(key, {})
            outcome = attempt.get("outcome") or "proposed"
            block_reason = attempt.get("block_reason")
            ghosts[node_id].append(Ghost(tactic, outcome, score, block_reason))
            seen[node_id].add(key)

    def rank(g: Ghost) -> tuple[int, float, str]:
        priority = {"blocked": 0, "failure": 1, "proposed": 2, "success": 3}.get(g.outcome, 4)
        return (priority, -(g.score or 0.0), g.tactic)

    for node_id, items in list(ghosts.items()):
        items.sort(key=rank)
        must_keep = [g for g in items if g.outcome == "blocked"]
        rest = [g for g in items if g.outcome != "blocked"]
        kept = (must_keep + rest)[:ghosts_per_node]
        ghosts[node_id] = kept
    return ghosts


def layout_tree(
    tree: dict[str, Any],
    panel_x: float,
    panel_y: float,
    panel_w: float,
    panel_h: float,
) -> dict[str, tuple[float, float]]:
    nodes = tree["nodes"]
    edges = tree_edges(tree)
    children = child_map(edges)
    root = tree["root_mvar_id"]
    max_depth = max((n.get("depth") or 0) for n in nodes.values()) or 1
    left = panel_x + 50
    right = panel_x + panel_w - 40
    top = panel_y + 118
    bottom = panel_y + panel_h - 56
    leaf_y: dict[str, float] = {}
    order = 0

    def assign(node_id: str) -> float:
        nonlocal order
        kids = [kid for kid in children.get(node_id, []) if kid in nodes]
        if not kids:
            order += 1
            leaf_y[node_id] = float(order)
            return leaf_y[node_id]
        ys = [assign(kid) for kid in kids]
        leaf_y[node_id] = sum(ys) / len(ys)
        return leaf_y[node_id]

    assign(root)
    leaf_count = max(1, order)
    positions: dict[str, tuple[float, float]] = {}
    for node_id, node in nodes.items():
        depth = node.get("depth") or 0
        x = left + (right - left) * depth / max_depth
        if leaf_count == 1:
            y = (top + bottom) / 2 + math.sin(depth * 0.72) * 26
        else:
            y = top + (bottom - top) * (leaf_y.get(node_id, 1) - 0.5) / leaf_count
        positions[node_id] = (x, y)
    return positions


def bezier(x1: float, y1: float, x2: float, y2: float) -> str:
    dx = max(24, abs(x2 - x1) * 0.42)
    return f"M{x1:.1f},{y1:.1f} C{x1+dx:.1f},{y1:.1f} {x2-dx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"


def graph_stats(tree: dict[str, Any], ghosts: dict[str, list[Ghost]]) -> tuple[int, int, int, int]:
    nodes = len(tree["nodes"])
    edges = len(tree_edges(tree))
    max_depth = max((n.get("depth") or 0) for n in tree["nodes"].values()) if nodes else 0
    ghost_count = sum(len(v) for v in ghosts.values())
    return nodes, edges, max_depth, ghost_count


def trace_blocked(trace_path: Path) -> list[str]:
    blocked: list[str] = []
    if not trace_path.exists():
        return blocked
    for line in trace_path.open():
        event = json.loads(line)
        for attempt in event.get("attempts") or []:
            if attempt.get("outcome") == "blocked" or attempt.get("block_reason"):
                tactic = attempt.get("tactic") or attempt.get("tactic_norm")
                if tactic:
                    blocked.append(tactic)
    return blocked


def solution_tactics(metrics: dict[str, Any] | None) -> list[str]:
    if not metrics:
        return []
    return [s.get("tactic", "") for s in metrics.get("solution_path") or [] if s.get("tactic")]


def first_reroute(wild_metrics: dict[str, Any] | None, int_metrics: dict[str, Any] | None) -> list[str]:
    wild = solution_tactics(wild_metrics)
    inter = solution_tactics(int_metrics)
    i = 0
    while i < min(len(wild), len(inter)) and norm_tactic(wild[i]) == norm_tactic(inter[i]):
        i += 1
    return inter[i : i + 3] or inter[-3:]


def draw_graph_panel(
    tree: dict[str, Any],
    metrics: dict[str, Any] | None,
    trace_path: Path,
    title: str,
    subtitle: str,
    panel_x: float,
    panel_y: float,
    panel_w: float,
    panel_h: float,
    ghosts_per_node: int,
    callout: list[str] | None = None,
    highlight_blocked: bool = True,
) -> tuple[str, dict[str, int]]:
    ghosts = collect_ghosts(trace_path, tree, ghosts_per_node)
    positions = layout_tree(tree, panel_x, panel_y, panel_w, panel_h)
    path_edges = collect_path_edges(tree, metrics)
    edges = tree_edges(tree)
    nodes = tree["nodes"]
    parts: list[str] = []

    parts.append(
        f'<rect x="{panel_x:.1f}" y="{panel_y:.1f}" width="{panel_w:.1f}" height="{panel_h:.1f}" '
        f'rx="10" fill="{PANEL}" stroke="{PANEL_STROKE}" stroke-width="1"/>'
    )
    parts.append(svg_text([title], panel_x + 26, panel_y + 36, 24, INK, weight="700"))
    parts.append(svg_text([subtitle], panel_x + 26, panel_y + 66, 15, MUTED))

    n_nodes, n_edges, max_depth, n_ghosts = graph_stats(tree, ghosts)
    chips = f"{n_nodes} goals  /  {n_edges} tactic edges  /  depth {max_depth}  /  {n_ghosts} trace branches"
    parts.append(svg_text([chips], panel_x + 26, panel_y + 91, 14, MUTED))

    if callout:
        box_w = min(330, panel_w - 52)
        box_h = 28 + 21 * len(callout)
        box_x = panel_x + panel_w - box_w - 24
        box_y = panel_y + 24
        parts.append(
            f'<rect x="{box_x:.1f}" y="{box_y:.1f}" width="{box_w:.1f}" height="{box_h:.1f}" '
            f'rx="8" fill="#fff6f4" stroke="#efb4ac" stroke-width="1"/>'
        )
        parts.append(svg_text(callout, box_x + 14, box_y + 22, 14, BLOCK, weight="600"))

    # Ghost exploration branches first, behind real tree.
    for node_id, items in ghosts.items():
        if node_id not in positions:
            continue
        x, y = positions[node_id]
        for idx, ghost in enumerate(items):
            direction = -1 if idx % 2 == 0 else 1
            lane = idx // 2 + 1
            dx = 42 + 8 * lane
            if x + dx > panel_x + panel_w - 20:
                dx = -dx
            dy = direction * (22 + 15 * lane)
            gx = max(panel_x + 24, min(panel_x + panel_w - 24, x + dx))
            gy = max(panel_y + 116, min(panel_y + panel_h - 28, y + dy))
            is_blocked = highlight_blocked and ghost.outcome == "blocked"
            is_failure = highlight_blocked and ghost.outcome in {"failure", "blocked"} and not is_blocked
            color = BLOCK if is_blocked else FAIL if is_failure else GHOST
            dash = "1 0" if is_blocked else "3 5"
            parts.append(
                f'<path d="{bezier(x, y, gx, gy)}" fill="none" stroke="{color}" '
                f'stroke-width="{2.5 if is_blocked else 1.4}" stroke-opacity="0.68" '
                f'stroke-dasharray="{dash}"/>'
            )
            radius = 3.8 if is_blocked else 3.0
            parts.append(
                f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="{radius}" fill="{PANEL}" '
                f'stroke="{color}" stroke-width="{1.5 if is_blocked else 1}"/>'
            )
            if is_blocked:
                label = "blocked: " + truncate(ghost.tactic, 34)
                ly = gy - 7 if direction < 0 else gy + 15
                parts.append(svg_text([label], gx + 5, ly, 10, color, family="ui-monospace, SFMono-Regular, Menlo, monospace"))

    # Solid MCTS tree.
    label_budget = 16 if len(edges) <= 24 else 8
    labels_drawn = 0
    for parent, child, tactic in edges:
        if parent not in positions or child not in positions:
            continue
        x1, y1 = positions[parent]
        x2, y2 = positions[child]
        is_path = (parent, child) in path_edges
        color = PATH if is_path else REAL
        width = 2.6 if is_path else 1.7
        parts.append(
            f'<path d="{bezier(x1, y1, x2, y2)}" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-opacity="0.92"/>'
        )
        if labels_drawn < label_budget and (is_path or len(edges) <= 18):
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            parts.append(svg_text([truncate(tactic, 42)], mx + 4, my - 5, 10, color, family="ui-monospace, SFMono-Regular, Menlo, monospace"))
            labels_drawn += 1

    root = tree["root_mvar_id"]
    for node_id, node in nodes.items():
        x, y = positions[node_id]
        if node_id == root:
            fill, stroke, radius = INK, INK, 6.4
        elif node.get("is_terminal"):
            fill, stroke, radius = TERM, TERM, 5.2
        else:
            fill, stroke, radius = "#ffffff", REAL, 4.6
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.7"/>'
        )

    return "".join(parts), {
        "nodes": n_nodes,
        "edges": n_edges,
        "depth": max_depth,
        "ghosts": n_ghosts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair-dir", type=Path, required=True)
    parser.add_argument("--intervention", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-label", default="")
    parser.add_argument("--ghosts-per-node", type=int, default=3)
    parser.add_argument("--fallback-id", default="wonton_theorem")
    args = parser.parse_args()

    pair_dir = args.pair_dir
    intervention = args.intervention
    wild_tree = read_json(pair_dir / "wild_type_mcts_tree.json")
    int_tree = read_json(pair_dir / f"{intervention}_mcts_tree.json")
    wild_metrics = read_json(pair_dir / "wild_type_metrics.json") if (pair_dir / "wild_type_metrics.json").exists() else None
    int_metrics = read_json(pair_dir / f"{intervention}_metrics.json") if (pair_dir / f"{intervention}_metrics.json").exists() else None
    comp_path = pair_dir / f"{intervention}_comparison.json"
    comparison = read_json(comp_path) if comp_path.exists() else {}

    theorem = clean_theorem(pair_dir, intervention, args.fallback_id)
    blocked = comparison.get("blocked") or []
    blocked_label = ", ".join(blocked) if blocked else intervention.replace("block_", "")
    ged = (comparison.get("ged_search_graph") or {}).get("normalized")
    soft = (comparison.get("ged_search_graph_soft") or {}).get("normalized")

    blocked_attempts = trace_blocked(pair_dir / f"{intervention}_mcts_trace.jsonl")
    reroute = first_reroute(wild_metrics, int_metrics)
    callout = [
        f"blocked tactic: {blocked_label}",
        f"blocked attempts: {len(blocked_attempts)}",
    ]
    if reroute:
        callout.append("reroute: " + " -> ".join(truncate(t, 18) for t in reroute[:2]))

    width, height = 1800, 1200
    margin = 62
    top_h = 252
    panel_y = 302
    panel_h = 760
    gutter = 52
    panel_w = (width - 2 * margin - gutter) / 2
    left_x = margin
    right_x = margin + panel_w + gutter

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    parts.append(svg_text(["Wonton Soup"], margin, 54, 25, INK, weight="800"))
    parts.append(svg_text(["baseline search vs tactic intervention, from real Lean MCTS logs"], margin, 82, 17, MUTED))
    if args.run_label:
        parts.append(svg_text([args.run_label], width - margin, 56, 15, MUTED, anchor="end"))

    theorem_lines = wrap_lines(theorem, 106)
    theorem_box_h = min(156, 26 + 22 * len(theorem_lines))
    parts.append(
        f'<rect x="{margin:.1f}" y="108" width="{width - 2 * margin:.1f}" height="{theorem_box_h:.1f}" '
        f'rx="10" fill="#fbfcfd" stroke="{PANEL_STROKE}" stroke-width="1"/>'
    )
    parts.append(svg_text(["theorem"], margin + 20, 133, 13, MUTED, weight="700"))
    parts.append(
        svg_text(
            theorem_lines[:6],
            margin + 20,
            160,
            17,
            INK,
            family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            line_height=1.22,
        )
    )
    if len(theorem_lines) > 6:
        parts.append(svg_text(["..."], margin + 20, 160 + 17 * 1.22 * 6, 17, INK, family="ui-monospace, SFMono-Regular, Menlo, monospace"))

    legend = "solid = expanded goal states; pale = proposed/failed trace branches; red = blocked by intervention"
    if ged is not None:
        legend += f"; GED={ged:.2f}"
        if soft is not None:
            legend += f" / soft={soft:.2f}"
    parts.append(svg_text([legend], margin, top_h + 18, 15, MUTED))

    wild_panel, _ = draw_graph_panel(
        wild_tree,
        wild_metrics,
        pair_dir / "wild_type_mcts_trace.jsonl",
        "wild type",
        "unmodified tactic policy",
        left_x,
        panel_y,
        panel_w,
        panel_h,
        args.ghosts_per_node,
        highlight_blocked=False,
    )
    int_panel, _ = draw_graph_panel(
        int_tree,
        int_metrics,
        pair_dir / f"{intervention}_mcts_trace.jsonl",
        intervention.replace("_", " "),
        "same theorem, one tactic family blocked",
        right_x,
        panel_y,
        panel_w,
        panel_h,
        args.ghosts_per_node,
        callout=callout,
    )
    parts.extend([wild_panel, int_panel])

    # A restrained Wonton layer mark between the panels.
    cx = width / 2
    parts.append(f'<line x1="{cx:.1f}" y1="{panel_y + 14:.1f}" x2="{cx:.1f}" y2="{panel_y + panel_h - 14:.1f}" stroke="#d7dee6" stroke-width="1"/>')
    parts.append(svg_text(["intervention mask"], cx, panel_y + panel_h + 34, 14, MUTED, anchor="middle"))

    parts.append("</svg>")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(parts))


if __name__ == "__main__":
    main()
