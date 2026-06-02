#!/usr/bin/env python3
"""Publication-safe Wonton Soup poster.

This is intentionally deterministic: every solid edge is copied from the MCTS
tree JSON, every accepted tactic label is the exact edge label from the tree,
and every red blocked stub is a blocked `exact` attempt from the intervention
trace. No image-generation redraw is involved.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import render_pair as rp


BG = "#fbf6ed"
INK = "#282623"
MUTED = "#766f63"
TEAL = "#0d8178"
TEAL_DARK = "#0b625e"
AMBER = "#dda43f"
PALE = "#a9c9da"
PALE_TEXT = "#789bae"
BLOCK = "#d94b25"
GREEN = "#2d9859"
GREY = "#afa79b"
MUTED_GREEN = "#9fb69d"
GOAL_TEXT = "#586a65"
GOAL_RULE = "#d9b870"
FONT = "Berkeley Mono, BerkeleyMono, ui-monospace, SFMono-Regular, Menlo, monospace"


def vertical_bezier_points(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]:
    dy = max(32, abs(y2 - y1) * 0.46)
    return (x1, y1), (x1, y1 + dy), (x2, y2 - dy), (x2, y2)


def vertical_bezier(x1: float, y1: float, x2: float, y2: float) -> str:
    p0, p1, p2, p3 = vertical_bezier_points(x1, y1, x2, y2)
    return f"M{p0[0]:.1f},{p0[1]:.1f} C{p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f} {p3[0]:.1f},{p3[1]:.1f}"


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


def layout_vertical(
    tree: dict[str, Any],
    x: float,
    y: float,
    w: float,
    h: float,
    wiggle: bool = False,
) -> dict[str, tuple[float, float]]:
    nodes = tree["nodes"]
    edges = rp.tree_edges(tree)
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


def trace_blocked_exact(trace_path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for line in trace_path.open():
        event = json.loads(line)
        node_id = (event.get("node") or {}).get("mvar_id")
        if not node_id:
            continue
        for attempt in event.get("attempts") or []:
            tactic = attempt.get("tactic") or attempt.get("tactic_norm") or ""
            if (attempt.get("outcome") == "blocked" or attempt.get("block_reason")) and rp.norm_tactic(tactic).startswith("exact"):
                out[node_id].append(tactic)
    return out


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


def incoming_tactics(tree: dict[str, Any]) -> dict[str, str]:
    incoming: dict[str, str] = {}
    for _parent, child, tactic in rp.tree_edges(tree):
        incoming[child] = tactic
    return incoming


def goal_snapshot_lines(goal: str, *, width: int = 29, max_lines: int = 4) -> list[str]:
    lines = rp.wrap_lines(goal, width)
    if len(lines) <= max_lines:
        return lines
    return lines[: max_lines - 1] + ["…"]


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
        title = f"after {rp.truncate(tactic, 18)}" if tactic else "goal"
        parts.append(
            rp.svg_text(
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
            rp.svg_text(
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
    ghosts = rp.collect_ghosts(trace_path, tree, 3)
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
                    f'<path d="{rp.bezier(sx, sy, gx, gy)}" fill="none" stroke="{GREY}" '
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
                            rp.svg_text(
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
                        parts.append(rp.svg_text(["blocked: exact"], gx + 13, label_y, 10.5, BLOCK, FONT))
                    blocked_labels_drawn += 1
                drawn += 1

        pale_drawn = 0
        for ghost in items:
            if pale_drawn >= 2:
                break
            if ghost.outcome == "success":
                continue
            if blocked_by_node and rp.norm_tactic(ghost.tactic).startswith("exact"):
                continue
            side = -1 if pale_drawn % 2 == 0 else 1
            gx = sx + side * (42 + 10 * pale_drawn)
            gy = sy + 34 + 12 * pale_drawn
            gx = max(x + 12, min(x + w - 12, gx))
            gy = max(y - 18, min(y + h + 18, gy))
            parts.append(
                f'<path d="{rp.bezier(sx, sy, gx, gy)}" fill="none" stroke="{PALE}" '
                f'stroke-width="1.25" stroke-dasharray="4 6" stroke-opacity="0.54"/>'
            )
            parts.append(f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="4.6" fill="{BG}" stroke="{PALE}" stroke-width="1.3" opacity="0.85"/>')
            show_muted_label = node_depth <= 1 and (neutral_only or pale_drawn == 0)
            if show_muted_label:
                label = rp.truncate(ghost.tactic, 18 if neutral_only else 14)
                anchor = "end" if gx < sx else "start"
                lx = gx - 8 if gx < sx else gx + 8
                parts.append(
                    rp.svg_text(
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


def draw_story_ribbon(parts: list[str], *, width: float, y: float) -> None:
    labels = [
        ("block exact", BLOCK),
        ("reroute", TEAL_DARK),
        ("solved", GREEN),
    ]
    xs = [width / 2 - 155, width / 2, width / 2 + 155]
    for i in range(len(xs) - 1):
        x1, x2 = xs[i] + 58, xs[i + 1] - 58
        parts.append(
            f'<path d="M{x1:.1f},{y:.1f} C{x1+34:.1f},{y:.1f} {x2-34:.1f},{y:.1f} {x2:.1f},{y:.1f}" '
            f'fill="none" stroke="{AMBER}" stroke-width="1.1" stroke-opacity="0.52"/>'
        )
        parts.append(
            f'<path d="M{x2-6:.1f},{y-4:.1f} L{x2:.1f},{y:.1f} L{x2-6:.1f},{y+4:.1f}" '
            f'fill="none" stroke="{AMBER}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" opacity="0.7"/>'
        )
    for x, (label, color) in zip(xs, labels):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.2" fill="{color}" opacity="0.92"/>')
        parts.append(
            rp.svg_text(
                [label],
                x,
                y + 24,
                12,
                color,
                FONT,
                "500",
                anchor="middle",
            )
        )


def draw_legend(parts: list[str], *, width: float, y: float) -> None:
    items = [
        ("winning route", TEAL),
        ("explored frontier", GREY),
        ("blocked exact", BLOCK),
        ("solved", GREEN),
    ]
    start_x = width / 2 - 255
    for idx, (label, color) in enumerate(items):
        x = start_x + idx * 170
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.3" fill="{color}" opacity="0.9"/>')
        parts.append(
            rp.svg_text(
                [label],
                x + 11,
                y + 4,
                10,
                MUTED if color != BLOCK else BLOCK,
                FONT,
            )
        )


def draw_caption(parts: list[str], *, width: float, y: float, text: str) -> None:
    parts.append(
        rp.svg_text(
            [text],
            width / 2,
            y,
            11,
            MUTED,
            FONT,
            "400",
            anchor="middle",
        )
    )


def draw_response_modes(parts: list[str], *, width: float, y: float) -> None:
    modes = [
        ("replicate", MUTED, False),
        ("reroute", TEAL_DARK, True),
        ("collapse", MUTED, False),
    ]
    start_x = width / 2 - 168
    for idx, (label, color, active) in enumerate(modes):
        x = start_x + idx * 168
        if active:
            parts.append(
                f'<rect x="{x-58:.1f}" y="{y-15:.1f}" width="116" height="30" rx="15" '
                f'fill="#e8f1e5" stroke="{GREEN}" stroke-width="0.8" stroke-opacity="0.45"/>'
            )
        parts.append(f'<circle cx="{x-42:.1f}" cy="{y:.1f}" r="3.8" fill="{color}" opacity="0.9"/>')
        parts.append(
            rp.svg_text(
                [label],
                x - 30,
                y + 4,
                10.5,
                color,
                FONT,
                "500" if active else "400",
            )
        )
    draw_caption(parts, width=width, y=y + 34, text="this paired run realizes the reroute response mode")


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

    parts.append(rp.svg_text([title], cx, y - 88, 25, INK, FONT, "700", anchor="middle"))
    if subtitle:
        parts.append(rp.svg_text([subtitle], cx, y - 60, 14, subtitle_color, FONT, "400", anchor="middle"))

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

    edges = rp.tree_edges(tree)
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
                    rp.svg_text(
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
                or rp.norm_tactic(tactic) == rp.norm_tactic(winner["terminal_tactic"])
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
                    rp.svg_text(
                        [tactic],
                        label_x,
                        label_y,
                        label_size,
                        label_color,
                        FONT,
                    )
                )
            if is_winner:
                parts.append(rp.svg_text(["solved"], ex, ey + 32, 14, GREEN, FONT, anchor="middle"))
                if outcome_label:
                    badge_w = 112
                    badge_x = ex - badge_w / 2
                    badge_y = ey + 44
                    parts.append(
                        f'<rect x="{badge_x:.1f}" y="{badge_y:.1f}" width="{badge_w}" height="20" rx="10" '
                        f'fill="#e8f1e5" stroke="{GREEN}" stroke-width="0.8" stroke-opacity="0.35" opacity="0.94"/>'
                    )
                    parts.append(
                        rp.svg_text(
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair-dir", type=Path, required=True)
    parser.add_argument("--intervention", default="block_exact")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--variant",
        choices=("hero", "ultra", "explanatory", "modes"),
        default="hero",
    )
    args = parser.parse_args()

    pair_dir = args.pair_dir
    theorem = rp.clean_theorem(pair_dir, args.intervention, "hf_deepseek_prover_v1_train_00795")
    wild_tree = rp.read_json(pair_dir / "wild_type_mcts_tree.json")
    int_tree = rp.read_json(pair_dir / f"{args.intervention}_mcts_tree.json")
    theorem_id = "hf_deepseek_prover_v1_train_00795"
    root_goal = wild_tree["nodes"][wild_tree["root_mvar_id"]]["goal_type"]
    target_line = root_goal.splitlines()[-1]
    visible_header = {
        "title": "Wonton Soup",
        "subtitle": "Collective perturbations reveal reroutes in proof search",
        "theorem_anchor": f"{theorem_id} · {target_line}",
        "story": ["block exact", "reroute", "solved"],
        "variant": args.variant,
    }

    width, height = 1200, 1800
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs>'
        '<pattern id="paper" width="90" height="90" patternUnits="userSpaceOnUse">'
        '<rect width="90" height="90" fill="#fbf6ed"/><circle cx="16" cy="21" r="0.8" fill="#eadfcd"/>'
        '<circle cx="70" cy="52" r="0.65" fill="#efe4d2"/></pattern>'
        '</defs>',
        f'<rect width="100%" height="100%" fill="{BG}"/>',
        '<rect width="100%" height="100%" fill="url(#paper)" opacity="0.32"/>',
    ]

    parts.append(rp.svg_text(["Wonton Soup"], width / 2, 82, 54, INK, FONT, "700", anchor="middle"))
    parts.append(
        rp.svg_text(
            ["Collective perturbations reveal reroutes in proof search"],
            width / 2,
            122,
            17,
            TEAL_DARK,
            FONT,
            "400",
            anchor="middle",
        )
    )
    pill_w = 660
    parts.append(f'<rect x="{(width-pill_w)/2:.1f}" y="150" width="{pill_w}" height="30" rx="7" fill="#f2e5ce" opacity="0.68"/>')
    parts.append(
        rp.svg_text(
            [visible_header["theorem_anchor"]],
            width / 2,
            170,
            11,
            MUTED,
            FONT,
            anchor="middle",
        )
    )
    if args.variant != "ultra":
        draw_story_ribbon(parts, width=width, y=220)
    if args.variant == "explanatory":
        draw_caption(
            parts,
            width=width,
            y=284,
            text="matched-budget rerun: blocking exact preserves success through a distinct proof route",
        )
    elif args.variant == "modes":
        draw_response_modes(parts, width=width, y=286)

    baseline = draw_tree(
        parts,
        tree=wild_tree,
        trace_path=pair_dir / "wild_type_mcts_trace.jsonl",
        title="wild type",
        subtitle="unlesioned run",
        x=78,
        y=430,
        w=425,
        h=1160,
        neutral_ghosts=True,
        wiggle=True,
        snapshot_sides=(-1, 1, -1),
        snapshot_count=0 if args.variant == "ultra" else 1,
        subtitle_color=MUTED,
    )
    intervention = draw_tree(
        parts,
        tree=int_tree,
        trace_path=pair_dir / f"{args.intervention}_mcts_trace.jsonl",
        title="lesion",
        subtitle="block exact",
        x=545,
        y=430,
        w=600,
        h=1160,
        neutral_ghosts=False,
        snapshot_sides=(-1, -1, -1),
        snapshot_count=0 if args.variant == "ultra" else 1,
        outcome_label="reroute recovered",
    )

    parts.append("</svg>")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(parts))

    if args.manifest:
        args.manifest.write_text(
            json.dumps(
                {
                    "theorem": theorem,
                    "visible_header": visible_header,
                    "baseline": baseline,
                    "intervention": intervention,
                    "baseline_red_or_blocked_drawn": False,
                    "source_files": {
                        "wild_tree": str(pair_dir / "wild_type_mcts_tree.json"),
                        "wild_trace": str(pair_dir / "wild_type_mcts_trace.jsonl"),
                        "intervention_tree": str(pair_dir / f"{args.intervention}_mcts_tree.json"),
                        "intervention_trace": str(pair_dir / f"{args.intervention}_mcts_trace.jsonl"),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
