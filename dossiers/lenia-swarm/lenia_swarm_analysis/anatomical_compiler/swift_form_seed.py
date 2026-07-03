"""Swift oracle seeding for form targets: re-seed an explicit density field into the Metal
engine via init.state_patch and roll it forward.

The descriptor compiler verifies on the Swift oracle by re-simulating a genotype from the
canonical make_init patch. A form compiler's answer is a rule that holds a specific body, so
its oracle check has to start from that body, not from noise: this writes the body into
init.state_patch (f32le, base64) with init.a_uniform forced to [0, 0], runs the same
LeniaCLI frame path, and reports the settled phenotype plus how far the body drifted while
settling.

The round-trip verifier (main) grows a genuine self-maintaining creature on the MLX map,
re-seeds that body on Swift under its own rule, and reports the drift, so the seeding path
(byte layout, orientation, centering) is checked against a real fixed point rather than the
metastable ring a hand-drawn mask can settle into.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis.anatomical_compiler._codec import clamp_params, load_dataset
from lenia_swarm_analysis.anatomical_compiler.form_topology import (
    feature_counts,
    persistence_image,
    topo_distance,
)
from lenia_swarm_analysis.anatomical_compiler.forward_sim import (
    DEFAULT_BINARY,
    METRIC_KEYS,
    state_patch_config,
)


@dataclass
class SeedRoundtrip:
    terminalField: np.ndarray            # [sx, sy] summed-mass terminal frame, for rendering
    phenotype: dict[str, Any]
    seededMass: float                    # total mass of the seeded field
    swiftMassMean: float                 # Swift's mass over the run (unclipped, from metrics)
    massConservation: float              # swiftMassMean / seededMass
    swiftOccupancy: float
    swiftGyration: float
    terminalLcf: float                   # largest connected component fraction of the settled body
    terminalComponents: int
    formDrift: float
    topoDistance: float
    targetFeatures: tuple[int, int]
    terminalFeatures: tuple[int, int]
    isStable: bool
    held: bool


def form_is_held(
    *, stable: bool, mass_conservation: float, form_drift: float,
    topology_distance: float, target_features: tuple[int, int],
    terminal_features: tuple[int, int],
) -> bool:
    """Core Swift-oracle invariant for accepting a re-seeded form."""
    return (
        stable
        and 0.95 < mass_conservation < 1.05
        and form_drift <= 0.25
        and topology_distance <= 0.5
        and terminal_features == target_features
    )


def seed_and_run(
    binary: Path, base_config: dict[str, Any], search_config: dict[str, Any],
    genotype: dict[str, Any], field: np.ndarray, *, center: tuple[int, int],
    seed: int, steps: int, stride: int, dossier_root: Path, timeout: float,
    occupancy_threshold: float,
) -> SeedRoundtrip:
    """Seed `field` as a state_patch, run the rule forward on Swift with frame capture, and
    report whether the body held.

    The byte-level correctness of the seed is read off mass conservation: Flow-Lenia conserves
    mass exactly, so Swift's own (unclipped) mass over the run must equal the seeded field's
    total mass to high precision; a misaligned or truncated state_patch read would change the
    total. Coherence and stability then say the loaded body is a valid creature, not scrambled
    noise. The 8-bit PNG frames are used only for the terminal component structure and the
    render, not for mass, because the seeded body's high-density cells saturate the frame."""
    from lenia_swarm_analysis.anatomical_compiler.mlx_coherence import _component_metrics
    from lenia_swarm_analysis.anatomical_compiler.mlx_validate import (
        _load_frames,
        _run_with_frames,
    )

    seeded_mass = float(np.asarray(field).sum())
    seeded_base = state_patch_config(base_config, field, center=center, seed=seed)
    with tempfile.TemporaryDirectory() as raw:
        output_dir = Path(raw) / "out"
        _run_with_frames(
            binary, seeded_base, search_config, genotype, output_dir,
            init_seed=seed, steps=steps, stride=stride,
            dossier_root=dossier_root, timeout=timeout,
        )
        frames = _load_frames(output_dir)
        results = list(output_dir.rglob("results.jsonl"))
        if not results:
            raise RuntimeError("No results.jsonl produced for state_patch seeding")
        record = json.loads(results[0].read_text(encoding="utf-8").splitlines()[0])

    metrics = record["metrics"]
    phenotype = {key: metrics.get(key) for key in METRIC_KEYS}
    swift_mass = float(metrics["mass_mean"])
    conservation = swift_mass / (seeded_mass + 1e-9)

    last = frames[max(frames)]
    if last.ndim == 3:
        last = last[:, :, 0]
    target = np.asarray(field).sum(axis=-1) if field.ndim == 3 else np.asarray(field)
    lcf, components = _component_metrics(last, occupancy_threshold)
    target_lcf, _ = _component_metrics(target, occupancy_threshold)
    target_occupancy = float((target > occupancy_threshold).mean())
    terminal_occupancy = float((last > occupancy_threshold).mean())
    form_drift = abs(terminal_occupancy - target_occupancy) / (
        target_occupancy + 1e-9
    ) + max(0.0, target_lcf - lcf)
    topology = topo_distance(persistence_image(last), persistence_image(target))
    target_features = feature_counts(target)
    terminal_features = feature_counts(last)

    is_stable = bool(metrics["is_stable"])
    held = form_is_held(
        stable=is_stable,
        mass_conservation=conservation,
        form_drift=form_drift,
        topology_distance=topology,
        target_features=target_features,
        terminal_features=terminal_features,
    )
    return SeedRoundtrip(
        terminalField=last, phenotype=phenotype, seededMass=seeded_mass,
        swiftMassMean=swift_mass, massConservation=conservation,
        swiftOccupancy=float(metrics["occupancy_mean"]),
        swiftGyration=float(metrics.get("gyration") or 0.0),
        terminalLcf=lcf, terminalComponents=components, formDrift=form_drift,
        topoDistance=topology, targetFeatures=target_features,
        terminalFeatures=terminal_features, isStable=is_stable, held=held,
    )


def main(argv: list[str] | None = None) -> int:
    from lenia_swarm_analysis.anatomical_compiler.form_compiler import grow_body
    from lenia_swarm_analysis.anatomical_compiler.mlx_lenia import LeniaConfig

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="configs/base/paper_base_3k_1c_128.json")
    parser.add_argument("--search", default="configs/search/search_crossmap_motion.json")
    parser.add_argument(
        "--dataset", default="outputs/anatomical-compiler/forward_dataset_3k_1c_128.jsonl"
    )
    parser.add_argument("--anchor-index", type=int, default=0,
                        help="dataset genotype to grow a genuine body from")
    parser.add_argument("--grow-steps", type=int, default=600)
    parser.add_argument("--steps", type=int, default=600,
                        help="Swift horizon for the re-seeded body")
    parser.add_argument("--stride", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--output", default="outputs/anatomical-compiler/swift_form_seed_roundtrip.json"
    )
    args = parser.parse_args(argv)

    root = Path.cwd()
    base_config = json.loads((root / args.base).read_text(encoding="utf-8"))
    search_config = json.loads((root / args.search).read_text(encoding="utf-8"))
    config = LeniaConfig.from_base_config(base_config)
    ranges = base_config["params"]["ranges"]
    occ = float(search_config["occupancy_threshold"])
    patch = base_config["init"]["patches"][0]
    center = (int(patch["center"][0]), int(patch["center"][1]))
    size = int(patch["size"])
    binary = root / DEFAULT_BINARY

    codec, genotype, _ = load_dataset((root / args.dataset).resolve())
    rule, _ = clamp_params(codec.unflatten(genotype[args.anchor_index]), ranges)

    print(f"growing a genuine body from dataset genotype {args.anchor_index} ...")
    body = grow_body(rule, config, center=center, size=size, occupancy_threshold=occ,
                     steps=args.grow_steps)
    field = np.asarray(body.field[0])
    g_h0, g_h1 = feature_counts(field.sum(axis=-1))
    print(f"grown body: lcf={body.lcf:.2f} occ={body.occupancy:.3f} "
          f"H0={g_h0} H1={g_h1} liveness={body.liveness:.4f}")

    result = seed_and_run(
        binary, base_config, search_config, rule, field, center=center, seed=args.seed,
        steps=args.steps, stride=args.stride, dossier_root=root, timeout=600.0,
        occupancy_threshold=occ,
    )

    report = {
        "anchorIndex": args.anchor_index,
        "grownFeatures": {"H0": g_h0, "H1": g_h1},
        "seededMass": result.seededMass,
        "swiftMassMean": result.swiftMassMean,
        "massConservation": result.massConservation,
        "swiftOccupancy": result.swiftOccupancy,
        "swiftGyration": result.swiftGyration,
        "terminalLcf": result.terminalLcf,
        "terminalComponents": result.terminalComponents,
        "formDrift": result.formDrift,
        "topoDistance": result.topoDistance,
        "terminalFeatures": {
            "H0": result.terminalFeatures[0], "H1": result.terminalFeatures[1]
        },
        "steps": args.steps,
        "isStable": result.isStable,
        "held": result.held,
    }
    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Swift re-seed of the grown body: seeded mass {result.seededMass:.2f} -> "
          f"Swift mass_mean {result.swiftMassMean:.2f} "
          f"(conservation {result.massConservation:.4f})")
    print(f"  terminal lcf {result.terminalLcf:.3f} ({result.terminalComponents} components)  "
          f"occ {result.swiftOccupancy:.3f}  gyration {result.swiftGyration:.1f}")
    print(f"  held={result.held}  is_stable={result.isStable}")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
