from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lenia-swarm-transport",
        description="Transport analysis tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("loop", add_help=False, help="Build loop transport packet")
    sub.add_parser("scale-report", add_help=False, help="Build transport scale report")
    sub.add_parser("validation-batch", add_help=False, help="Build transport validation batch spec")
    sub.add_parser("validation-report", add_help=False, help="Build transport validation report")
    sub.add_parser("repro-report", add_help=False, help="Build transport reproducibility report")
    sub.add_parser("dense-report", add_help=False, help="Build transport dense report")
    sub.add_parser("winner", add_help=False, help="Build transport winner packet")
    sub.add_parser("confidence-report", add_help=False, help="Build transport confidence report")

    args, remaining = parser.parse_known_args(argv)

    if args.command == "loop":
        from .loop import main as run

        return run(remaining)
    if args.command == "scale-report":
        from .scale_report import main as run

        return run(remaining)
    if args.command == "validation-batch":
        from .validation_batch import main as run

        return run(remaining)
    if args.command == "validation-report":
        from .validation_report import main as run

        return run(remaining)
    if args.command == "repro-report":
        from .repro_report import main as run

        return run(remaining)
    if args.command == "dense-report":
        from .dense_report import main as run

        return run(remaining)
    if args.command == "winner":
        from .winner import main as run

        return run(remaining)
    if args.command == "confidence-report":
        from .confidence_report import main as run

        return run(remaining)

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
