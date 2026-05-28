from __future__ import annotations

from lenia_swarm_analysis._dispatch import Subcommand, dispatch_subcommands

COMMANDS = (
    Subcommand("analyze", "analysis", "Compute persistent topology summaries"),
    Subcommand("compare", "compare", "Compare topology across representations"),
    Subcommand("robustness", "robustness", "Subsample robustness analysis"),
)


def main(argv: list[str] | None = None) -> int:
    return dispatch_subcommands(
        argv,
        prog="lenia-swarm-topology",
        description="Persistent topology analysis tools",
        package=__package__ or "lenia_swarm_analysis.topology",
        commands=COMMANDS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
