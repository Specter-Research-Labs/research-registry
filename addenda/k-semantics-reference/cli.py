from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from cli_support import (
    aggregate_rows,
    coerce_summary_row,
    format_rows,
    load_compute_request,
    load_report_rows,
    load_sweep_cases,
    write_text,
)
from demos.bitstring import run_bitstring_demo
from demos.chemotaxis import run_chemotaxis_demo
from demos.compositional import run_compositional_demo
from demos.grid import run_grid_demo
from demos.grn import run_grn_demo
from demos.hanoi import run_hanoi_demo
from demos.paper_amoeba import run_paper_amoeba_demo
from demos.paper_planarian import run_paper_planarian_demo
from demos.sorting import run_sorting_demo
from demos.synthesis import run_synthesis_demo


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    description: str
    run: Callable[[int], dict[str, Any]]


def _benchmark_cases() -> dict[str, BenchmarkCase]:
    return {
        "sorting-small": BenchmarkCase(
            name="sorting-small",
            description="Adjacent-swap sorting on 5 items with exact support enabled.",
            run=lambda seed: run_sorting_demo(n=5, trials=32, H=160, seed=seed),
        ),
        "grid-small": BenchmarkCase(
            name="grid-small",
            description="Shortest-path grid search on an 8x8 lattice.",
            run=lambda seed: run_grid_demo(size=8, trials=32, H=120, seed=seed),
        ),
        "bitstring-small": BenchmarkCase(
            name="bitstring-small",
            description="Single-bit repair on 7-bit strings with exact support enabled.",
            run=lambda seed: run_bitstring_demo(n_bits=7, trials=32, H=120, seed=seed),
        ),
    }


def _run_benchmark_case(
    case: BenchmarkCase,
    *,
    repeats: int,
    warmup: int,
    seed: int,
) -> dict[str, Any]:
    for _ in range(warmup):
        case.run(seed)

    durations: list[float] = []
    result: dict[str, Any] | None = None
    for _ in range(repeats):
        started_at = perf_counter()
        result = case.run(seed)
        durations.append(perf_counter() - started_at)

    if result is None:
        raise RuntimeError(f"benchmark case {case.name} produced no result")

    row = coerce_summary_row(result, name=case.name)
    row.update(
        {
            "description": case.description,
            "repeats": repeats,
            "seed": seed,
            "mean_wall_sec": round(sum(durations) / len(durations), 6),
            "min_wall_sec": round(min(durations), 6),
            "max_wall_sec": round(max(durations), 6),
            "exact_supported": bool(result.get("domain", {}).get("exact_supported", False)),
        }
    )
    return row


def _add_trial_args(
    parser: argparse.ArgumentParser,
    *,
    horizon_flag: str,
    horizon_help: str,
) -> None:
    parser.add_argument("--trials", type=int, required=True, help="Number of trials")
    parser.add_argument(horizon_flag, type=int, required=True, help=horizon_help)
    parser.add_argument("--seed", type=int, required=True, help="RNG seed")


def _paper_amoeba_cli_notes(result: dict[str, Any]) -> dict[str, Any]:
    result["cli"] = {
        "assumptions": [
            "MFPT uses L^2 / (prefactor * Dcell) with Dcell converted from um^2/min to um^2/s.",
            "The returned K range brackets the minimum and maximum motility coefficients.",
        ],
        "units": {
            "distance_um": "um",
            "dcell": "um^2/min",
            "tau_agent": "s",
        },
    }
    return result


def _paper_planarian_cli_notes(result: dict[str, Any]) -> dict[str, Any]:
    result["cli"] = {
        "assumptions": [
            "The blind baseline treats each neoblast cycle as one round of combinatorial search.",
            "K is derived from the covering-time estimate over C(n_responsive_genes, n_required_genes).",
        ],
        "units": {
            "neoblast_cycle": "hours",
            "tau_agent": "days",
        },
    }
    return result


def _cmd_demo_sorting(args: argparse.Namespace) -> dict[str, Any]:
    return run_sorting_demo(n=int(args.n), trials=int(args.trials), H=int(args.H), seed=int(args.seed))


def _cmd_demo_grid(args: argparse.Namespace) -> dict[str, Any]:
    return run_grid_demo(size=int(args.size), trials=int(args.trials), H=int(args.H), seed=int(args.seed))


def _cmd_demo_bitstring(args: argparse.Namespace) -> dict[str, Any]:
    return run_bitstring_demo(
        n_bits=int(args.n_bits),
        trials=int(args.trials),
        H=int(args.H),
        seed=int(args.seed),
    )


def _cmd_demo_synthesis(args: argparse.Namespace) -> dict[str, Any]:
    return run_synthesis_demo(
        max_len=int(args.max_len),
        trials=int(args.trials),
        H=int(args.H),
        seed=int(args.seed),
    )


def _cmd_demo_chemotaxis(args: argparse.Namespace) -> dict[str, Any]:
    return run_chemotaxis_demo(
        size=int(args.size),
        noise_sigma=float(args.noise_sigma),
        trials=int(args.trials),
        H=int(args.H),
        seed=int(args.seed),
    )


def _cmd_demo_hanoi(args: argparse.Namespace) -> dict[str, Any]:
    return run_hanoi_demo(
        n_disks=int(args.n_disks),
        trials=int(args.trials),
        H=int(args.H),
        seed=int(args.seed),
    )


def _cmd_demo_compositional(args: argparse.Namespace) -> dict[str, Any]:
    return run_compositional_demo(
        n_sort=int(args.n_sort),
        n_bits=int(args.n_bits),
        trials=int(args.trials),
        H_sort=int(args.H_sort),
        H_bits=int(args.H_bits),
        seed=int(args.seed),
    )


def _cmd_demo_grn(args: argparse.Namespace) -> dict[str, Any]:
    return run_grn_demo(
        n_genes=int(args.n_genes),
        trials=int(args.trials),
        H=int(args.H),
        seed=int(args.seed),
    )


def _cmd_demo_paper_amoeba(args: argparse.Namespace) -> dict[str, Any]:
    return _paper_amoeba_cli_notes(
        run_paper_amoeba_demo(
            distance_um=float(args.distance_um),
            dcell_min_um2_per_min=float(args.dcell_min),
            dcell_max_um2_per_min=float(args.dcell_max),
            tau_agent_s=float(args.tau_agent_s),
            mfpt_prefactor=float(args.mfpt_prefactor),
        )
    )


def _cmd_demo_paper_planarian(args: argparse.Namespace) -> dict[str, Any]:
    return _paper_planarian_cli_notes(
        run_paper_planarian_demo(
            n_responsive_genes=int(args.n_responsive_genes),
            n_required_genes=int(args.n_required_genes),
            neoblast_count=int(args.neoblast_count),
            neoblast_cycle_hours=float(args.neoblast_cycle_hours),
            tau_agent_days=float(args.tau_agent_days),
        )
    )


def _cmd_compute(args: argparse.Namespace) -> dict[str, Any]:
    return load_compute_request(Path(args.input)).execute()


def _cmd_sweep(args: argparse.Namespace) -> None:
    cases = load_sweep_cases(Path(args.input))
    rows = [coerce_summary_row(case.request.execute(), name=case.name) for case in cases]
    text = format_rows(rows, output_format=str(args.format))
    write_text(Path(args.output) if args.output else None, text)


def _cmd_report(args: argparse.Namespace) -> None:
    rows = load_report_rows(Path(args.input))
    aggregate = aggregate_rows(rows)
    text = format_rows(rows, output_format=str(args.format), aggregate=aggregate)
    write_text(Path(args.output) if args.output else None, text)


def _cmd_benchmark(args: argparse.Namespace) -> None:
    if int(args.repeats) < 1:
        raise ValueError("--repeats must be >= 1")
    if int(args.warmup) < 0:
        raise ValueError("--warmup must be >= 0")

    cases = _benchmark_cases()
    selected_names = list(args.case) if args.case else list(cases)
    rows = [
        _run_benchmark_case(
            cases[name],
            repeats=int(args.repeats),
            warmup=int(args.warmup),
            seed=int(args.seed),
        )
        for name in selected_names
    ]
    aggregate = aggregate_rows(rows)
    text = format_rows(rows, output_format=str(args.format), aggregate=aggregate)
    write_text(Path(args.output) if args.output else None, text)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="k-semantics-reference")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    demo = sub.add_parser("demo", help="Run built-in demos")
    demo_sub = demo.add_subparsers(dest="demo_cmd", required=True)

    sorting = demo_sub.add_parser("sorting", help="Insertion sort vs blind random adjacent swaps")
    sorting.add_argument("--n", type=int, required=True, help="Number of items")
    _add_trial_args(sorting, horizon_flag="--H", horizon_help="Horizon (max swaps)")
    sorting.set_defaults(fn=_cmd_demo_sorting)

    grid = demo_sub.add_parser("grid", help="Shortest path vs blind random walk in an open grid")
    grid.add_argument("--size", type=int, required=True, help="Grid size (size x size)")
    _add_trial_args(grid, horizon_flag="--H", horizon_help="Horizon (max steps)")
    grid.set_defaults(fn=_cmd_demo_grid)

    bitstring = demo_sub.add_parser("bitstring", help="Greedy bit repair vs blind random bit flips")
    bitstring.add_argument("--n-bits", dest="n_bits", type=int, required=True, help="Bitstring length")
    _add_trial_args(bitstring, horizon_flag="--H", horizon_help="Horizon (max bit flips)")
    bitstring.set_defaults(fn=_cmd_demo_bitstring)

    synthesis = demo_sub.add_parser("synthesis", help="Biased program search vs blind uniform sampling")
    synthesis.add_argument("--max-len", dest="max_len", type=int, required=True, help="Max program length")
    _add_trial_args(synthesis, horizon_flag="--H", horizon_help="Horizon (max program evals)")
    synthesis.set_defaults(fn=_cmd_demo_synthesis)

    chemotaxis = demo_sub.add_parser("chemotaxis", help="Gradient follower vs blind walk on 2D lattice")
    chemotaxis.add_argument("--size", type=int, required=True, help="Grid size (size x size)")
    chemotaxis.add_argument("--noise-sigma", dest="noise_sigma", type=float, default=0.1, help="Sensing noise std dev (default: 0.1)")
    _add_trial_args(chemotaxis, horizon_flag="--H", horizon_help="Horizon (max steps)")
    chemotaxis.set_defaults(fn=_cmd_demo_chemotaxis)

    hanoi = demo_sub.add_parser("hanoi", help="Optimal Hanoi vs blind random legal moves")
    hanoi.add_argument("--n-disks", dest="n_disks", type=int, required=True, help="Number of disks")
    _add_trial_args(hanoi, horizon_flag="--H", horizon_help="Horizon (max moves)")
    hanoi.set_defaults(fn=_cmd_demo_hanoi)

    compositional = demo_sub.add_parser("compositional", help="Verify K additivity over independent stages")
    compositional.add_argument("--n-sort", dest="n_sort", type=int, default=6, help="Sort list length")
    compositional.add_argument("--n-bits", dest="n_bits", type=int, default=8, help="Bitstring length")
    compositional.add_argument("--trials", type=int, required=True, help="Number of trials")
    compositional.add_argument("--H-sort", dest="H_sort", type=int, default=200, help="Sorting horizon")
    compositional.add_argument("--H-bits", dest="H_bits", type=int, default=100, help="Bitstring horizon")
    compositional.add_argument("--seed", type=int, required=True, help="RNG seed")
    compositional.set_defaults(fn=_cmd_demo_compositional)

    grn = demo_sub.add_parser("grn", help="Boolean network attractor search vs blind gene policy")
    grn.add_argument("--n-genes", dest="n_genes", type=int, required=True, help="Number of genes")
    _add_trial_args(grn, horizon_flag="--H", horizon_help="Horizon (max gene updates)")
    grn.set_defaults(fn=_cmd_demo_grn)

    paper_amoeba = demo_sub.add_parser("paper-amoeba", help="Replicate paper Sec 5.2 amoeboid chemotaxis K estimate")
    paper_amoeba.add_argument("--distance-um", dest="distance_um", type=float, default=100.0, help="Traversal distance in micrometers")
    paper_amoeba.add_argument("--dcell-min", dest="dcell_min", type=float, default=30.0, help="Lower bound random motility coefficient (um^2/min)")
    paper_amoeba.add_argument("--dcell-max", dest="dcell_max", type=float, default=40.0, help="Upper bound random motility coefficient (um^2/min)")
    paper_amoeba.add_argument("--tau-agent-s", dest="tau_agent_s", type=float, default=100.0, help="Agent traversal time in seconds")
    paper_amoeba.add_argument("--mfpt-prefactor", dest="mfpt_prefactor", type=float, default=1.0, help="MFPT denominator prefactor (1.0 for L^2/D, 2.0 for L^2/2D)")
    paper_amoeba.set_defaults(fn=_cmd_demo_paper_amoeba)

    paper_planarian = demo_sub.add_parser("paper-planarian", help="Replicate paper Sec 6.2 planarian BaCl2 combinatoric K estimate")
    paper_planarian.add_argument("--n-responsive-genes", dest="n_responsive_genes", type=int, default=2700, help="Differentially responsive gene count")
    paper_planarian.add_argument("--n-required-genes", dest="n_required_genes", type=int, default=10, help="Minimum concerted gene changes")
    paper_planarian.add_argument("--neoblast-count", dest="neoblast_count", type=int, default=100000, help="Parallel neoblast explorers")
    paper_planarian.add_argument("--neoblast-cycle-hours", dest="neoblast_cycle_hours", type=float, default=30.0, help="Neoblast cycle duration in hours")
    paper_planarian.add_argument("--tau-agent-days", dest="tau_agent_days", type=float, default=37.0, help="Observed adaptation duration in days")
    paper_planarian.set_defaults(fn=_cmd_demo_paper_planarian)

    compute = sub.add_parser("compute", help="Compute K from a JSON file of paired trials")
    compute.add_argument("--input", required=True, help="Path to paired trials JSON")
    compute.set_defaults(fn=_cmd_compute)

    sweep = sub.add_parser("sweep", help="Compute a batch of cases and render summary rows")
    sweep.add_argument("--input", required=True, help="Path to JSON or JSONL cases")
    sweep.add_argument("--format", choices=("jsonl", "csv", "markdown"), default="jsonl")
    sweep.add_argument("--output", help="Optional output file path")
    sweep.set_defaults(fn=_cmd_sweep)

    report = sub.add_parser("report", help="Render summary rows or raw compute cases as a report")
    report.add_argument("--input", required=True, help="Path to JSON or JSONL rows")
    report.add_argument("--format", choices=("jsonl", "csv", "markdown"), default="markdown")
    report.add_argument("--output", help="Optional output file path")
    report.set_defaults(fn=_cmd_report)

    benchmark = sub.add_parser("benchmark", help="Run fixed reference cases and report wall time")
    benchmark.add_argument(
        "--case",
        action="append",
        choices=tuple(_benchmark_cases()),
        help="Benchmark case to run. Repeat to select multiple cases; defaults to all cases.",
    )
    benchmark.add_argument("--repeats", type=int, default=3, help="Measured repeats per case")
    benchmark.add_argument("--warmup", type=int, default=1, help="Unmeasured warmup runs per case")
    benchmark.add_argument("--seed", type=int, default=0, help="Seed used for all benchmark runs")
    benchmark.add_argument("--format", choices=("jsonl", "csv", "markdown"), default="markdown")
    benchmark.add_argument("--output", help="Optional output file path")
    benchmark.set_defaults(fn=_cmd_benchmark)

    args = parser.parse_args(argv)
    result = args.fn(args)
    if result is None:
        return
    if args.pretty:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
