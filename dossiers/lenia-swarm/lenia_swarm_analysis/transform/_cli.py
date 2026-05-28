from __future__ import annotations

from lenia_swarm_analysis._dispatch import Subcommand, dispatch_subcommands

COMMANDS = (
    Subcommand("replay", "replay", "Build transformation replay packet"),
    Subcommand("atlas", "atlas", "Build transformation atlas packet"),
    Subcommand("focal", "focal", "Build transformation focal packet"),
    Subcommand("topology", "topology_packet", "Build transformation topology packet"),
    Subcommand("family-comparison", "family_comparison", "Build family comparison packet"),
)


def main(argv: list[str] | None = None) -> int:
    return dispatch_subcommands(
        argv,
        prog="lenia-swarm-transform",
        description="Transformation analysis packet tools",
        package=__package__ or "lenia_swarm_analysis.transform",
        commands=COMMANDS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
