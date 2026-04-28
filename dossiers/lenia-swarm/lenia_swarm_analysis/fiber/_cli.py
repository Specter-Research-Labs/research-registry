from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lenia-swarm-fiber",
        description="Fiber candidate and continuation tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("candidates", add_help=False, help="Select fiber candidates from manifests")
    sub.add_parser("cycle-lift", add_help=False, help="Build cycle-lift packet from topology")
    sub.add_parser("continuation", add_help=False, help="Run stateful fiber continuation")
    sub.add_parser("continuation-batch", add_help=False, help="Run batch of stateful continuations")

    args, remaining = parser.parse_known_args(argv)

    if args.command == "candidates":
        from .candidates import main as run

        return run(remaining)
    if args.command == "cycle-lift":
        from .cycle_lift import main as run

        return run(remaining)
    if args.command == "continuation":
        from .continuation import main as run

        return run(remaining)
    if args.command == "continuation-batch":
        from .continuation_batch import main as run

        return run(remaining)

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
