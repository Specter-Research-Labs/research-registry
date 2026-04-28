from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MotifCandidate:
    slug: str
    name: str
    surface_kind: str
    readiness: str
    upstream_surface: str
    summary: str
    first_claims: tuple[str, ...]
    first_metrics: tuple[str, ...]
    first_tasks: tuple[str, ...]
    upstream_links: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


CATALOG: tuple[MotifCandidate, ...] = (
    MotifCandidate(
        slug="lamina_cartridge",
        name="Lamina Cartridge Executable Circuit",
        surface_kind="tutorial",
        readiness="immediate",
        upstream_surface="FlyBrainLab Tutorials",
        summary=(
            "Executable visual circuit tutorial and the cleanest first surface for "
            "pattern-sensitive recovery, local lesions, and compact circuit intervention sweeps."
        ),
        first_claims=(
            "pattern_sensitive_recovery",
            "collective_controller",
            "competency_atlas",
        ),
        first_metrics=(
            "lesion_tolerance",
            "reroute_capacity",
            "basin_preservation",
            "structured_vs_noise_gap",
        ),
        first_tasks=(
            "structured_vs_shuffled_visual_drive",
            "single_neuron_ablation",
            "synapse_dropout_sweep",
        ),
        upstream_links=(
            "https://github.com/FlyBrainLab/Tutorials/blob/master/tutorials/cartridge/Cartridge.ipynb",
        ),
    ),
    MotifCandidate(
        slug="osn_ephys",
        name="Olfactory Sensory Neuron Ephys Tutorial",
        surface_kind="tutorial",
        readiness="immediate",
        upstream_surface="FlyBrainLab Tutorials",
        summary=(
            "Olfactory tutorial surface for structured-vs-noise assays, input discrimination, and "
            "later lesion-resilience tests on compact sensory motifs."
        ),
        first_claims=(
            "pattern_sensitive_recovery",
            "competency_atlas",
        ),
        first_metrics=(
            "structured_vs_noise_gap",
            "efficiency_over_blind",
            "lesion_tolerance",
        ),
        first_tasks=(
            "odor_panel_vs_shuffled_panel",
            "input_channel_dropout",
            "stimulus_generalization",
        ),
        upstream_links=(
            "https://github.com/FlyBrainLab/Tutorials/blob/master/tutorials/osn_ephys_tutorial/OSN_ephys_tutorial.ipynb",
        ),
    ),
    MotifCandidate(
        slug="optic_lobe_1_0",
        name="Optic Lobe Dataset 1.0",
        surface_kind="dataset",
        readiness="near_term",
        upstream_surface="FlyBrainLab Datasets",
        summary=(
            "Current visual-system dataset surface for scaling up from the lamina tutorial into a "
            "larger motif panel without leaving the same sensory domain."
        ),
        first_claims=(
            "pattern_sensitive_recovery",
            "collective_controller",
            "competency_atlas",
        ),
        first_metrics=(
            "lesion_tolerance",
            "reroute_capacity",
            "structured_vs_noise_gap",
            "collective_advantage",
        ),
        first_tasks=(
            "visual_motif_extraction",
            "matched_null_comparison",
            "recurrent_vs_feedforward_ablation",
        ),
        upstream_links=(
            "https://github.com/FlyBrainLab/datasets/blob/main/README.md#optic-lobe-dataset",
            "https://opticlobe.neuronlp.fruitflybrain.org",
        ),
    ),
    MotifCandidate(
        slug="hemibrain_1_2",
        name="Hemibrain 1.2",
        surface_kind="dataset",
        readiness="near_term",
        upstream_surface="FlyBrainLab Datasets",
        summary=(
            "Broad central-brain dataset for motif extraction once the harness and first "
            "intervention contract are stable on smaller tutorial surfaces."
        ),
        first_claims=(
            "lesion_rerouting_collective",
            "collective_controller",
            "competency_atlas",
        ),
        first_metrics=(
            "lesion_tolerance",
            "reroute_capacity",
            "basin_preservation",
            "efficiency_over_blind",
        ),
        first_tasks=(
            "motif_panel_selection",
            "degree_matched_nulls",
            "lesion_recovery_panel",
        ),
        upstream_links=(
            "https://github.com/FlyBrainLab/datasets/blob/main/README.md#hemibrain-dataset",
            "https://hemibrain12.neuronlp.fruitflybrain.org",
        ),
    ),
    MotifCandidate(
        slug="flywire_783",
        name="FlyWire Snapshot 783",
        surface_kind="dataset",
        readiness="later",
        upstream_surface="FlyBrainLab Datasets",
        summary=(
            "Large-scale atlas surface for expanding the competency catalog after the dossier has a"
            " stable motif registry, intervention suite, and null model discipline."
        ),
        first_claims=(
            "competency_atlas",
            "collective_controller",
        ),
        first_metrics=(
            "competency_catalog_breadth",
            "lesion_tolerance",
            "basin_preservation",
        ),
        first_tasks=(
            "motif_library_growth",
            "release_to_release_comparison",
            "cross_substrate_fingerprint_expansion",
        ),
        upstream_links=(
            "https://github.com/FlyBrainLab/datasets/blob/main/README.md#flywire-dataset",
            "https://flywire.neuronlp.fruitflybrain.org",
        ),
    ),
)


def catalog() -> tuple[MotifCandidate, ...]:
    return CATALOG
