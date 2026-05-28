from __future__ import annotations

from lenia_swarm_analysis._dispatch import Subcommand, dispatch_subcommands

COMMANDS = (
    Subcommand("loop", "loop", "Build loop transport packet"),
    Subcommand("scale-report", "scale_report", "Build transport scale report"),
    Subcommand("validation-batch", "validation_batch", "Build transport validation batch spec"),
    Subcommand("validation-report", "validation_report", "Build transport validation report"),
    Subcommand("repro-report", "repro_report", "Build transport reproducibility report"),
    Subcommand("dense-report", "dense_report", "Build transport dense report"),
    Subcommand("winner", "winner", "Build transport winner packet"),
    Subcommand("confidence-report", "confidence_report", "Build transport confidence report"),
)


def main(argv: list[str] | None = None) -> int:
    return dispatch_subcommands(
        argv,
        prog="lenia-swarm-transport",
        description="Transport analysis tools",
        package=__package__ or "lenia_swarm_analysis.transport",
        commands=COMMANDS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
