from __future__ import annotations

from lenia_swarm_analysis._dispatch import Subcommand, dispatch_subcommands

COMMANDS = (
    Subcommand("morphospace", "morphospace_cli", "Warehouse, feature, and export bridge"),
    Subcommand("topology", "topology._cli", "Persistent topology analysis tools"),
    Subcommand("transform", "transform._cli", "Transformation analysis packet tools"),
    Subcommand("generators", "generators._cli", "Topology generator analysis tools"),
    Subcommand("fiber", "fiber._cli", "Fiber candidate and continuation tools"),
    Subcommand("transport", "transport._cli", "Transport analysis tools"),
    Subcommand("hotspot", "hotspot._cli", "Hotspot analysis tools"),
    Subcommand("imgep", "imgep._cli", "IMGEP curiosity-driven exploration tools"),
    Subcommand("agda", "agda._cli", "Agda proof generation tools"),
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
        commands=COMMANDS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
