"""Render the addenda index specimens from public source, examples, and fixtures.

Run in the repository's development shell: python3 ops/render_addenda_specimens.py.
Requires Python 3.12+, Graphviz, and Typst. No research sweeps are run.
"""

import ast
import base64
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/assets/addenda-specimens"
PAPER, INK, TEAL, RUST = "#f1eee5", "#263d3b", "#247e76", "#b75943"
CATALOG = {}
MONO_FONT = base64.b64encode(
    (ROOT / "site/fonts/BerkeleyMono-Regular.woff2").read_bytes()
).decode()
SERIF_FONT = base64.b64encode(
    (ROOT / "site/fonts/IBMPlexSerif-Regular.woff2").read_bytes()
).decode()


def text(x, y, value, size=22, color=INK, family="mono", **attrs):
    size = max(size, 28)
    attributes = " ".join(
        f'{key.replace("_", "-")}="{value}"' for key, value in attrs.items()
    )
    return f'<text x="{x}" y="{y}" class="{family}" font-size="{size}" fill="{color}" {attributes}>{html.escape(str(value))}</text>'


def line(x1, y1, x2, y2, color="#d0cabc", width=1):
    return f'<path d="M{x1},{y1}L{x2},{y2}" fill="none" stroke="{color}" stroke-width="{width}"/>'


def rect(x, y, w, h, color, **attrs):
    attributes = " ".join(
        f'{key.replace("_", "-")}="{value}"' for key, value in attrs.items()
    )
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}" {attributes}/>'
    )


def source(path):
    return (ROOT / path).read_text()


def python(project, code):
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT / project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def save(slug, elements, *, alt, caption, sources, kind, recipe):
    artifact = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600" '
        'role="img" aria-labelledby="title desc">'
        f'<title id="title">{html.escape(alt)}</title><desc id="desc">{html.escape(caption)}</desc>'
        f"<style>@font-face{{font-family:Berkeley;src:url(data:font/woff2;base64,{MONO_FONT})}}"
        + (
            f"@font-face{{font-family:Plex;src:url(data:font/woff2;base64,{SERIF_FONT})}}"
            if any('class="serif"' in item for item in elements)
            else ""
        )
        + ".mono{font-family:Berkeley,monospace}.serif{font-family:Plex,Georgia,serif}</style>"
        + rect(0, 0, 1000, 600, PAPER)
        + "".join(elements)
        + "</svg>\n"
    )
    ET.fromstring(artifact)
    pending = OUT / f"{slug}.svg.tmp"
    pending.write_text(artifact)
    pending.replace(OUT / f"{slug}.svg")
    CATALOG[slug] = {
        "src": f"/assets/addenda-specimens/{slug}.svg?v=20261017",
        "alt": alt,
        "caption": caption,
        "kind": kind,
        "recipe": recipe,
        "sources": [
            {
                "path": path,
                "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
            }
            for path in sources
        ],
        "sourceHref": "https://github.com/Specter-Research-Labs/research-registry/blob/main/"
        + sources[0],
    }


def code_lines(lines, *, x=55, y=115, size=25, step=43, color=INK):
    return [
        text(x, y + index * step, row, size, color) for index, row in enumerate(lines)
    ]


def poly():
    path = "addenda/poly-morphogenesis/docs/diagrams/rd_styled.dot"
    dot = source(path).replace('bgcolor="white"', f'bgcolor="{PAPER}"')
    dot = (
        dot.replace("#4a90d9", TEAL)
        .replace("#e8f4fd", "#e0e8de")
        .replace("#2c5f8a", TEAL)
    )
    raw = subprocess.run(
        ["dot", "-Tsvg"], input=dot, text=True, capture_output=True, check=True
    ).stdout
    graph = raw[raw.index("<svg") :]
    graph = re.sub(
        r'<svg width="[^"]+" height="[^"]+"',
        '<svg x="25" y="75" width="950" height="445"',
        graph,
        count=1,
    )
    save(
        "poly-morphogenesis",
        [
            graph,
        ],
        alt="The actual Catlab wiring diagram for the ten-cell reaction–diffusion phase",
        caption="Catlab’s ten-cell RD wiring export, restyled for this page. This is the implemented composition, not a result from the unreproduced numerical sweep.",
        sources=[path, "addenda/poly-morphogenesis/src/diagrams.jl"],
        kind="Wiring export",
        recipe="Graphviz renders the committed rd_styled.dot; only colors and framing change.",
    )


def k_grid():
    payload = json.loads(
        python(
            "addenda/k-semantics-reference",
            """
import json,random
import demos.grid as demo
original = demo.compare_policies_in_problem_space
routes = {}
def capture(space, agent, blind, **kwargs):
    for name,policy in [('agent',agent),('blind',blind)]:
        rng=random.Random(7)
        state=space.executor.initial_state_sampler(rng)
        points=[state]
        for _ in range(int(space.H)):
            if space.executor.is_goal(state): break
            operator=policy.choose_operator(space,state,rng)
            state=space.executor.apply_operator(state,operator,rng)
            points.append(state)
        routes[name]=points
    return original(space,agent,blind,**kwargs)
demo.compare_policies_in_problem_space=capture
result=demo.run_grid_demo(size=7,trials=32,H=500,seed=7)
print(json.dumps({'routes':routes,'exact':result['exact'],'sample':{'K':result['K'],'counts':result['counts'],'tau':result['tau']},'parameters':{'size':7,'trials':32,'H':500,'seed':7}}))
""",
        )
    )
    (OUT / "k-grid.json").write_text(json.dumps(payload, indent=2) + "\n")
    elements = []
    for name, left, color, label in [
        ("blind", 80, RUST, "BLIND RANDOM WALK"),
        ("agent", 590, TEAL, "SHORTEST-PATH POLICY"),
    ]:
        points = payload["routes"][name]
        assert points[0] == [0, 0] and points[-1] == [6, 6]
        elements.append(text(left - 20, 94, label, 18, color))
        for x in range(7):
            for y in range(7):
                elements.append(
                    f'<circle cx="{left + x * 53}" cy="{140 + y * 53}" r="3.5" fill="#bdb8ab"/>'
                )
        path = " ".join(
            f"{'M' if index == 0 else 'L'}{left + x * 53},{140 + y * 53}"
            for index, (x, y) in enumerate(points)
        )
        elements.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="round" stroke-linecap="round" opacity=".8"/>'
        )
        elements.append(rect(left - 8, 132, 16, 16, INK))
        elements.append(
            f'<circle cx="{left + 318}" cy="458" r="10" fill="{PAPER}" stroke="{color}" stroke-width="4"/>'
        )
        elements.append(
            text(left - 20, 510, f"{len(points) - 1} moves in this replay", 18, color)
        )
    exact = payload["exact"]
    k = exact["K"]["restricted_mean_at_H_exact"]
    elements += [
        line(48, 537, 952, 537),
        text(48, 575, f"K = {k:.2f} · ≈{10**k:.1f}×", 30),
        text(952, 574, "EXPECTED COSTS · H = 500", 28, text_anchor="end"),
    ]
    save(
        "k-semantics-reference",
        elements,
        alt="Two source-generated paths on a seven-by-seven grid: random walk and shortest-path policy",
        caption=f"Two seed-7 replays. K = log₁₀(τ_blind/τ_agent) = {k:.2f}, about {10**k:.1f}× expected-cost savings. The exact calculation caps costs at 500 steps, giving a lower bound for this grid; it is not the ratio of the pictured paths.",
        sources=[
            "addenda/k-semantics-reference/demos/grid.py",
            "addenda/k-semantics-reference/core.py",
        ],
        kind="Executable demo",
        recipe="run_grid_demo(size=7, trials=32, H=500, seed=7); paths instrument the same policy closures with Random(7).",
    )


def equational():
    results = json.loads(
        python(
            "addenda/equational-theories-distillation",
            """
import json
from small_models import all_two_element_operations,equation_holds_universally
from syntax import parse_equation
op=next(op for op in all_two_element_operations() if op.name=='xor')
print(json.dumps({'table':op.table,'commutative':equation_holds_universally(parse_equation('x * y = y * x'),op),'idempotent':equation_holds_universally(parse_equation('x = x * x'),op)}))
""",
        )
    )
    assert results["commutative"] and not results["idempotent"]
    elements = [
        text(85, 139, "◇", 35),
        text(230, 139, "0", 30),
        text(345, 139, "1", 30),
    ]
    for row in range(2):
        elements.append(text(90, 262 + row * 115, str(row), 30))
        for col in range(2):
            value = results["table"][row * 2 + col]
            elements += [
                rect(
                    185 + col * 115,
                    195 + row * 115,
                    100,
                    100,
                    "#e0e8de" if value else "#ded9ce",
                ),
                text(
                    235 + col * 115,
                    260 + row * 115,
                    str(value),
                    38,
                    text_anchor="middle",
                ),
            ]
    elements += [
        text(545, 170, "x ◇ y = y ◇ x", 35, family="serif"),
        text(545, 215, "holds for every x, y", 19, TEAL),
        text(545, 307, "x ◇ x = x", 35, family="serif"),
        text(545, 352, "fails at x = 1", 19, RUST),
        text(545, 408, "1 ◇ 1 = 0 ≠ 1", 32, RUST, family="serif"),
        line(48, 500, 952, 500),
        text(48, 552, "0110 / XOR", 19),
        text(952, 552, "CARRIER {0, 1}", 19, text_anchor="end"),
    ]
    save(
        "equational-theories-distillation",
        elements,
        alt="XOR’s two-element Cayley table: commutativity holds, while idempotence fails at one",
        caption="An exact finite countermodel checked by the project’s evaluator. XOR is commutative, but 1 ◇ 1 = 0 refutes idempotence.",
        sources=[
            "addenda/equational-theories-distillation/small_models.py",
            "addenda/equational-theories-distillation/tests/test_small_models.py",
        ],
        kind="Checked countermodel",
        recipe="Enumerate all assignments with equation_holds_universally for the shipped xor operation.",
    )
    sheet = source(
        "addenda/equational-theories-distillation/docs/cheatsheet-v0.txt"
    ).splitlines()
    excerpt = [row[2:] for row in sheet if row.startswith("- if E1 is `x = y ◇")][0]
    parts = re.findall(r"`([^`]+)`", excerpt)
    save(
        "equational-sheet",
        [
            *code_lines(parts[:2], x=48, y=210, size=22, step=90),
            text(48, 255, "or", 18, TEAL),
            text(48, 430, "derive", 18, TEAL),
            text(48, 490, parts[-1], 30, family="serif"),
        ],
        alt="An exact kernel rule excerpted from the shipped equational decision sheet",
        caption="Source excerpt from cheatsheet-v0.txt; not a new theorem or a hidden-benchmark score.",
        sources=["addenda/equational-theories-distillation/docs/cheatsheet-v0.txt"],
        kind="Source excerpt",
        recipe="Typeset the first source-triggered kernel rule verbatim.",
    )


def tokens():
    spec = tomllib.loads(source("addenda/design-tokens/web.toml"))
    elements = [
        text(48, 200, "Aa", 130, family="serif"),
        text(300, 164, "IBM Plex Serif", 34, family="serif"),
        text(300, 210, "Berkeley Mono 012345", 25),
    ]
    for index, name in enumerate(["ink", "paper", "accent", "accent-2", "surface"]):
        color = spec["colors"][name]
        x = 48 + index * 184
        elements += [
            rect(x, 285, 168, 146, color, stroke="#d0cabc"),
            text(x, 475, name, 18),
            text(x, 515, color, 18),
        ]
    save(
        "design-tokens",
        elements,
        alt="The real web color palette with IBM Plex Serif and Berkeley Mono type specimens",
        caption="The site’s actual web palette, typefaces, and token names.",
        sources=["addenda/design-tokens/web.toml", "addenda/design-tokens/base.toml"],
        kind="Token specimen",
        recipe="Read web.toml colors and use the site’s bundled fonts.",
    )


def typst():
    raw = OUT / "typst-render.svg"
    subprocess.run(
        [
            "typst",
            "compile",
            "--pages",
            "1",
            "--font-path",
            str(ROOT / "addenda/typst-field-manual/assets/fonts"),
            str(ROOT / "addenda/typst-field-manual/paper-example.typ"),
            str(raw),
        ],
        check=True,
    )
    content = raw.read_text()
    tree = ET.fromstring(content)
    width = float(tree.attrib["width"].removesuffix("pt"))
    nested = content[content.index("<svg") :]
    nested = re.sub(
        r"<svg[^>]+>",
        f'<svg x="45" y="65" width="910" height="500" viewBox="25 15 {width - 50} 310" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">',
        nested,
        count=1,
    )
    save(
        "typst-field-manual",
        [nested],
        alt="The title and abstract of the actual Typst paper example, rendered by Typst",
        caption="A crop of paper-example.typ rendered with the bundled publication fonts. Template content, not a research report.",
        sources=[
            "addenda/typst-field-manual/paper-example.typ",
            "addenda/typst-field-manual/specter-paper.typ",
        ],
        kind="Typeset output",
        recipe="typst compile --pages 1 --font-path addenda/typst-field-manual/assets/fonts; crop the title and abstract.",
    )
    raw.unlink()


def lean():
    readme = source("addenda/lean-corpus-extractor/README.md")
    record = json.loads(
        next(row for row in readme.splitlines() if row.startswith('{"item_id"'))
    )
    elements = [
        *code_lines(
            [
                "theorem {name} :",
                "  forall (a b : Nat),",
                "  a + b = b + a := by",
                "  sorry",
            ],
            y=135,
            size=30,
            step=48,
        ),
        line(48, 355, 952, 355),
        *code_lines(
            [
                record["item_id"],
                record["display_name"],
                record["payload"]["source"]["module"],
            ],
            y=411,
            size=24,
            step=49,
        ),
    ]
    save(
        "lean-corpus-extractor",
        elements,
        alt="Nat.add_comm and the extractor’s documented corpus record",
        caption="The declaration template from the extractor’s README example, reflowed for display, with its unchanged record identifiers.",
        sources=["addenda/lean-corpus-extractor/README.md"],
        kind="Documented output",
        recipe="Read the documented JSON example; reflow its declaration template and typeset its identifiers.",
    )
    fixture = json.loads(
        source(
            "addenda/lean-sorry-dataset/tests/fixtures/index.min.jsonl"
        ).splitlines()[0]
    )
    save(
        "lean-sorry-dataset",
        [
            *code_lines(fixture["goal_text"].splitlines(), y=160, size=47, step=70),
            line(48, 290, 952, 290),
            *code_lines(
                [
                    f'item_id     "{fixture["item_id"]}"',
                    f'path        "{fixture["location_path"]}"',
                    f'Lean        "{fixture["repo_lean_version"]}"',
                    f'license     "{fixture["repo_license_spdx"]}"',
                ],
                y=352,
                size=27,
                step=51,
            ),
        ],
        alt="A real dataset test fixture: x : Nat, goal x = x, and its index metadata",
        caption="The committed index.min.jsonl test fixture. This is a format specimen, not a sampled production record.",
        sources=["addenda/lean-sorry-dataset/tests/fixtures/index.min.jsonl"],
        kind="Index fixture",
        recipe="Read the first committed fixture record without changing its values.",
    )
    output = json.loads(
        python(
            "addenda/lean-tactic-representation",
            """from cli import main
main(['show','nested_constructor_apply','--format','json'])""",
        )
    )
    (OUT / "tactic-example.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    )
    program = python(
        "addenda/lean-tactic-representation",
        """import json
from examples.catalog import get_example
from render import render_program
print(json.dumps(render_program(get_example('nested_constructor_apply').program)))""",
    )
    rows = json.loads(program)
    elements = [
        text(48, 145, "⊢ P ∧ Q", 47, family="serif"),
        *code_lines(rows, y=240, size=32, step=53, color=TEAL),
    ]
    save(
        "lean-tactic-representation",
        elements,
        alt="The toy interpreter’s actual nested constructor/apply program",
        caption="An executed toy-interpreter example: constructor, apply proveP, exact ha, and exact hq.",
        sources=[
            "addenda/lean-tactic-representation/examples/catalog.py",
            "addenda/lean-tactic-representation/render.py",
        ],
        kind="Toy interpreter output",
        recipe="show nested_constructor_apply --format json; render_program on that same example.",
    )
    tree = json.loads(
        source(
            "dossiers/wonton-soup/docs/figures/poster/data/hf00795-block-exact/wild_type_mcts_tree.json"
        )
    )
    goal = tree["nodes"][tree["root_mvar_id"]]["goal_type"]
    tactic = next(iter(tree["nodes"][tree["root_mvar_id"]]["children"]))
    elements = [
        text(48, 115, "[STATE]", 23, TEAL),
        *code_lines(goal.splitlines(), y=169, size=23, step=43),
        text(48, 417, "[/STATE]", 23, TEAL),
        text(48, 475, "[TAC]", 23, RUST),
        text(260, 475, tactic, 32),
        text(48, 535, "[/TAC]", 23, RUST),
    ]
    save(
        "lean-mcts-learning",
        elements,
        alt="A recorded Wonton goal and its next tactic in the training-pair format",
        caption="The training-pair format applied to the first committed step of the public hf00795 trace. No training or evaluation score is implied.",
        sources=[
            "addenda/lean-mcts-learning/data/tactic_sft.py",
            "dossiers/wonton-soup/docs/figures/poster/data/hf00795-block-exact/wild_type_mcts_tree.json",
        ],
        kind="Recorded step / data format",
        recipe="Use the recorded root goal and its first committed tactic; typeset the builder’s STATE/TAC fields.",
    )


def tools():
    scoring = ast.parse(
        source("addenda/lean-sorry-repos-benchmark/tests/test_scoring.py")
    )
    test = next(
        node
        for node in scoring.body
        if isinstance(node, ast.FunctionDef)
        and node.name.endswith("uses_item_level_any_success")
    )
    call = next(
        node
        for node in ast.walk(test)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "aggregate_verification_pass_at_k"
    )
    matrix = ast.literal_eval(
        next(
            kw.value for kw in call.keywords if kw.arg == "verification_success_by_item"
        )
    )
    elements = []
    for col in range(3):
        elements.append(
            text(370 + col * 200, 125, f"try {col + 1}", 24, text_anchor="middle")
        )
    for row, outcomes in enumerate(matrix):
        elements.append(text(48, 240 + row * 115, f"item {row + 1}", 24))
        for col, ok in enumerate(outcomes):
            x, y = 290 + col * 200, 175 + row * 115
            elements += [
                rect(x, y, 160, 90, "#e0e8de" if ok else "#e4ded3"),
                text(
                    x + 80,
                    y + 58,
                    "PASS" if ok else "FAIL",
                    25,
                    TEAL if ok else RUST,
                    text_anchor="middle",
                ),
            ]
    save(
        "lean-sorry-repos-benchmark",
        elements,
        alt="The scoring unit test’s three-by-three verification outcome matrix",
        caption="The actual pass-at-k scoring test fixture. These are test inputs, not benchmark performance.",
        sources=["addenda/lean-sorry-repos-benchmark/tests/test_scoring.py"],
        kind="Scoring fixture",
        recipe="Read verification_success_by_item from the named scoring test via Python’s AST.",
    )
    test = source("addenda/tinygrad-benchmarks/tests/test_compare.py")
    assert "-VALUE = 'old'" in test and "+VALUE = 'new'" in test
    save(
        "tinygrad-benchmarks",
        [
            text(48, 133, "tinygrad/demo.py", 27),
            rect(40, 192, 920, 85, "#ecd9cf"),
            text(65, 247, "-VALUE = 'old'", 37, RUST),
            rect(40, 288, 920, 85, "#dfe7da"),
            text(65, 343, "+VALUE = 'new'", 37, TEAL),
        ],
        alt="The exact old/new diff from the tinygrad patch-comparison test fixture",
        caption="The patch-comparison test’s diff fixture. It demonstrates matching machinery, not a real tinygrad task or a speed result.",
        sources=["addenda/tinygrad-benchmarks/tests/test_compare.py"],
        kind="Patch fixture",
        recipe="Typeset the unchanged old/new lines used by test_compare_attempts_to_gold_detects_close_match.",
    )
    readme = source("addenda/specter-viz/README.md")
    assert "vec![1.0, 0.82, 0.71, 0.64]" in readme
    values = [1.0, 0.82, 0.71, 0.64]
    low = [0.92, 0.75, 0.66, 0.60]
    high = [1.08, 0.89, 0.76, 0.68]
    assert "vec![0.92, 0.75, 0.66, 0.60]" in readme
    assert "vec![1.08, 0.89, 0.76, 0.68]" in readme
    elements = [
        *code_lines(
            [
                'Panel::new("Overview")',
                "LineChart::new()",
                "  .interval(&loss_band)",
                "  .series(&loss)",
                "  .try_show(ui)",
            ],
            y=155,
            size=25,
            step=52,
        ),
    ]

    def point(index, value):
        return f"{590 + index * 110:.1f},{405 - (value - 0.5) * 400:.1f}"

    band = [point(i, v) for i, v in enumerate(high)] + [
        point(i, low[i]) for i in reversed(range(4))
    ]
    elements += [
        f'<polygon points="{" ".join(band)}" fill="#344aa0" opacity=".12"/>',
        line(570, 430, 950, 430),
        line(570, 430, 570, 135),
        f'<polyline points="{" ".join(point(i, v) for i, v in enumerate(values))}" fill="none" stroke="#344aa0" stroke-width="4"/>',
    ]
    for i, value in enumerate(values):
        x, y = point(i, value).split(",")
        elements += [
            f'<circle cx="{x}" cy="{y}" r="6" fill="#344aa0"/>',
            text(float(x), float(y) - 17, str(value), 18, text_anchor="middle"),
        ]
    elements += [
        text(48, 515, "loss = [1.0, 0.82, 0.71, 0.64]", 26),
    ]
    save(
        "specter-viz",
        elements,
        alt="The actual Panel and LineChart API alongside the four-point example series and interval from its README",
        caption="The native component API and a plot of its documented sample values. Example data, not measured training loss or a screenshot of the egui widget.",
        sources=[
            "addenda/specter-viz/README.md",
            "addenda/specter-viz/src/charts/line.rs",
        ],
        kind="Component API / example data",
        recipe="Typeset the Panel/LineChart calls and plot exactly the series and interval values in the README.",
    )


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    poly()
    k_grid()
    equational()
    tokens()
    typst()
    lean()
    tools()
    CATALOG["lean-tactic-representation"]["dataHref"] = (
        "/assets/addenda-specimens/tactic-example.json"
    )
    (OUT / "manifest.json").write_text(
        json.dumps(CATALOG, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"Rendered {len(CATALOG)} source-backed specimens.")
