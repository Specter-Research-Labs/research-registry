"""Rebuild dossier index artwork from the public dossier model and proof logs.

Run with python3 ops/render_dossier_previews.py; requires node.
"""

import colorsys
import html
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/assets"
PAPER = "#f1eee5"
INK = "#263d3b"
TEAL = "#247e76"
RUST = "#b75943"


def text(x, y, value, size=18, fill=INK, **attrs):
    extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" {extra}>{html.escape(value)}</text>'


def svg(name, title, description, elements):
    content = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600" '
        'role="img" aria-labelledby="title description">'
        f'<title id="title">{title}</title><desc id="description">{description}</desc>'
        '<style>text{font-family:monospace}path,circle{vector-effect:non-scaling-stroke}</style>'
        f'<rect width="1000" height="600" fill="{PAPER}"/>'
        + "".join(elements) + "</svg>\n"
    )
    (OUT / name).write_text(content)


def sorting():
    # Execute the page's own model, keeping the artwork and replay on the same rules.
    source = (ROOT / "site/templates/dossiers/zhang-levin-playground/index.html").read_text()
    model = source[source.index("function mulberry32"):source.index("// Rendering helpers")]
    result = subprocess.run(
        ["node", "-e", model + "\nconsole.log(JSON.stringify(runClusteringPair(1038, 50).ins));"],
        check=True, text=True, capture_output=True,
    )
    states = json.loads(result.stdout)["states"]
    assert [v for v, _ in states[-1]["order"]] == list(range(50))
    elements = []
    samples = [states[round(k / 99 * (len(states) - 1))] for k in range(100)]
    for value in range(50):
        rgb = colorsys.hls_to_rgb(0.015 + value / 49 * 0.49, 0.40, 0.48)
        color = "#" + "".join(f"{round(c * 255):02x}" for c in rgb)
        points = []
        for k, state in enumerate(samples):
            position = next(i for i, cell in enumerate(state["order"]) if cell[0] == value)
            x = 48 + k / 99 * 904
            y = 50 + position / 49 * 470
            if k == 0:
                points.append(f"M{x:.2f},{y:.2f}")
            else:
                midpoint = (x + previous_x) / 2
                points.append(f"C{midpoint:.2f},{previous_y:.2f} {midpoint:.2f},{y:.2f} {x:.2f},{y:.2f}")
            previous_x, previous_y = x, y
        elements.append(f'<path d="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2.4" opacity=".85"/>')
        elements.append(f'<circle cx="952" cy="{50 + value / 49 * 470:.2f}" r="3.5" fill="{color}"/>')
    elements += [text(46, 568, "BUBBLE × INSERTION", 20), text(954, 568, "50 CELL PATHS →", 18, text_anchor="end")]
    svg("research-sorting.svg", "Fifty sorting cells braid into order",
        "Each colored path follows one cell through the dossier’s seeded Bubble–Insertion replay (seed 1038). One hundred evenly spaced swap samples are connected by interpolated curves. Time runs left to right; cell position runs top to bottom.", elements)


def proof():
    directory = ROOT / "dossiers/wonton-soup/docs/figures/poster"
    data = json.loads((directory / "out/wonton-real-log-block-exact-take-03-coral-reroute.manifest.json").read_text())
    elements = [text(45, 43, "LEAN / RECORDED SEARCH", 19), text(955, 43, "hf00795", 17, text_anchor="end")]
    elements.append('<path d="M310 84V532" stroke="#d1cabe" stroke-width="1"/>')
    for name, filename, left, width in [
        ("baseline", "wild_type_mcts_tree.json", 45, 215),
        ("intervention", "block_exact_mcts_tree.json", 355, 600),
    ]:
        tree = json.loads((directory / "data/hf00795-block-exact" / filename).read_text())
        nodes = tree["nodes"]
        selected = set(data[name]["winner"]["selected_path"])
        positions = {}
        layers = {}
        for key, node in nodes.items():
            layers.setdefault(node["depth"], []).append(key)
        for depth, keys in sorted(layers.items()):
            for index, key in enumerate(keys):
                x = left + (index + 0.5) / len(keys) * width
                positions[key] = (x, 145 + depth * 62)
        for key, node in nodes.items():
            x, y = positions[key]
            for tactic, children in node["children"].items():
                for child in children:
                    cx, cy = positions[child]
                    winner = key in selected and child in selected
                    color = TEAL if winner else "#b8b4a8"
                    elements.append(f'<path d="M{x},{y}C{x},{y+32} {cx},{cy-32} {cx},{cy}" fill="none" stroke="{color}" stroke-width="{2.8 if winner else 1.1}"/>')
                    if winner:
                        elements.append(text((x + cx) / 2 + 10, (y + cy) / 2, tactic, 16, TEAL))
        for key, (x, y) in positions.items():
            winner = key in selected
            terminal = nodes[key]["is_terminal"]
            elements.append(f'<circle cx="{x}" cy="{y}" r="{7 if winner else 4}" fill="{TEAL if winner else PAPER}" stroke="{TEAL if winner else "#a7a598"}" stroke-width="1.2"/>')
            if terminal:
                elements.append(f'<circle cx="{x}" cy="{y}" r="12" fill="none" stroke="{TEAL}" stroke-width="1"/>')
            if key in data[name]["blocked_exact_attempts"]:
                elements.append(f'<path d="M{x+12},{y}l20,0m-5,-5 10,10m0,-10 -10,10" fill="none" stroke="{RUST}" stroke-width="1.6"/>')
        label = "ALL TACTICS" if name == "baseline" else "EXACT REMOVED"
        elements.append(text(left, 90, label, 17, TEAL if name == "baseline" else RUST))
        wx, wy = positions[data[name]["winner"]["terminal_node"]]
        if name == "baseline":
            elements.append(text(wx + 15, wy + 6, data[name]["winner"]["terminal_tactic"], 17, TEAL))
    elements += [text(45, 565, "PROOF ROUTES FROM THE SAME THEOREM", 16), text(955, 565, "○ GOAL   × BLOCKED", 15, text_anchor="end")]
    svg("research-proof.svg", "Two recorded Lean proof searches",
        "Actual goal trees for theorem hf00795, before and after removing exact. Teal follows the recorded winning paths; rust marks blocked exact attempts. Node positions are laid out for this illustration.", elements)


if __name__ == "__main__":
    sorting()
    proof()
