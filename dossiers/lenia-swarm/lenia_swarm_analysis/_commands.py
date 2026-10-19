from __future__ import annotations

from lenia_swarm_analysis._dispatch import CommandGroup, Subcommand

ANALYSIS_GROUPS = (
    CommandGroup(
        name="morphospace",
        module="morphospace_cli",
        help="Warehouse, feature, and export bridge",
        prog="lenia-swarm-morphospace",
        description="Canonical warehouse lifecycle for lenia-swarm morphospace analysis",
        package="lenia_swarm_analysis",
        commands=(),
    ),
    CommandGroup(
        name="observer",
        module="observer._cli",
        help="Prequential observer measurements on replay states",
        prog="lenia-swarm-observer",
        description="Epiplexity, transfer geometry and conditional codelength of replayed creatures",
        package="lenia_swarm_analysis.observer",
        commands=(
            Subcommand("measure", "measure", "S and H per creature and observer"),
            Subcommand("transfer", "transfer", "Cross-creature transfer matrix"),
            Subcommand("conditional", "conditional", "Conditional codelength for creature pairs"),
        ),
    ),
    CommandGroup(
        name="agda",
        module="agda._cli",
        help="Agda proof generation tools",
        prog="lenia-swarm-agda",
        description="Agda proof generation tools",
        package="lenia_swarm_analysis.agda",
        commands=(
            Subcommand("facing-packet", "facing_packet", "Build Agda-facing packet"),
            Subcommand("codegen", "codegen", "Generate Agda module from facing packet"),
            Subcommand("package", "package", "Build complete Agda package"),
        ),
    ),
)

GROUPS_BY_NAME = {group.name: group for group in ANALYSIS_GROUPS}

STANDALONE_COMMANDS = (
    Subcommand("chakazul-presets", "chakazul_presets", "Extract Chakazul Lenia presets"),
)

ROOT_COMMANDS = (
    *(Subcommand(group.name, group.module, group.help) for group in ANALYSIS_GROUPS),
    *STANDALONE_COMMANDS,
)
