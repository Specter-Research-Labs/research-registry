from __future__ import annotations

from lenia_swarm_analysis._dispatch import Subcommand, dispatch_subcommands

COMMANDS = (
    Subcommand("history-seed", "history_seed", "Build IMGEP history seed from bundles"),
    Subcommand("hotspot-batch", "hotspot_batch", "Build IMGEP hotspot batch spec"),
    Subcommand("hotspot-report", "hotspot_report", "Build IMGEP hotspot report"),
    Subcommand("hotspot-export", "hotspot_export", "Export IMGEP hotspot results"),
)


def main(argv: list[str] | None = None) -> int:
    return dispatch_subcommands(
        argv,
        prog="lenia-swarm-imgep",
        description="IMGEP curiosity-driven exploration tools",
        package=__package__ or "lenia_swarm_analysis.imgep",
        commands=COMMANDS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
