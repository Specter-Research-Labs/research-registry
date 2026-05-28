from __future__ import annotations

from lenia_swarm_analysis._dispatch import Subcommand, dispatch_subcommands

COMMANDS = (
    Subcommand("candidates", "candidates", "Select fiber candidates from manifests"),
    Subcommand("cycle-lift", "cycle_lift", "Build cycle-lift packet from topology"),
    Subcommand("continuation", "continuation", "Run stateful fiber continuation"),
    Subcommand("continuation-batch", "continuation_batch", "Run batch of stateful continuations"),
)


def main(argv: list[str] | None = None) -> int:
    return dispatch_subcommands(
        argv,
        prog="lenia-swarm-fiber",
        description="Fiber candidate and continuation tools",
        package=__package__ or "lenia_swarm_analysis.fiber",
        commands=COMMANDS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
