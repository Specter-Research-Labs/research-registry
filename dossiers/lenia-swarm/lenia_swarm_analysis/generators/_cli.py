from __future__ import annotations

from lenia_swarm_analysis._dispatch import Subcommand, dispatch_subcommands

COMMANDS = (
    Subcommand("analysis", "analysis", "Run generator extraction and analysis"),
    Subcommand("pilot", "pilot", "Analyze generator pilot runs"),
    Subcommand("cycle-transport", "cycle_transport", "Analyze cycle transport evidence"),
    Subcommand("circuit", "circuit", "Analyze generator circuits"),
    Subcommand("bidirectional", "bidirectional", "Analyze bidirectional generators"),
    Subcommand("continuation", "continuation", "Analyze continuation summaries"),
    Subcommand("targets", "targets", "Build generator targets from topology"),
    Subcommand("sheets", "sheets", "Render generator summary sheets"),
)


def main(argv: list[str] | None = None) -> int:
    return dispatch_subcommands(
        argv,
        prog="lenia-swarm-generators",
        description="Topology generator analysis tools",
        package=__package__ or "lenia_swarm_analysis.generators",
        commands=COMMANDS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
