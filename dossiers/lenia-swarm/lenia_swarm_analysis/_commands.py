from __future__ import annotations

from lenia_swarm_analysis._dispatch import CommandGroup, Subcommand

OBSERVER = CommandGroup(
    name="observer",
    module="observer._cli",
    help="Prequential observer measurements on replay states",
    description="Epiplexity, transfer geometry and conditional codelength of replayed creatures",
    package="lenia_swarm_analysis.observer",
    commands=(
        Subcommand("measure", "measure", "S and H per creature and observer"),
        Subcommand("transfer", "transfer", "Cross-creature transfer matrix"),
        Subcommand("conditional", "conditional", "Conditional codelength for creature pairs"),
    ),
)

ANATOMICAL_COMPILER = CommandGroup(
    name="anatomical-compiler",
    module="anatomical_compiler._cli",
    help="Shape, behaviour and rule-inverse measurements of the anatomical compiler report",
    description="Measurements behind the anatomical compiler report",
    package="lenia_swarm_analysis.anatomical_compiler",
    commands=(
        Subcommand("trajectory-inverse", "trajectory_inverse",
                   "Prepare paired still and trajectory inverse searches, or refine a winner"),
        Subcommand("render-trajectory-inverse", "render_trajectory_inverse",
                   "Render assets for a paired trajectory-inverse experiment"),
        Subcommand("behavior-spread", "behavior_spread", "Behaviour spread among shape mates"),
        Subcommand("fiber-locality", "fiber_locality", "Rule distance between shape neighbours"),
        Subcommand("functional-map", "functional_map", "Complexity against drift after damage"),
        Subcommand("functional-morphospace", "functional_morphospace",
                   "PCA over the behavioural metrics of a harvest"),
        Subcommand("shape-function-coupling", "shape_function_coupling",
                   "Behaviour variance explained by shape descriptors"),
        Subcommand("shape-function-survey", "shape_function_survey",
                   "Shape-function coupling across harvests"),
    ),
)

ROOT_COMMANDS = (
    Subcommand("morphospace", "morphospace_cli", "Warehouse, feature, and export bridge"),
    Subcommand("waddington", "waddington._cli", "Waddington landscape study stages"),
    Subcommand(OBSERVER.name, OBSERVER.module, OBSERVER.help),
    Subcommand(ANATOMICAL_COMPILER.name, ANATOMICAL_COMPILER.module, ANATOMICAL_COMPILER.help),
    Subcommand("chakazul-presets", "chakazul_presets", "Extract Chakazul Lenia presets"),
    Subcommand("compact", "compact", "Rewrite JSON artifacts into the current storage format"),
    Subcommand(
        "coherent-body-pilot", "coherent_body_pilot", "Cell-swap pilot on long-lived Flow bodies"
    ),
)
