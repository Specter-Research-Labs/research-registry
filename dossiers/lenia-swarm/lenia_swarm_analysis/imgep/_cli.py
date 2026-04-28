from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lenia-swarm-imgep",
        description="IMGEP curiosity-driven exploration tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("history-seed", add_help=False, help="Build IMGEP history seed from bundles")
    sub.add_parser("hotspot-batch", add_help=False, help="Build IMGEP hotspot batch spec")
    sub.add_parser("hotspot-report", add_help=False, help="Build IMGEP hotspot report")
    sub.add_parser("hotspot-export", add_help=False, help="Export IMGEP hotspot results")

    args, remaining = parser.parse_known_args(argv)

    if args.command == "history-seed":
        from .history_seed import main as run

        return run(remaining)
    if args.command == "hotspot-batch":
        from .hotspot_batch import main as run

        return run(remaining)
    if args.command == "hotspot-report":
        from .hotspot_report import main as run

        return run(remaining)
    if args.command == "hotspot-export":
        from .hotspot_export import main as run

        return run(remaining)

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
