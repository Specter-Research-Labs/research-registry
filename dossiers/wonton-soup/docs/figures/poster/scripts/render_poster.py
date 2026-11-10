#!/usr/bin/env python3
"""Render the Wonton Soup poster deterministically from block-exact MCTS logs.

Every solid edge is copied from the MCTS tree JSON, every accepted tactic label
is the exact edge label from the tree, and every red blocked stub is a blocked
`exact` attempt from the intervention trace.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import textwrap
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

THEOREM_ID = "hf_deepseek_prover_v1_train_00795"
BG = "#f8f5ee"
INK = "#24211d"
MUTED = "#736d63"
TEAL = "#111111"
TEAL_DARK = "#2f7f53"
AMBER = "#b9852d"
PALE = "#c9c2b7"
PALE_TEXT = "#7a8c98"
BLOCK = "#cb3e32"
GREEN = "#2f7f53"
GREY = "#aba397"
MUTED_GREEN = "#9faf94"
GOAL_TEXT = "#4b5c52"
GOAL_RULE = "#d7a64b"
CHIP = "#ebe3d5"
GRID = "#e4dbcd"
FONT = "Berkeley Mono, BerkeleyMono, ui-monospace, SFMono-Regular, Menlo, monospace"


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


def norm_tactic(tactic: str) -> str:
    return re.sub(r"\s+", " ", tactic.strip())


def layout_vertical(
    tree: dict[str, Any],
    x: float,
    y: float,
    w: float,
    h: float,
    wiggle: bool = False,
) -> dict[str, tuple[float, float]]:
    nodes = tree["nodes"]
    edges = tree_edges(tree)
    children: dict[str, list[str]] = defaultdict(list)
    for parent, child, _ in edges:
        children[parent].append(child)
    root = tree["root_mvar_id"]

    leaf_index: dict[str, float] = {}
    order = 0

    def assign(node_id: str) -> float:
        nonlocal order
        kids = [kid for kid in children.get(node_id, []) if kid in nodes]
        if not kids:
            leaf_index[node_id] = float(order)
            order += 1
            return leaf_index[node_id]
        vals = [assign(kid) for kid in kids]
        leaf_index[node_id] = sum(vals) / len(vals)
        return leaf_index[node_id]

    assign(root)
    leaf_count = max(order, 1)
    max_depth = max((node.get("depth") or 0) for node in nodes.values()) or 1
    positions: dict[str, tuple[float, float]] = {}
    for node_id, node in nodes.items():
        depth = node.get("depth") or 0
        yy = y + (h * depth / max_depth)
        if leaf_count == 1:
            xx = x + w / 2 + (math.sin(depth * 0.9) * 36 if wiggle else 0)
        else:
            xx = x + 26 + (w - 52) * (leaf_index[node_id] + 0.5) / leaf_count
        positions[node_id] = (xx, yy)
    return positions


def trace_winner(trace_path: Path) -> dict[str, Any]:
    """Return the first solved terminal path recorded by the MCTS trace."""
    for line in trace_path.open():
        event = json.loads(line)
        if not (event.get("terminal_reached") and event.get("backprop_success")):
            continue
        selected_path = event.get("selected_path") or []
        terminal_tactic = None
        for attempt in event.get("attempts") or []:
            if attempt.get("outcome") == "success" and not attempt.get("child_mvar_ids"):
                terminal_tactic = attempt.get("tactic") or attempt.get("tactic_norm")
                break
        return {
            "selected_path": selected_path,
            "terminal_node": selected_path[-1] if selected_path else None,
            "terminal_tactic": terminal_tactic,
            "iteration": event.get("iteration"),
        }
    return {"selected_path": [], "terminal_node": None, "terminal_tactic": None, "iteration": None}


def terminal_closers(tree: dict[str, Any]) -> dict[str, list[str]]:
    closers: dict[str, list[str]] = {}
    for node_id, node in tree["nodes"].items():
        tactics = [
            tactic
            for tactic, children in (node.get("children") or {}).items()
            if not children
        ]
        if tactics:
            closers[node_id] = tactics
    return closers


@dataclass(frozen=True)
class Ghost:
    tactic: str
    outcome: str
    score: float | None = None
    block_reason: str | None = None


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


def bezier(x1: float, y1: float, x2: float, y2: float) -> str:
    dx = max(24, abs(x2 - x1) * 0.42)
    return f"M{x1:.1f},{y1:.1f} C{x1+dx:.1f},{y1:.1f} {x2-dx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"


def truncate(text: str, width: int) -> str:
    text = norm_tactic(text)
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)].rstrip() + "…"


def draw_ghosts(
    parts: list[str],
    *,
    tree: dict[str, Any],
    trace_path: Path,
    positions: dict[str, tuple[float, float]],
    blocked_by_node: dict[str, list[str]] | None,
    neutral_only: bool,
    x: float,
    y: float,
    w: float,
    h: float,
    blocked_label_limit: int = 3,
) -> list[dict[str, Any]]:
    ghosts = collect_ghosts(trace_path, tree, 3)
    blocked_labels_drawn = 0
    displayed_muted_attempts: list[dict[str, Any]] = []
    for node_id, items in ghosts.items():
        if node_id not in positions:
            continue
        node_depth = tree["nodes"].get(node_id, {}).get("depth") or 0
        sx, sy = positions[node_id]
        drawn = 0
        # Draw blocked exact attempts explicitly from trace so red never appears
        # on baseline and never represents accepted proof edges.
        if not neutral_only and blocked_by_node and blocked_by_node.get(node_id):
            for tactic in blocked_by_node[node_id][:2]:
                angle = -0.85 if drawn % 2 == 0 else 0.85
                length = 54
                gx = sx + math.cos(angle) * length
                gy = sy + math.sin(angle) * length
                parts.append(
                    f'<path d="{bezier(sx, sy, gx, gy)}" fill="none" stroke="{GREY}" '
                    f'stroke-width="2.1" stroke-opacity="0.75"/>'
                )
                parts.append(f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="8.4" fill="{BG}" stroke="{BLOCK}" stroke-width="2"/>')
                parts.append(
                    f'<path d="M{gx-4.2:.1f},{gy-4.2:.1f} L{gx+4.2:.1f},{gy+4.2:.1f} '
                    f'M{gx+4.2:.1f},{gy-4.2:.1f} L{gx-4.2:.1f},{gy+4.2:.1f}" '
                    f'stroke="{BLOCK}" stroke-width="2" stroke-linecap="round"/>'
                )
                if blocked_labels_drawn < blocked_label_limit:
                    label_y = gy - 13 if angle < 0 else gy + 19
                    if gx > x + w - 130:
                        parts.append(
                            svg_text(
                                ["blocked: exact"],
                                gx - 13,
                                label_y,
                                10.5,
                                BLOCK,
                                FONT,
                                anchor="end",
                            )
                        )
                    else:
                        parts.append(svg_text(["blocked: exact"], gx + 13, label_y, 10.5, BLOCK, FONT))
                    blocked_labels_drawn += 1
                drawn += 1

        pale_drawn = 0
        for ghost in items:
            if pale_drawn >= 2:
                break
            if ghost.outcome == "success":
                continue
            if blocked_by_node and norm_tactic(ghost.tactic).startswith("exact"):
                continue
            side = -1 if pale_drawn % 2 == 0 else 1
            gx = sx + side * (42 + 10 * pale_drawn)
            gy = sy + 34 + 12 * pale_drawn
            gx = max(x + 12, min(x + w - 12, gx))
            gy = max(y - 18, min(y + h + 18, gy))
            parts.append(
                f'<path d="{bezier(sx, sy, gx, gy)}" fill="none" stroke="{PALE}" '
                f'stroke-width="1.25" stroke-dasharray="4 6" stroke-opacity="0.54"/>'
            )
            parts.append(f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="4.6" fill="{BG}" stroke="{PALE}" stroke-width="1.3" opacity="0.85"/>')
            show_muted_label = node_depth <= 1 and (neutral_only or pale_drawn == 0)
            if show_muted_label:
                label = truncate(ghost.tactic, 18 if neutral_only else 14)
                anchor = "end" if gx < sx else "start"
                lx = gx - 8 if gx < sx else gx + 8
                parts.append(
                    svg_text(
                        [label],
                        lx,
                        gy - 7,
                        11 if neutral_only else 10,
                        PALE_TEXT,
                        FONT,
                        anchor=anchor,
                    )
                )
                displayed_muted_attempts.append(
                    {
                        "node": node_id,
                        "tactic": ghost.tactic,
                        "label": label,
                        "outcome": ghost.outcome,
                    }
                )
            pale_drawn += 1
    return displayed_muted_attempts


def incoming_tactics(tree: dict[str, Any]) -> dict[str, str]:
    incoming: dict[str, str] = {}
    for _parent, child, tactic in tree_edges(tree):
        incoming[child] = tactic
    return incoming


def choose_snapshot_nodes(winner_path: list[str], max_count: int = 3) -> list[str]:
    if max_count <= 0:
        return []
    candidates = winner_path[1:]
    if len(candidates) <= max_count:
        return candidates
    if max_count == 2:
        return [candidates[len(candidates) // 2], candidates[-1]]
    last = len(candidates) - 1
    idxs = sorted({round((i + 1) * last / max_count) for i in range(max_count)})
    return [candidates[i] for i in idxs]


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


def goal_snapshot_lines(goal: str, *, width: int = 29, max_lines: int = 4) -> list[str]:
    lines = wrap_lines(goal, width)
    if len(lines) <= max_lines:
        return lines
    return lines[: max_lines - 1] + ["…"]


def draw_goal_snapshots(
    parts: list[str],
    *,
    tree: dict[str, Any],
    positions: dict[str, tuple[float, float]],
    winner_path: list[str],
    x: float,
    y: float,
    w: float,
    h: float,
    side_pattern: tuple[int, ...],
    max_count: int,
) -> list[dict[str, Any]]:
    incoming = incoming_tactics(tree)
    snapshots: list[dict[str, Any]] = []
    nodes = choose_snapshot_nodes(winner_path, max_count=max_count)
    for idx, node_id in enumerate(nodes):
        if node_id not in tree["nodes"] or node_id not in positions:
            continue
        goal = tree["nodes"][node_id].get("goal_type") or ""
        if not goal:
            continue
        sx, sy = positions[node_id]
        side = side_pattern[idx % len(side_pattern)]
        label_x = sx + side * (96 if w < 440 else 150)
        label_x = max(x + 18, min(x + w - 18, label_x))
        label_y = max(y + 6, min(y + h - 76, sy - 18 + idx * 4))
        anchor = "start" if side > 0 else "end"
        rule_x = label_x - 8 if anchor == "start" else label_x + 8
        leader_end_y = label_y + 8
        display_lines = goal_snapshot_lines(goal)
        height = 18 + 8 * len(display_lines)
        parts.append(
            f'<path d="M{sx:.1f},{sy:.1f} C{(sx+rule_x)/2:.1f},{sy:.1f} '
            f'{(sx+rule_x)/2:.1f},{leader_end_y:.1f} {rule_x:.1f},{leader_end_y:.1f}" '
            f'fill="none" stroke="{GOAL_RULE}" stroke-width="0.9" stroke-opacity="0.42"/>'
        )
        parts.append(
            f'<path d="M{rule_x:.1f},{label_y-7:.1f} L{rule_x:.1f},{label_y+height:.1f}" '
            f'stroke="{GOAL_RULE}" stroke-width="1.2" stroke-opacity="0.66" stroke-linecap="round"/>'
        )
        tactic = incoming.get(node_id, "")
        title = f"after {truncate(tactic, 18)}" if tactic else "goal"
        parts.append(
            svg_text(
                [title],
                label_x,
                label_y,
                8.5,
                MUTED,
                FONT,
                "400",
                anchor=anchor,
            )
        )
        parts.append(
            svg_text(
                display_lines,
                label_x,
                label_y + 12,
                8.5,
                GOAL_TEXT,
                FONT,
                line_height=1.18,
                anchor=anchor,
            )
        )
        snapshots.append(
            {
                "node": node_id,
                "incoming_tactic": tactic,
                "goal_type": goal,
                "display_lines": display_lines,
            }
        )
    return snapshots


def trace_blocked_exact(trace_path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for line in trace_path.open():
        event = json.loads(line)
        node_id = (event.get("node") or {}).get("mvar_id")
        if not node_id:
            continue
        for attempt in event.get("attempts") or []:
            tactic = attempt.get("tactic") or attempt.get("tactic_norm") or ""
            if (attempt.get("outcome") == "blocked" or attempt.get("block_reason")) and norm_tactic(tactic).startswith("exact"):
                out[node_id].append(tactic)
    return out


def vertical_bezier_points(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]:
    dy = max(32, abs(y2 - y1) * 0.46)
    return (x1, y1), (x1, y1 + dy), (x2, y2 - dy), (x2, y2)


def cubic_point(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    u = 1 - t
    x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
    return x, y


def cubic_tangent(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    u = 1 - t
    dx = 3 * u**2 * (p1[0] - p0[0]) + 6 * u * t * (p2[0] - p1[0]) + 3 * t**2 * (p3[0] - p2[0])
    dy = 3 * u**2 * (p1[1] - p0[1]) + 6 * u * t * (p2[1] - p1[1]) + 3 * t**2 * (p3[1] - p2[1])
    return dx, dy


def arrowhead(parts: list[str], x1: float, y1: float, x2: float, y2: float, color: str) -> None:
    p0, p1, p2, p3 = vertical_bezier_points(x1, y1, x2, y2)
    mx, my = cubic_point(p0, p1, p2, p3, 0.55)
    dx, dy = cubic_tangent(p0, p1, p2, p3, 0.55)
    length = max(math.hypot(dx, dy), 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    size = 8
    p1 = (mx + ux * size, my + uy * size)
    p2 = (mx - ux * size * 0.72 + px * size * 0.46, my - uy * size * 0.72 + py * size * 0.46)
    p3 = (mx - ux * size * 0.72 - px * size * 0.46, my - uy * size * 0.72 - py * size * 0.46)
    parts.append(
        f'<path d="M{p1[0]:.1f},{p1[1]:.1f} L{p2[0]:.1f},{p2[1]:.1f} L{p3[0]:.1f},{p3[1]:.1f} Z" '
        f'fill="{color}" opacity="0.9"/>'
    )


def vertical_bezier(x1: float, y1: float, x2: float, y2: float) -> str:
    p0, p1, p2, p3 = vertical_bezier_points(x1, y1, x2, y2)
    return f"M{p0[0]:.1f},{p0[1]:.1f} C{p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f} {p3[0]:.1f},{p3[1]:.1f}"


def draw_tree(
    parts: list[str],
    *,
    tree: dict[str, Any],
    trace_path: Path,
    title: str,
    subtitle: str | None,
    x: float,
    y: float,
    w: float,
    h: float,
    neutral_ghosts: bool,
    wiggle: bool = False,
    snapshot_sides: tuple[int, ...] = (-1, 1, -1),
    snapshot_count: int = 3,
    outcome_label: str | None = None,
    subtitle_color: str = BLOCK,
    blocked_label_limit: int = 3,
) -> dict[str, Any]:
    positions = layout_vertical(tree, x, y, w, h, wiggle=wiggle)
    blocked = {} if neutral_ghosts else trace_blocked_exact(trace_path)
    winner = trace_winner(trace_path)
    winner_path = winner["selected_path"]
    winner_edges = set(zip(winner_path, winner_path[1:]))
    winner_terminal = winner["terminal_node"]
    closers = terminal_closers(tree)
    cx = x + w / 2

    parts.append(svg_text([title], cx, y - 88, 25, INK, FONT, "700", anchor="middle"))
    if subtitle:
        parts.append(svg_text([subtitle], cx, y - 60, 14, subtitle_color, FONT, "400", anchor="middle"))

    displayed_muted_attempts = draw_ghosts(
        parts,
        tree=tree,
        trace_path=trace_path,
        positions=positions,
        blocked_by_node=blocked,
        neutral_only=neutral_ghosts,
        x=x,
        y=y,
        w=w,
        h=h,
        blocked_label_limit=blocked_label_limit,
    )

    edges = tree_edges(tree)
    for winner_pass in (False, True):
        for parent, child, tactic in edges:
            is_winner = (parent, child) in winner_edges
            if is_winner != winner_pass:
                continue
            x1, y1 = positions[parent]
            x2, y2 = positions[child]
            color = TEAL if is_winner else GREY
            width = 4.7 if is_winner else 1.55
            opacity = 0.98 if is_winner else 0.45
            parts.append(
                f'<path d="{vertical_bezier(x1, y1, x2, y2)}" fill="none" stroke="{color}" '
                f'stroke-width="{width}" stroke-linecap="round" stroke-opacity="{opacity}"/>'
            )
            if is_winner:
                arrowhead(parts, x1, y1, x2, y2, color)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if is_winner or len(edges) <= 8:
                label_color = TEAL_DARK if is_winner else "#8b877e"
                parts.append(
                    svg_text(
                        [tactic],
                        mx + 8,
                        my,
                        15,
                        label_color,
                        FONT,
                    )
                )

    solved_leaf_positions: dict[str, list[tuple[str, float, float, bool]]] = {}
    for node_id, tactics in closers.items():
        sx, sy = positions[node_id]
        solved_leaf_positions[node_id] = []
        for idx, tactic in enumerate(tactics):
            is_winner = node_id == winner_terminal and (
                not winner["terminal_tactic"]
                or norm_tactic(tactic) == norm_tactic(winner["terminal_tactic"])
            )
            dx = 0 if len(tactics) == 1 else (idx - (len(tactics) - 1) / 2) * 36
            ex = sx + dx
            ey = sy + (58 if is_winner else 44)
            color = TEAL if is_winner else GREY
            width = 4.2 if is_winner else 1.45
            opacity = 0.98 if is_winner else 0.42
            parts.append(
                f'<path d="{vertical_bezier(sx, sy, ex, ey)}" fill="none" stroke="{color}" '
                f'stroke-width="{width}" stroke-linecap="round" stroke-opacity="{opacity}"/>'
            )
            if is_winner:
                arrowhead(parts, sx, sy, ex, ey, color)
            leaf_color = GREEN if is_winner else MUTED_GREEN
            leaf_opacity = 1.0 if is_winner else 0.48
            parts.append(
                f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="{11.5 if is_winner else 7.5}" '
                f'fill="{leaf_color}" stroke="{leaf_color}" stroke-width="2" opacity="{leaf_opacity}"/>'
            )
            label_color = TEAL_DARK if is_winner else "#8b877e"
            if is_winner or len(edges) <= 8:
                label_x = ex + (30 if is_winner else 9)
                label_y = ey + (-14 if is_winner else -4)
                label_size = 12 if is_winner and outcome_label else 15
                parts.append(
                    svg_text(
                        [tactic],
                        label_x,
                        label_y,
                        label_size,
                        label_color,
                        FONT,
                    )
                )
            if is_winner:
                parts.append(svg_text(["solved"], ex, ey + 32, 14, GREEN, FONT, anchor="middle"))
                if outcome_label:
                    badge_w = 112
                    badge_x = ex - badge_w / 2
                    badge_y = ey + 44
                    parts.append(
                        f'<rect x="{badge_x:.1f}" y="{badge_y:.1f}" width="{badge_w}" height="20" rx="10" '
                        f'fill="#e8f1e5" stroke="{GREEN}" stroke-width="0.8" stroke-opacity="0.35" opacity="0.94"/>'
                    )
                    parts.append(
                        svg_text(
                            [outcome_label],
                            badge_x + badge_w / 2,
                            badge_y + 13.5,
                            8.6,
                            TEAL_DARK,
                            FONT,
                            "500",
                            anchor="middle",
                        )
                    )
            solved_leaf_positions[node_id].append((tactic, ex, ey, is_winner))

    goal_snapshots = draw_goal_snapshots(
        parts,
        tree=tree,
        positions=positions,
        winner_path=winner_path,
        x=x,
        y=y,
        w=w,
        h=h,
        side_pattern=snapshot_sides,
        max_count=snapshot_count,
    )

    for node_id, node in tree["nodes"].items():
        px, py = positions[node_id]
        if node_id == tree["root_mvar_id"]:
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="9.8" fill="{BG}" stroke="{INK}" stroke-width="2.2"/>')
        elif node.get("is_terminal"):
            stroke = GREEN if node_id == winner_terminal else GREY
            width = 2.4 if node_id == winner_terminal else 1.5
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="8.4" fill="{BG}" stroke="{stroke}" stroke-width="{width}"/>')
        else:
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="7.8" fill="{BG}" stroke="{INK}" stroke-width="1.8"/>')

    return {
        "edges": [{"parent": p, "child": c, "tactic": t} for p, c, t in edges],
        "winner": winner,
        "winner_edges": [{"parent": p, "child": c} for p, c in winner_edges],
        "terminal_closers": closers,
        "blocked_exact_attempts": blocked,
        "displayed_muted_attempts": displayed_muted_attempts,
        "goal_snapshots": goal_snapshots,
    }


def start_svg(width: int, height: int) -> list[str]:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<pattern id="grid" width="42" height="42" patternUnits="userSpaceOnUse">'
        f'<path d="M42 0H0V42" fill="none" stroke="{GRID}" stroke-width="0.9" opacity="0.72"/>'
        "</pattern>",
        '<pattern id="grain" width="90" height="90" patternUnits="userSpaceOnUse">'
        '<circle cx="16" cy="21" r="0.8" fill="#eadfcd"/>'
        '<circle cx="70" cy="52" r="0.65" fill="#efe4d2"/></pattern>',
        "</defs>",
        f'<rect width="100%" height="100%" fill="{BG}"/>',
        '<rect width="100%" height="100%" fill="url(#grid)" opacity="0.64"/>',
        '<rect width="100%" height="100%" fill="url(#grain)" opacity="0.25"/>',
    ]
    return parts


def text(
    parts: list[str],
    lines: list[str],
    x: float,
    y: float,
    size: float,
    fill: str,
    *,
    weight: str = "400",
    anchor: str = "start",
    line_height: float = 1.25,
) -> None:
    parts.append(
        svg_text(
            lines,
            x,
            y,
            size,  # type: ignore[arg-type]
            fill,
            FONT,
            weight,
            line_height,
            anchor,
        )
    )


def draw_chip(parts: list[str], x: float, y: float, label: str, value: str) -> None:
    parts.append(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="178" height="46" rx="7" '
        f'fill="{CHIP}" stroke="{GRID}" stroke-width="0.8" opacity="0.92"/>'
    )
    text(parts, [label], x + 14, y + 17, 8.5, MUTED, weight="700")
    text(parts, [value], x + 14, y + 35, 12, INK, weight="700")


def render_poster(
    *,
    theorem: str,
    wild_tree: dict[str, Any],
    int_tree: dict[str, Any],
    pair_dir: Path,
    intervention: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    parts = start_svg(1200, 1800)
    text(parts, ["Wonton Soup"], 80, 92, 44, INK, weight="700")
    text(parts, ["proof graph blueprint / matched-budget perturbation"], 84, 130, 15, AMBER)
    text(parts, wrap_lines(theorem, 74), 82, 184, 10.5, MUTED, line_height=1.22)
    draw_chip(parts, 770, 78, "wild close", "exact H''")
    draw_chip(parts, 968, 78, "lesion close", "rintro ⟨⟩")
    text(parts, ["red X = blocked exact"], 968, 260, 10.5, BLOCK)
    parts.append(f'<path d="M70 1030H1130" stroke="{AMBER}" stroke-width="1.2" stroke-dasharray="8 8" opacity="0.45"/>')
    baseline = draw_tree(
        parts,
        tree=wild_tree,
        trace_path=pair_dir / "wild_type_mcts_trace.jsonl",
        title="wild type",
        subtitle="unlesioned route",
        x=105,
        y=430,
        w=990,
        h=470,
        neutral_ghosts=True,
        wiggle=False,
        snapshot_count=1,
        subtitle_color=MUTED,
    )
    intervention_data = draw_tree(
        parts,
        tree=int_tree,
        trace_path=pair_dir / f"{intervention}_mcts_trace.jsonl",
        title="intervention",
        subtitle="block exact; alternate proof family",
        x=105,
        y=1185,
        w=990,
        h=390,
        neutral_ghosts=False,
        snapshot_sides=(1, -1, 1),
        snapshot_count=1,
        outcome_label="reroute",
        subtitle_color=BLOCK,
        blocked_label_limit=0,
    )
    text(parts, ["same theorem, same budget class, different structural route"], 600, 1718, 12, MUTED, anchor="middle")
    parts.append("</svg>")
    return "\n".join(parts), baseline, intervention_data


def theorem_id_from_text(text: str, fallback: str) -> str:
    match = re.search(r"hf_deepseek_prover_v1_train_\d+", text)
    return match.group(0) if match else fallback


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


def read_json(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair-dir", type=Path, required=True)
    parser.add_argument("--intervention", default="block_exact")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    theorem = clean_theorem(args.pair_dir, args.intervention, THEOREM_ID)
    wild_tree = read_json(args.pair_dir / "wild_type_mcts_tree.json")
    int_tree = read_json(args.pair_dir / f"{args.intervention}_mcts_tree.json")
    svg, baseline, intervention = render_poster(
        theorem=theorem,
        wild_tree=wild_tree,
        int_tree=int_tree,
        pair_dir=args.pair_dir,
        intervention=args.intervention,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(svg)

    if args.manifest:
        args.manifest.write_text(
            json.dumps(
                {
                    "take": "blueprint-ledger",
                    "theorem": theorem,
                    "baseline": baseline,
                    "intervention": intervention,
                    "baseline_red_or_blocked_drawn": False,
                    "source_files": {
                        "wild_tree": str(args.pair_dir / "wild_type_mcts_tree.json"),
                        "wild_trace": str(args.pair_dir / "wild_type_mcts_trace.jsonl"),
                        "intervention_tree": str(args.pair_dir / f"{args.intervention}_mcts_tree.json"),
                        "intervention_trace": str(args.pair_dir / f"{args.intervention}_mcts_trace.jsonl"),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
