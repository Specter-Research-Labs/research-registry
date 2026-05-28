from __future__ import annotations

from lenia_swarm_analysis._dispatch import Subcommand, dispatch_subcommands

COMMANDS = (
    Subcommand("facing-packet", "facing_packet", "Build Agda-facing packet"),
    Subcommand("codegen", "codegen", "Generate Agda module from facing packet"),
    Subcommand("package", "package", "Build complete Agda package"),
)


def main(argv: list[str] | None = None) -> int:
    return dispatch_subcommands(
        argv,
        prog="lenia-swarm-agda",
        description="Agda proof generation tools",
        package=__package__ or "lenia_swarm_analysis.agda",
        commands=COMMANDS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
