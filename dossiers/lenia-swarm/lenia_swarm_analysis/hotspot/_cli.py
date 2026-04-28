from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lenia-swarm-hotspot",
        description="Hotspot analysis tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("packet", add_help=False, help="Build hotspot packet from sources")
    sub.add_parser("neighborhood", add_help=False, help="Build hotspot neighborhood packet")
    sub.add_parser("refresh-batch", add_help=False, help="Build transport refresh batch spec")
    sub.add_parser("refresh-report", add_help=False, help="Build hotspot transport refresh report")

    args, remaining = parser.parse_known_args(argv)

    if args.command == "packet":
        from .packet import main as run

        return run(remaining)
    if args.command == "neighborhood":
        from .neighborhood import main as run

        return run(remaining)
    if args.command == "refresh-batch":
        from .refresh_batch import main as run

        return run(remaining)
    if args.command == "refresh-report":
        from .refresh_report import main as run

        return run(remaining)

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
