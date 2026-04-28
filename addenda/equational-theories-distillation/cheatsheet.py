from __future__ import annotations

from collections import defaultdict
from typing import cast

from analysis import build_public_analysis
from graph import ImplicationGraph
from laws import LawCatalog
from public_benchmark import PublicProblem


def _kernel_catalog_lines(kernel_bridge_analysis: dict[str, object]) -> list[str]:
    source_rules = cast(list[dict[str, object]], kernel_bridge_analysis["source_rules"])
    grouped_sources: dict[str, list[str]] = defaultdict(list)
    for rule in source_rules:
        grouped_sources[cast(str, rule["kernel_equation"])].append(
            cast(str, rule["source_equation"]),
        )

    lines = []
    for kernel_equation, source_equations in grouped_sources.items():
        rendered_sources = " or ".join(f"`{equation}`" for equation in source_equations)
        lines.append(f"- if E1 is {rendered_sources}, derive `{kernel_equation}`.")
    return lines


def _micro_rewrite_lines(kernel_micro_rewrite_analysis: dict[str, object]) -> list[str]:
    source_rules = cast(list[dict[str, object]], kernel_micro_rewrite_analysis["source_rules"])
    lines = []
    for rule in source_rules:
        source_equation = cast(str, rule["source_equation"])
        base_equation = cast(str, rule["base_equation"])
        helper_equation = cast(str, rule["helper_equation"])
        if source_equation == "x = y ◇ (y ◇ ((x ◇ z) ◇ z))":
            lines.append(
                "- if E1 is `x = y ◇ (y ◇ ((x ◇ z) ◇ z))`, derive "
                f"`{base_equation}` and helper `{helper_equation}`; allow one local flip "
                "inside `((x ◇ z) ◇ z)` to get `x ◇ y = y ◇ ((z ◇ x) ◇ z)`."
            )
            continue
        if source_equation == "x = ((y ◇ z) ◇ x) ◇ (z ◇ y)":
            lines.append(
                "- if E1 is `x = ((y ◇ z) ◇ x) ◇ (z ◇ y)`, derive "
                f"`{base_equation}` and helper `{helper_equation}`; allow one local flip "
                "on the left nest to get `(x ◇ y) ◇ x = (y ◇ z) ◇ z`."
            )
            continue
        lines.append(
            f"- if E1 is `{source_equation}`, derive `{base_equation}` and helper "
            f"`{helper_equation}`; allow at most 2 local rewrites."
        )
    return lines


def draft_cheatsheet_from_analysis(analysis: dict[str, object]) -> str:
    pair_evaluator = cast(dict[str, object], analysis["two_element_pair_evaluator"])
    kernel_bridge_analysis = cast(dict[str, object], analysis["kernel_bridge_analysis"])
    kernel_micro_rewrite_analysis = cast(
        dict[str, object],
        analysis["kernel_micro_rewrite_analysis"],
    )

    representative_lines = [
        f"`{representative['bits']}` {representative['theory_name']}"
        for representative in cast(list[dict[str, object]], pair_evaluator["representatives"])
    ]
    kernel_catalog_lines = _kernel_catalog_lines(kernel_bridge_analysis)
    micro_rewrite_lines = _micro_rewrite_lines(kernel_micro_rewrite_analysis)

    return "\n".join(
        [
            "You answer whether Equation 1 implies Equation 2 over all magmas.",
            "Run this checklist in order. Stop at the first decisive result.",
            (
                "1. Normalize variables by first appearance. For exact source matches, "
                "substitution checks, and context checks, also allow swapping equation sides."
            ),
            "2. Immediate TRUE families:",
            "- if E1 is `x = t` and `x` never appears in `t`, answer TRUE.",
            (
                "- if E1 is `x = t`, every occurrence of `x` in `t` is on a mixed path "
                "(its root-to-leaf path uses both `L` and `R`), some other variable occurs "
                "exactly once in `t`, and the x-path set does not contain both exact `LR` and "
                "`RL`, answer TRUE."
            ),
            "- if the leftmost leaf of `t` is still `x`, do not assume collapse from shape alone.",
            "3. Tiny-model separator on carrier `{0,1}`:",
            "- read a 4-bit table `abcd` as `f(0,0)=a`, `f(0,1)=b`, `f(1,0)=c`, `f(1,1)=d`.",
            "- test these 10 representatives: " + ", ".join(representative_lines) + ".",
            "- if any representative satisfies E1 but breaks E2, answer FALSE immediately.",
            "- do not turn `no separator found` into TRUE.",
            "4. Direct TRUE checks after no separator:",
            (
                "- if E2 is a direct substitution instance of E1, answer TRUE. "
                "Use one consistent replacement for each variable in E1; equality may swap sides."
            ),
            "- if E2 is a one-hole context instance of E1, answer TRUE.",
            "5. Exact source-triggered kernel catalog after no separator:",
            (
                "- only use the following cataloged source matches after normalization and "
                "optional side-swap of E1; do not invent new kernels."
            ),
            *kernel_catalog_lines,
            (
                "- after deriving the listed kernel, accept TRUE only if E2 is an exact "
                "substitution instance or one-hole context instance of that kernel."
            ),
            "6. Exact commutativity repairs after no separator:",
            *micro_rewrite_lines,
            "- accept TRUE only if E2 is obtained exactly after at most 2 local rewrites.",
            "7. Last FALSE tie-break if nothing else fires:",
            (
                "- if you cannot mentally run all 10 tables, the fastest fallback six are "
                "`0000`, `0101`, `0011`, `0110`, `1100`, `1010`."
            ),
            (
                "- only at this last step, if E1 uses just 2 variables and either repeats more "
                "than E2 or has the same op count as E2, answer FALSE."
            ),
            "8. Never infer TRUE just because no small counterexample appeared.",
            (
                "9. Prefer FALSE from a witnessed tiny model or TRUE from an exact "
                "cataloged derivation."
            ),
        ]
    )


def draft_cheatsheet(
    catalog: LawCatalog,
    graph: ImplicationGraph,
    problems: list[PublicProblem],
) -> str:
    analysis = build_public_analysis(catalog=catalog, graph=graph, problems=problems)
    return draft_cheatsheet_from_analysis(analysis)
