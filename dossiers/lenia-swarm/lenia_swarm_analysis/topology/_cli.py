from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lenia-swarm-topology",
        description="Persistent topology analysis tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("analyze", add_help=False, help="Compute persistent topology summaries")
    sub.add_parser("compare", add_help=False, help="Compare topology across representations")
    sub.add_parser("robustness", add_help=False, help="Subsample robustness analysis")

    args, remaining = parser.parse_known_args(argv)

    if args.command == "analyze":
        from .analysis import main as run

        return run(remaining)
    if args.command == "compare":
        from .compare import main as run

        return run(remaining)
    if args.command == "robustness":
        from .robustness import main as run

        return run(remaining)

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
