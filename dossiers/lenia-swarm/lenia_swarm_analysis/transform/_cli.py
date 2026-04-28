from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lenia-swarm-transform",
        description="Transformation analysis packet tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("replay", add_help=False, help="Build transformation replay packet")
    sub.add_parser("atlas", add_help=False, help="Build transformation atlas packet")
    sub.add_parser("focal", add_help=False, help="Build transformation focal packet")
    sub.add_parser("topology", add_help=False, help="Build transformation topology packet")
    sub.add_parser("family-comparison", add_help=False, help="Build family comparison packet")

    args, remaining = parser.parse_known_args(argv)

    if args.command == "replay":
        from .replay import main as run

        return run(remaining)
    if args.command == "atlas":
        from .atlas import main as run

        return run(remaining)
    if args.command == "focal":
        from .focal import main as run

        return run(remaining)
    if args.command == "topology":
        from .topology_packet import main as run

        return run(remaining)
    if args.command == "family-comparison":
        from .family_comparison import main as run

        return run(remaining)

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
