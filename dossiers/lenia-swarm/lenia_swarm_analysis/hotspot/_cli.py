from __future__ import annotations

from lenia_swarm_analysis._dispatch import Subcommand, dispatch_subcommands

COMMANDS = (
    Subcommand("packet", "packet", "Build hotspot packet from sources"),
    Subcommand("neighborhood", "neighborhood", "Build hotspot neighborhood packet"),
    Subcommand("refresh-batch", "refresh_batch", "Build transport refresh batch spec"),
    Subcommand("refresh-report", "refresh_report", "Build hotspot transport refresh report"),
)


def main(argv: list[str] | None = None) -> int:
    return dispatch_subcommands(
        argv,
        prog="lenia-swarm-hotspot",
        description="Hotspot analysis tools",
        package=__package__ or "lenia_swarm_analysis.hotspot",
        commands=COMMANDS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
