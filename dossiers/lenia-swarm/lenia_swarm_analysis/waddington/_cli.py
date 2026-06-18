"""CLI for the Waddington landscape study.

Stages (the replay-with-capture between build-inputs and ingest is a LeniaCLI step):
  build-inputs : sample seeded export indices per config from the run shards
  (replay)     : .build/release/LeniaCLI publish replay --input <inputs/HASH.jsonl> \
                     --output <replay/HASH> --no-promotion --development-trace --trace-interval 25
  ingest       : ingest replay runs into the study warehouse (development_samples + axes)
  analyze      : compute endpoint + drift-field landscapes for all configs
  render       : write figures (needs matplotlib)
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lenia-swarm-waddington", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build-inputs", help="sample seeded export indices per config")
    sub.add_parser("ingest", help="ingest replay-with-capture runs into the study warehouse")
    sub.add_parser("analyze", help="compute endpoint + drift landscapes")
    sub.add_parser("render", help="render figures")
    sub.add_parser("atlas", help="morphospace atlas: fingerprints at their landscape location")
    sub.add_parser("biascheck", help="split-half sampling robustness check")
    sub.add_parser("random-inputs", help="synthesize uniform-random-genotype scout dirs")
    sub.add_parser("ingest-random", help="ingest random-genotype replay runs")
    sub.add_parser("compare", help="contrast random-genotype vs harvest landscapes")
    sub.add_parser("motion-compare", help="contrast score-rewarded motion: random vs harvest")
    sub.add_parser("dynamics", help="flux-vs-behavior + developmental program clustering")
    sub.add_parser("perturb-inputs", help="synthesize baseline+ablated scout dirs")
    sub.add_parser("ingest-perturb", help="ingest baseline+perturbed replay runs")
    sub.add_parser("perturb-analyze", help="valley depth vs recovery from ablation")
    sub.add_parser("families", help="curated-family morphospace from the compendium taxonomy")
    sub.add_parser("family-generate", help="replay real family configs with capture + ingest")
    sub.add_parser("family-analyze", help="family-coloured 16-axis shape landscape + programs")
    sub.add_parser("family-behavior", help="behaviour fingerprints: families by behaviour vs shape")
    sub.add_parser("family-tda", help="cubical PH + Zernike: family/species separability")
    sub.add_parser("family-fidelity", help="audit replay fidelity + TDA robustness")
    sub.add_parser("family-representatives", help="one canonical Flow-Lenia creature per family")
    sub.add_parser("panels", help="3D + top-down landscape panels per rule")
    sub.add_parser("bifurcation", help="genotype-space (m,s) bifurcation slice + cusp/bistability")
    args = parser.parse_args(argv)

    if args.command == "build-inputs":
        from .build_inputs import build_all
        build_all()
    elif args.command == "ingest":
        from .ingest import ingest_all
        ingest_all()
    elif args.command == "analyze":
        from .landscape import build
        build()
    elif args.command == "render":
        from .render import render
        render()
    elif args.command == "atlas":
        from .visuals import atlas
        atlas()
    elif args.command == "biascheck":
        from .visuals import biascheck
        biascheck()
    elif args.command == "random-inputs":
        from .random_experiment import build_random_inputs
        build_random_inputs()
    elif args.command == "ingest-random":
        from .random_experiment import ingest_random
        ingest_random()
    elif args.command == "compare":
        from .random_experiment import compare
        compare()
    elif args.command == "motion-compare":
        from .random_experiment import motion_compare
        motion_compare()
    elif args.command == "dynamics":
        from .dynamics import build
        build()
    elif args.command == "perturb-inputs":
        from .perturbation import build_perturb_inputs
        build_perturb_inputs()
    elif args.command == "ingest-perturb":
        from .perturbation import ingest_perturb
        ingest_perturb()
    elif args.command == "perturb-analyze":
        from .perturbation import analyze
        analyze()
    elif args.command == "families":
        from .families import build
        build()
    elif args.command == "family-generate":
        from .family_pipeline import generate
        generate()
    elif args.command == "family-analyze":
        from .family_pipeline import analyze
        analyze()
    elif args.command == "family-behavior":
        from .behavior import build
        build()
    elif args.command == "family-tda":
        from .tda import build
        build()
    elif args.command == "family-fidelity":
        from .fidelity import build
        build()
    elif args.command == "family-representatives":
        from .representatives import build
        build()
    elif args.command == "panels":
        from .panels import build
        build()
    elif args.command == "bifurcation":
        from .bifurcation import build
        build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
