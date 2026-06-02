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
        name="topology",
        module="topology._cli",
        help="Persistent topology analysis tools",
        prog="lenia-swarm-topology",
        description="Persistent topology analysis tools",
        package="lenia_swarm_analysis.topology",
        commands=(
            Subcommand("analyze", "analysis", "Compute persistent topology summaries"),
            Subcommand("compare", "compare", "Compare topology across representations"),
            Subcommand("robustness", "robustness", "Subsample robustness analysis"),
        ),
    ),
    CommandGroup(
        name="transform",
        module="transform._cli",
        help="Transformation analysis packet tools",
        prog="lenia-swarm-transform",
        description="Transformation analysis packet tools",
        package="lenia_swarm_analysis.transform",
        commands=(
            Subcommand("replay", "replay", "Build transformation replay packet"),
            Subcommand("atlas", "atlas", "Build transformation atlas packet"),
            Subcommand("focal", "focal", "Build transformation focal packet"),
            Subcommand("topology", "topology_packet", "Build transformation topology packet"),
            Subcommand("family-comparison", "family_comparison", "Build family comparison packet"),
        ),
    ),
    CommandGroup(
        name="generators",
        module="generators._cli",
        help="Topology generator analysis tools",
        prog="lenia-swarm-generators",
        description="Topology generator analysis tools",
        package="lenia_swarm_analysis.generators",
        commands=(
            Subcommand("analysis", "analysis", "Run generator extraction and analysis"),
            Subcommand("pilot", "pilot", "Analyze generator pilot runs"),
            Subcommand("cycle-transport", "cycle_transport", "Analyze cycle transport evidence"),
            Subcommand("circuit", "circuit", "Analyze generator circuits"),
            Subcommand("bidirectional", "bidirectional", "Analyze bidirectional generators"),
            Subcommand("continuation", "continuation", "Analyze continuation summaries"),
            Subcommand("targets", "targets", "Build generator targets from topology"),
            Subcommand("sheets", "sheets", "Render generator summary sheets"),
        ),
    ),
    CommandGroup(
        name="fiber",
        module="fiber._cli",
        help="Fiber candidate and continuation tools",
        prog="lenia-swarm-fiber",
        description="Fiber candidate and continuation tools",
        package="lenia_swarm_analysis.fiber",
        commands=(
            Subcommand("candidates", "candidates", "Select fiber candidates from manifests"),
            Subcommand("cycle-lift", "cycle_lift", "Build cycle-lift packet from topology"),
            Subcommand("continuation", "continuation", "Run stateful fiber continuation"),
            Subcommand(
                "continuation-batch",
                "continuation_batch",
                "Run batch of stateful continuations",
            ),
        ),
    ),
    CommandGroup(
        name="transport",
        module="transport._cli",
        help="Transport analysis tools",
        prog="lenia-swarm-transport",
        description="Transport analysis tools",
        package="lenia_swarm_analysis.transport",
        commands=(
            Subcommand("loop", "loop", "Build loop transport packet"),
            Subcommand("scale-report", "scale_report", "Build transport scale report"),
            Subcommand(
                "validation-batch",
                "validation_batch",
                "Build transport validation batch spec",
            ),
            Subcommand(
                "validation-report",
                "validation_report",
                "Build transport validation report",
            ),
            Subcommand("repro-report", "repro_report", "Build transport reproducibility report"),
            Subcommand("dense-report", "dense_report", "Build transport dense report"),
            Subcommand("winner", "winner", "Build transport winner packet"),
            Subcommand(
                "confidence-report",
                "confidence_report",
                "Build transport confidence report",
            ),
        ),
    ),
    CommandGroup(
        name="hotspot",
        module="hotspot._cli",
        help="Hotspot analysis tools",
        prog="lenia-swarm-hotspot",
        description="Hotspot analysis tools",
        package="lenia_swarm_analysis.hotspot",
        commands=(
            Subcommand("packet", "packet", "Build hotspot packet from sources"),
            Subcommand("neighborhood", "neighborhood", "Build hotspot neighborhood packet"),
            Subcommand("refresh-batch", "refresh_batch", "Build transport refresh batch spec"),
            Subcommand(
                "refresh-report",
                "refresh_report",
                "Build hotspot transport refresh report",
            ),
        ),
    ),
    CommandGroup(
        name="imgep",
        module="imgep._cli",
        help="IMGEP curiosity-driven exploration tools",
        prog="lenia-swarm-imgep",
        description="IMGEP curiosity-driven exploration tools",
        package="lenia_swarm_analysis.imgep",
        commands=(
            Subcommand("history-seed", "history_seed", "Build IMGEP history seed from bundles"),
            Subcommand("hotspot-batch", "hotspot_batch", "Build IMGEP hotspot batch spec"),
            Subcommand("hotspot-report", "hotspot_report", "Build IMGEP hotspot report"),
            Subcommand("hotspot-export", "hotspot_export", "Export IMGEP hotspot results"),
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
    Subcommand("attractor-packet", "attractor_packet", "Build attractor packet"),
    Subcommand("arrangement-packet", "arrangement_packet", "Build arrangement packet"),
    Subcommand(
        "empirical-fibration-packet",
        "empirical_fibration_packet",
        "Build empirical fibration packet",
    ),
    Subcommand("local-results-library", "local_results_library", "Build local results library"),
    Subcommand("loop-variant-report", "loop_variant_report", "Build loop variant report"),
    Subcommand("chakazul-presets", "chakazul_presets", "Extract Chakazul Lenia presets"),
)

ROOT_COMMANDS = (
    *(Subcommand(group.name, group.module, group.help) for group in ANALYSIS_GROUPS),
    *STANDALONE_COMMANDS,
)
