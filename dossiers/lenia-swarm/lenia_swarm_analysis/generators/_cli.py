from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lenia-swarm-generators",
        description="Topology generator analysis tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("analysis", add_help=False, help="Run generator extraction and analysis")
    sub.add_parser("pilot", add_help=False, help="Analyze generator pilot runs")
    sub.add_parser("cycle-transport", add_help=False, help="Analyze cycle transport evidence")
    sub.add_parser("circuit", add_help=False, help="Analyze generator circuits")
    sub.add_parser("bidirectional", add_help=False, help="Analyze bidirectional generators")
    sub.add_parser("continuation", add_help=False, help="Analyze continuation summaries")
    sub.add_parser("targets", add_help=False, help="Build generator targets from topology")
    sub.add_parser("sheets", add_help=False, help="Render generator summary sheets")

    args, remaining = parser.parse_known_args(argv)

    if args.command == "analysis":
        from .analysis import main as run

        return run(remaining)
    if args.command == "pilot":
        from .pilot import main as run

        return run(remaining)
    if args.command == "cycle-transport":
        from .cycle_transport import main as run

        return run(remaining)
    if args.command == "circuit":
        from .circuit import main as run

        return run(remaining)
    if args.command == "bidirectional":
        from .bidirectional import main as run

        return run(remaining)
    if args.command == "continuation":
        from .continuation import main as run

        return run(remaining)
    if args.command == "targets":
        from .targets import main as run

        return run(remaining)
    if args.command == "sheets":
        from .sheets import main as run

        return run(remaining)

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
