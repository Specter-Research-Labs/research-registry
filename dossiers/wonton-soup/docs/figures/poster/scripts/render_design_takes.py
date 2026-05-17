#!/usr/bin/env python3
"""Render substantially different publication-poster design takes.

These variants deliberately share the same real proof data as
render_publication_poster.py while changing composition and palette.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import render_pair as rp
import render_publication_poster as pub


THEOREM_ID = "hf_deepseek_prover_v1_train_00795"
FONT = pub.FONT


@dataclass(frozen=True)
class Palette:
    bg: str
    ink: str
    muted: str
    path: str
    path_dark: str
    block: str
    solved: str
    ghost: str
    ghost_text: str
    grey: str
    muted_green: str
    goal_text: str
    goal_rule: str
    accent: str
    chip: str
    grid: str


PALE_NOIR = Palette(
    bg="#11100e",
    ink="#f3ecdc",
    muted="#b7aa94",
    path="#23d7c5",
    path_dark="#8ff3e4",
    block="#ff6a44",
    solved="#7ad67b",
    ghost="#6b6f72",
    ghost_text="#8db0be",
    grey="#5e5a52",
    muted_green="#59765b",
    goal_text="#d9d1bf",
    goal_rule="#f0b64a",
    accent="#f0b64a",
    chip="#1d1a16",
    grid="#2c2923",
)

BLUEPRINT = Palette(
    bg="#f5fbff",
    ink="#10263a",
    muted="#5c7488",
    path="#007d95",
    path_dark="#005c72",
    block="#d74336",
    solved="#24784d",
    ghost="#b1c8d8",
    ghost_text="#6d9ab5",
    grey="#9eb0bd",
    muted_green="#9db9a8",
    goal_text="#3e5968",
    goal_rule="#87bdd8",
    accent="#277ca3",
    chip="#e4f3fb",
    grid="#d8ecf7",
)

CORAL = Palette(
    bg="#fff3ea",
    ink="#321f1b",
    muted="#7f6256",
    path="#047f6f",
    path_dark="#07584f",
    block="#df4f68",
    solved="#28714b",
    ghost="#d5b9aa",
    ghost_text="#a67c6e",
    grey="#c5aa9d",
    muted_green="#9fbc94",
    goal_text="#5b5e4f",
    goal_rule="#e5a650",
    accent="#f29f4b",
    chip="#ffe1d2",
    grid="#f4d5c5",
)

LEDGER = Palette(
    bg="#f8f5ee",
    ink="#24211d",
    muted="#736d63",
    path="#111111",
    path_dark="#111111",
    block="#cb3e32",
    solved="#2f7f53",
    ghost="#c9c2b7",
    ghost_text="#7a8c98",
    grey="#aba397",
    muted_green="#9faf94",
    goal_text="#4b5c52",
    goal_rule="#d7a64b",
    accent="#b9852d",
    chip="#ebe3d5",
    grid="#e4dbcd",
)

BLUEPRINT_LEDGER = Palette(
    bg=LEDGER.bg,
    ink=LEDGER.ink,
    muted=LEDGER.muted,
    path=LEDGER.path,
    path_dark=LEDGER.solved,
    block=LEDGER.block,
    solved=LEDGER.solved,
    ghost=LEDGER.ghost,
    ghost_text=LEDGER.ghost_text,
    grey=LEDGER.grey,
    muted_green=LEDGER.muted_green,
    goal_text=LEDGER.goal_text,
    goal_rule=LEDGER.goal_rule,
    accent=LEDGER.accent,
    chip=LEDGER.chip,
    grid=LEDGER.grid,
)


TAKES = {
    "noir": PALE_NOIR,
    "blueprint": BLUEPRINT,
    "coral": CORAL,
    "ledger": LEDGER,
}


def configure_palette(p: Palette) -> None:
    pub.BG = p.bg
    pub.INK = p.ink
    pub.MUTED = p.muted
    pub.TEAL = p.path
    pub.TEAL_DARK = p.path_dark
    pub.AMBER = p.accent
    pub.PALE = p.ghost
    pub.PALE_TEXT = p.ghost_text
    pub.BLOCK = p.block
    pub.GREEN = p.solved
    pub.GREY = p.grey
    pub.MUTED_GREEN = p.muted_green
    pub.GOAL_TEXT = p.goal_text
    pub.GOAL_RULE = p.goal_rule


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
        rp.svg_text(
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


def start_svg(width: int, height: int, p: Palette, *, grid: bool, grain: bool = False) -> list[str]:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
    ]
    if grid:
        parts.append(
            f'<pattern id="grid" width="42" height="42" patternUnits="userSpaceOnUse">'
            f'<path d="M42 0H0V42" fill="none" stroke="{p.grid}" stroke-width="0.9" opacity="0.72"/>'
            "</pattern>"
        )
    if grain:
        parts.append(
            '<pattern id="grain" width="90" height="90" patternUnits="userSpaceOnUse">'
            '<circle cx="16" cy="21" r="0.8" fill="#eadfcd"/>'
            '<circle cx="70" cy="52" r="0.65" fill="#efe4d2"/></pattern>'
        )
    parts.append("</defs>")
    parts.append(f'<rect width="100%" height="100%" fill="{p.bg}"/>')
    if grid:
        parts.append('<rect width="100%" height="100%" fill="url(#grid)" opacity="0.64"/>')
    if grain:
        parts.append('<rect width="100%" height="100%" fill="url(#grain)" opacity="0.25"/>')
    return parts


def theorem_lines(theorem: str, width: int) -> list[str]:
    return rp.wrap_lines(theorem, width)


def winner_tactics(tree: dict[str, Any], trace_path: Path) -> list[str]:
    winner = pub.trace_winner(trace_path)
    incoming = pub.incoming_tactics(tree)
    tactics = [incoming[node_id] for node_id in winner["selected_path"][1:] if node_id in incoming]
    if winner["terminal_tactic"]:
        tactics.append(winner["terminal_tactic"])
    return tactics


def blocked_count(trace_path: Path) -> int:
    return sum(len(v) for v in pub.trace_blocked_exact(trace_path).values())


def draw_path_strip(
    parts: list[str],
    *,
    x: float,
    y: float,
    w: float,
    label: str,
    tactics: list[str],
    p: Palette,
    blocked: int = 0,
    dark: bool = False,
) -> None:
    text(parts, [label], x, y - 18, 11, p.muted, weight="700")
    if len(tactics) <= 1:
        return
    left, right = x + 26, x + w - 26
    step = (right - left) / (len(tactics) - 1)
    parts.append(
        f'<path d="M{left:.1f},{y:.1f} L{right:.1f},{y:.1f}" fill="none" '
        f'stroke="{p.path}" stroke-width="2.2" stroke-linecap="round" opacity="0.82"/>'
    )
    for idx, tactic in enumerate(tactics):
        sx = left + idx * step
        parts.append(f'<circle cx="{sx:.1f}" cy="{y:.1f}" r="5.4" fill="{p.bg}" stroke="{p.path}" stroke-width="2"/>')
        label_y = y + 21 if idx % 2 == 0 else y - 26
        fill = p.path_dark if not dark else p.path
        text(parts, [rp.truncate(tactic, 16)], sx, label_y, 8.5, fill, anchor="middle")
    if blocked:
        bx = left + step * 0.72
        parts.append(
            f'<path d="M{bx:.1f},{y-34:.1f} L{bx:.1f},{y+34:.1f}" stroke="{p.block}" '
            f'stroke-width="1.4" stroke-dasharray="4 4" opacity="0.82"/>'
        )
        parts.append(f'<circle cx="{bx:.1f}" cy="{y-40:.1f}" r="7" fill="{p.bg}" stroke="{p.block}" stroke-width="2"/>')
        parts.append(
            f'<path d="M{bx-3.5:.1f},{y-43.5:.1f} L{bx+3.5:.1f},{y-36.5:.1f} '
            f'M{bx+3.5:.1f},{y-43.5:.1f} L{bx-3.5:.1f},{y-36.5:.1f}" '
            f'stroke="{p.block}" stroke-width="1.7" stroke-linecap="round"/>'
        )
        text(parts, [f"{blocked} exact blocks"], bx + 13, y - 36, 8.5, p.block)


def draw_chip(parts: list[str], x: float, y: float, label: str, value: str, p: Palette) -> None:
    parts.append(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="178" height="46" rx="7" '
        f'fill="{p.chip}" stroke="{p.grid}" stroke-width="0.8" opacity="0.92"/>'
    )
    text(parts, [label], x + 14, y + 17, 8.5, p.muted, weight="700")
    text(parts, [value], x + 14, y + 35, 12, p.ink, weight="700")


def draw_ledger_rows(
    parts: list[str],
    *,
    x: float,
    y: float,
    w: float,
    title: str,
    rows: list[str],
    p: Palette,
    accent: str,
) -> None:
    text(parts, [title], x, y, 16, p.ink, weight="700")
    row_y = y + 32
    for idx, row in enumerate(rows):
        fill = p.chip if idx % 2 == 0 else p.bg
        parts.append(
            f'<rect x="{x:.1f}" y="{row_y-17:.1f}" width="{w:.1f}" height="28" rx="4" '
            f'fill="{fill}" stroke="{p.grid}" stroke-width="0.6" opacity="0.95"/>'
        )
        parts.append(f'<circle cx="{x+13:.1f}" cy="{row_y-3:.1f}" r="3.8" fill="{accent}" opacity="0.9"/>')
        text(parts, [rp.truncate(row, 48)], x + 27, row_y + 1, 10.5, p.ink)
        row_y += 32


def render_noir(
    *,
    theorem: str,
    wild_tree: dict[str, Any],
    int_tree: dict[str, Any],
    pair_dir: Path,
    intervention: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    p = PALE_NOIR
    configure_palette(p)
    parts = start_svg(1200, 1800, p, grid=False)
    for x in range(92, 1160, 128):
        parts.append(f'<path d="M{x} 0V1800" stroke="{p.grid}" stroke-width="0.8" opacity="0.5"/>')
    text(parts, ["Wonton Soup"], 72, 94, 58, p.ink, weight="700")
    text(parts, ["distributed proof search under tactic lesions"], 76, 136, 16, p.path)
    text(parts, theorem_lines(theorem, 52), 76, 184, 11, p.muted, line_height=1.28)
    draw_chip(parts, 788, 78, "paired theorem", "hf00795", p)
    draw_chip(parts, 984, 78, "intervention", "block exact", p)
    draw_path_strip(
        parts,
        x=75,
        y=300,
        w=488,
        label="wild type route",
        tactics=winner_tactics(wild_tree, pair_dir / "wild_type_mcts_trace.jsonl"),
        p=p,
        dark=True,
    )
    draw_path_strip(
        parts,
        x=630,
        y=300,
        w=480,
        label="lesioned reroute",
        tactics=winner_tactics(int_tree, pair_dir / f"{intervention}_mcts_trace.jsonl"),
        p=p,
        blocked=blocked_count(pair_dir / f"{intervention}_mcts_trace.jsonl"),
        dark=True,
    )
    baseline = pub.draw_tree(
        parts,
        tree=wild_tree,
        trace_path=pair_dir / "wild_type_mcts_trace.jsonl",
        title="baseline",
        subtitle="exact allowed",
        x=74,
        y=505,
        w=420,
        h=1010,
        neutral_ghosts=True,
        wiggle=True,
        snapshot_count=1,
        subtitle_color=p.muted,
    )
    intervention_data = pub.draw_tree(
        parts,
        tree=int_tree,
        trace_path=pair_dir / f"{intervention}_mcts_trace.jsonl",
        title="reroute",
        subtitle="exact blocked",
        x=558,
        y=505,
        w=565,
        h=1010,
        neutral_ghosts=False,
        snapshot_sides=(-1, -1, -1),
        snapshot_count=1,
        outcome_label=None,
        subtitle_color=p.block,
    )
    text(parts, ["winner paths are real accepted MCTS edges; red marks exact attempts blocked in the rerun"], 600, 1712, 11, p.muted, anchor="middle")
    parts.append("</svg>")
    return "\n".join(parts), baseline, intervention_data


def render_blueprint(
    *,
    theorem: str,
    wild_tree: dict[str, Any],
    int_tree: dict[str, Any],
    pair_dir: Path,
    intervention: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    p = BLUEPRINT
    configure_palette(p)
    parts = start_svg(1200, 1800, p, grid=True)
    text(parts, ["WONTON SOUP"], 80, 92, 44, p.ink, weight="700")
    text(parts, ["proof graph blueprint / matched-budget perturbation"], 84, 130, 15, p.accent)
    text(parts, theorem_lines(theorem, 74), 82, 184, 10.5, p.muted, line_height=1.22)
    draw_chip(parts, 770, 78, "wild close", "exact H''", p)
    draw_chip(parts, 968, 78, "lesion close", "rintro ⟨⟩", p)
    parts.append(f'<path d="M70 1030H1130" stroke="{p.accent}" stroke-width="1.2" stroke-dasharray="8 8" opacity="0.5"/>')
    baseline = pub.draw_tree(
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
        subtitle_color=p.muted,
    )
    intervention_data = pub.draw_tree(
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
        subtitle_color=p.block,
    )
    text(parts, ["same theorem, same budget class, different structural route"], 600, 1718, 12, p.muted, anchor="middle")
    parts.append("</svg>")
    return "\n".join(parts), baseline, intervention_data


def render_blueprint_ledger(
    *,
    theorem: str,
    wild_tree: dict[str, Any],
    int_tree: dict[str, Any],
    pair_dir: Path,
    intervention: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    p = BLUEPRINT_LEDGER
    configure_palette(p)
    parts = start_svg(1200, 1800, p, grid=True, grain=True)
    text(parts, ["Wonton Soup"], 80, 92, 44, p.ink, weight="700")
    text(parts, ["proof graph blueprint / matched-budget perturbation"], 84, 130, 15, p.accent)
    text(parts, theorem_lines(theorem, 74), 82, 184, 10.5, p.muted, line_height=1.22)
    draw_chip(parts, 770, 78, "wild close", "exact H''", p)
    draw_chip(parts, 968, 78, "lesion close", "rintro ⟨⟩", p)
    text(parts, ["red X = blocked exact"], 968, 260, 10.5, p.block)
    parts.append(f'<path d="M70 1030H1130" stroke="{p.accent}" stroke-width="1.2" stroke-dasharray="8 8" opacity="0.45"/>')
    baseline = pub.draw_tree(
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
        subtitle_color=p.muted,
    )
    intervention_data = pub.draw_tree(
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
        subtitle_color=p.block,
        blocked_label_limit=0,
    )
    text(parts, ["same theorem, same budget class, different structural route"], 600, 1718, 12, p.muted, anchor="middle")
    parts.append("</svg>")
    return "\n".join(parts), baseline, intervention_data


def render_coral(
    *,
    theorem: str,
    wild_tree: dict[str, Any],
    int_tree: dict[str, Any],
    pair_dir: Path,
    intervention: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    p = CORAL
    configure_palette(p)
    parts = start_svg(1200, 1800, p, grid=False, grain=True)
    parts.append(f'<rect x="0" y="0" width="360" height="1800" fill="{p.chip}" opacity="0.62"/>')
    text(parts, ["Wonton", "Soup"], 72, 102, 54, p.ink, weight="700", line_height=1.05)
    text(parts, ["a proof-search system reroutes when exact is lesioned"], 75, 226, 13, p.path_dark, line_height=1.25)
    text(parts, theorem_lines(theorem, 35), 75, 300, 9.5, p.muted, line_height=1.25)
    draw_path_strip(
        parts,
        x=72,
        y=500,
        w=245,
        label="baseline",
        tactics=winner_tactics(wild_tree, pair_dir / "wild_type_mcts_trace.jsonl"),
        p=p,
    )
    draw_path_strip(
        parts,
        x=72,
        y=642,
        w=245,
        label="lesion",
        tactics=winner_tactics(int_tree, pair_dir / f"{intervention}_mcts_trace.jsonl"),
        p=p,
        blocked=blocked_count(pair_dir / f"{intervention}_mcts_trace.jsonl"),
    )
    baseline = pub.draw_tree(
        parts,
        tree=wild_tree,
        trace_path=pair_dir / "wild_type_mcts_trace.jsonl",
        title="wild",
        subtitle="exact path",
        x=70,
        y=880,
        w=260,
        h=600,
        neutral_ghosts=True,
        wiggle=True,
        snapshot_count=0,
        subtitle_color=p.muted,
    )
    intervention_data = pub.draw_tree(
        parts,
        tree=int_tree,
        trace_path=pair_dir / f"{intervention}_mcts_trace.jsonl",
        title="lesioned search",
        subtitle="reroute recovered",
        x=420,
        y=420,
        w=690,
        h=1080,
        neutral_ghosts=False,
        snapshot_sides=(-1, -1, 1),
        snapshot_count=1,
        outcome_label=None,
        subtitle_color=p.block,
    )
    text(parts, ["blocked exact attempts are shown only where the intervention trace records them"], 758, 1654, 11, p.muted, anchor="middle")
    parts.append("</svg>")
    return "\n".join(parts), baseline, intervention_data


def render_ledger(
    *,
    theorem: str,
    wild_tree: dict[str, Any],
    int_tree: dict[str, Any],
    pair_dir: Path,
    intervention: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    p = LEDGER
    configure_palette(p)
    parts = start_svg(1200, 1800, p, grid=False, grain=True)
    text(parts, ["Wonton Soup"], 76, 94, 52, p.ink, weight="700")
    text(parts, ["log-anchored perturbation poster"], 80, 134, 15, p.muted)
    text(parts, theorem_lines(theorem, 82), 80, 188, 10.8, p.muted, line_height=1.22)
    baseline = pub.draw_tree(
        parts,
        tree=wild_tree,
        trace_path=pair_dir / "wild_type_mcts_trace.jsonl",
        title="wild type graph",
        subtitle="no blocked tactic semantics",
        x=80,
        y=430,
        w=460,
        h=690,
        neutral_ghosts=True,
        wiggle=True,
        snapshot_count=0,
        subtitle_color=p.muted,
    )
    intervention_data = pub.draw_tree(
        parts,
        tree=int_tree,
        trace_path=pair_dir / f"{intervention}_mcts_trace.jsonl",
        title="intervention graph",
        subtitle="exact blocked",
        x=650,
        y=430,
        w=470,
        h=690,
        neutral_ghosts=False,
        snapshot_count=0,
        outcome_label="reroute",
        subtitle_color=p.block,
    )
    parts.append(f'<path d="M72 1240H1128" stroke="{p.grid}" stroke-width="1.4"/>')
    draw_ledger_rows(
        parts,
        x=90,
        y=1304,
        w=455,
        title="baseline accepted route",
        rows=winner_tactics(wild_tree, pair_dir / "wild_type_mcts_trace.jsonl"),
        p=p,
        accent=p.path,
    )
    draw_ledger_rows(
        parts,
        x=655,
        y=1304,
        w=455,
        title="intervention accepted route",
        rows=winner_tactics(int_tree, pair_dir / f"{intervention}_mcts_trace.jsonl"),
        p=p,
        accent=p.solved,
    )
    b_count = blocked_count(pair_dir / f"{intervention}_mcts_trace.jsonl")
    parts.append(
        f'<rect x="655" y="1640" width="455" height="44" rx="6" fill="#f7ddd8" '
        f'stroke="{p.block}" stroke-width="1" opacity="0.88"/>'
    )
    text(parts, [f"lesion: exact blocked {b_count} times; winner closes with rintro ⟨⟩"], 678, 1668, 11, p.block, weight="700")
    parts.append("</svg>")
    return "\n".join(parts), baseline, intervention_data


RENDERERS = {
    "noir": render_noir,
    "blueprint": render_blueprint,
    "blueprint-ledger": render_blueprint_ledger,
    "coral": render_coral,
    "ledger": render_ledger,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair-dir", type=Path, required=True)
    parser.add_argument("--intervention", default="block_exact")
    parser.add_argument("--take", choices=tuple(RENDERERS), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    theorem = rp.clean_theorem(args.pair_dir, args.intervention, THEOREM_ID)
    wild_tree = rp.read_json(args.pair_dir / "wild_type_mcts_tree.json")
    int_tree = rp.read_json(args.pair_dir / f"{args.intervention}_mcts_tree.json")
    svg, baseline, intervention = RENDERERS[args.take](
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
                    "take": args.take,
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
