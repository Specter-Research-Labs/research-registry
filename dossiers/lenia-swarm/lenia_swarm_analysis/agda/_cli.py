from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lenia-swarm-agda",
        description="Agda proof generation tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("facing-packet", add_help=False, help="Build Agda-facing packet")
    sub.add_parser("codegen", add_help=False, help="Generate Agda module from facing packet")
    sub.add_parser("package", add_help=False, help="Build complete Agda package")

    args, remaining = parser.parse_known_args(argv)

    if args.command == "facing-packet":
        from .facing_packet import main as run

        return run(remaining)
    if args.command == "codegen":
        from .codegen import main as run

        return run(remaining)
    if args.command == "package":
        from .package import main as run

        return run(remaining)

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
