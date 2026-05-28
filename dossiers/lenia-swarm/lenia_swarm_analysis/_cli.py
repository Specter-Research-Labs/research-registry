from __future__ import annotations

from lenia_swarm_analysis._commands import ROOT_COMMANDS
from lenia_swarm_analysis._dispatch import dispatch_subcommands


def main(argv: list[str] | None = None) -> int:
    return dispatch_subcommands(
        argv,
        prog="lenia-swarm-analysis",
        description=(
            "Canonical Python analysis surface for Lenia swarm artifacts. "
            "LeniaCLI and LeniaStudio own simulation/runtime workflows; this command "
            "routes corpus analysis, TDA, packets, and warehouse bridge operations."
        ),
        package="lenia_swarm_analysis",
        commands=ROOT_COMMANDS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
