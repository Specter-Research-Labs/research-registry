from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from analysis import write_public_analysis
from cheatsheet import (
    draft_cheatsheet,
    draft_cheatsheet_from_analysis,
)
from graph import load_graph
from laws import load_law_catalog
from paths import runtime_layout
from public_benchmark import load_public_problems
from sources import fetch_sources, require_source_files


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="equational-theories-distillation",
        description="Distillation workbench for the Equational Theories Stage 1 benchmark."
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=None,
        help="Override runtime/cache root. Default uses SPECTER_RUNTIME_ROOT or ../../tmp/.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Download the pinned source assets.")
    fetch_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Redownload even when the local source file already exists.",
    )

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Map the public problems into the 4694-law universe and write analysis JSON.",
    )
    analyze_parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Override analysis JSON output path.",
    )
    analyze_parser.add_argument(
        "--size4-sat-timeout-ms",
        type=int,
        default=0,
        help=(
            "Run explicit size-4 SAT search on residual false cases "
            "with this per-problem timeout."
        ),
    )
    analyze_parser.add_argument(
        "--size5-sat-timeout-ms",
        type=int,
        default=0,
        help=(
            "Run explicit size-5 SAT search on false cases that remain after "
            "the size-4 SAT pass."
        ),
    )

    cheatsheet_parser = subparsers.add_parser(
        "draft-cheatsheet",
        help="Write a first-pass cheatsheet draft from the current public analysis.",
    )
    cheatsheet_parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Override cheatsheet output path.",
    )
    cheatsheet_parser.add_argument(
        "--analysis",
        type=Path,
        default=None,
        help=(
            "Reuse an existing analysis JSON instead of recomputing. "
            "If omitted, the runtime public-analysis.json is used when present."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    layout = runtime_layout(args.runtime_root)

    if args.command == "fetch":
        resolved = fetch_sources(layout, refresh=args.refresh)
        print(f"runtime_root={layout.root}")
        for name, path in sorted(resolved.items()):
            print(f"{name}={path}")
        print(f"manifest={layout.sources_dir / 'sources.manifest.json'}")
        return 0

    sources = require_source_files(layout)
    catalog = load_law_catalog(sources["equations"])
    graph = load_graph(sources["graph"], law_count=len(catalog.equations))
    problems = load_public_problems(
        normal_path=sources["normal"],
        hard_path=sources["hard"],
        catalog=catalog,
        graph=graph,
    )

    if args.command == "analyze":
        out_path = args.out or (layout.analysis_dir / "public-analysis.json")
        analysis = write_public_analysis(
            path=out_path,
            catalog=catalog,
            graph=graph,
            problems=problems,
            size4_sat_timeout_ms=args.size4_sat_timeout_ms,
            size5_sat_timeout_ms=args.size5_sat_timeout_ms,
        )
        label_agreement = cast(dict[str, object], analysis["mapped_label_agreement"])
        countermodels = cast(dict[str, object], analysis["two_element_countermodel_cover"])
        theorem_rules = cast(dict[str, object], analysis["theorem_backed_true_rules"])
        theorem_cover = cast(dict[str, object], theorem_rules["combined_true_rule_cover"])
        pair_evaluator = cast(dict[str, object], analysis["two_element_pair_evaluator"])
        sat_search = cast(dict[str, object], analysis["size4_sat_search"])
        size5_sat_search = cast(dict[str, object], analysis["size5_sat_search"])
        combined_surface = cast(dict[str, object], analysis["combined_decision_surface"])
        kernel_bridge_analysis = cast(dict[str, object], analysis["kernel_bridge_analysis"])
        kernel_bridge_candidate_surface = cast(
            dict[str, object],
            analysis["kernel_bridge_candidate_surface"],
        )
        kernel_micro_rewrite_analysis = cast(
            dict[str, object],
            analysis["kernel_micro_rewrite_analysis"],
        )
        kernel_micro_rewrite_candidate_surface = cast(
            dict[str, object],
            analysis["kernel_micro_rewrite_candidate_surface"],
        )
        canonical_size5_unknown_followup = cast(
            dict[str, object],
            analysis["canonical_size5_unknown_followup"],
        )
        print(f"problems={analysis['problem_count']}")
        print(f"label_agreement={label_agreement['correct']}/{label_agreement['total']}")
        print(
            "theorem_true_coverage="
            f"{theorem_cover['public_true_count']}/{theorem_rules['public_true_problem_count']}"
        )
        print(
            "pair_evaluator_false_coverage="
            f"{pair_evaluator['false_separated_problem_count']}/{pair_evaluator['false_problem_count']}"
        )
        print(
            "two_element_false_coverage="
            f"{countermodels['covered_false_problem_count']}/{countermodels['false_problem_count']}"
        )
        if bool(sat_search.get("enabled")):
            print(
                "size4_sat_coverage="
                f"{sat_search['covered_count']}/{sat_search['residual_after_three_element_count']}"
            )
            print(f"size4_sat_statuses={sat_search['pair_status_counts']}")
        if bool(size5_sat_search.get("enabled")):
            print(
                "size5_sat_coverage="
                f"{size5_sat_search['covered_count']}/{size5_sat_search['residual_after_size4_count']}"
            )
            print(f"size5_sat_statuses={size5_sat_search['pair_status_counts']}")
        print(
            "combined_surface="
            f"{combined_surface['decided_problem_count']}/{analysis['problem_count']}"
        )
        print(
            "kernel_bridge_candidate_surface="
            f"{kernel_bridge_candidate_surface['decided_problem_count']}/{analysis['problem_count']}"
        )
        print(
            "kernel_bridge_true_tail="
            f"{kernel_bridge_analysis['covered_public_problem_count']}/"
            f"{kernel_bridge_analysis['remaining_true_problem_count']}"
        )
        print(
            "kernel_micro_rewrite_candidate_surface="
            f"{kernel_micro_rewrite_candidate_surface['decided_problem_count']}/"
            f"{analysis['problem_count']}"
        )
        print(
            "kernel_micro_rewrite_true_tail="
            f"{kernel_micro_rewrite_analysis['covered_public_problem_count']}/"
            f"{kernel_micro_rewrite_analysis['remaining_true_problem_count']}"
        )
        if bool(canonical_size5_unknown_followup.get("enabled")):
            print(
                "canonical_size5_unknown_followup="
                f"{canonical_size5_unknown_followup['pair_status_counts']}"
            )
        print(f"analysis={out_path}")
        return 0

    if args.command == "draft-cheatsheet":
        out_path = args.out or (layout.analysis_dir / "cheatsheet-v0.txt")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        analysis_path = args.analysis or (layout.analysis_dir / "public-analysis.json")
        if analysis_path.exists():
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
            cheatsheet = draft_cheatsheet_from_analysis(analysis)
        else:
            cheatsheet = draft_cheatsheet(catalog=catalog, graph=graph, problems=problems)
        out_path.write_text(cheatsheet + "\n", encoding="utf-8")
        print(f"cheatsheet={out_path}")
        print(f"bytes={out_path.stat().st_size}")
        return 0

    raise AssertionError(f"unsupported command: {args.command}")
