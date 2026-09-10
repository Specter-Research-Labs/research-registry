#!/usr/bin/env python3
"""Run a fixed cell-swap pilot on visually selected, long-lived Flow Lenia bodies.

See docs/coherent-body-pilot.md for selection, interpretation, and invocation.
The original causal-emergence cohorts are never modified.
"""

import argparse
import base64
import gzip
import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import numpy as np
from scipy import ndimage

AGES = (900, 2700)
SWAP_SEEDS = (17, 31, 47)
STEPS = 240
DOSE = 0.12


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n")


def call(argv, log):
    with log.open("w") as f:
        subprocess.run([str(x) for x in argv], stdout=f, stderr=subprocess.STDOUT, check=True)


def analyze(root):
    plan = json.loads((root / "plan.json").read_text())
    expected = {f"{r['candidate']}-a{age}" for r in plan["specimens"] for age in plan["ages"]}
    assert {p.name for p in (root / "trials").iterdir()} == expected
    arms = {"control", *(f"swap-{seed}" for seed in plan["swap_seeds"])}
    for checkpoint in (root / "trials").iterdir():
        assert {p.name for p in checkpoint.iterdir()} == arms

    def load(p):
        return [json.loads(x) for x in gzip.open(p, "rt")]

    def field(t):
        return (
            np.frombuffer(base64.b64decode(t["fieldF16Base64"]), dtype="<f2")
            .astype(float)
            .reshape(t["fieldResolution"], t["fieldResolution"])
        )

    def component(t):
        v = field(t)
        labels, n = ndimage.label(v > 0.001, np.ones((3, 3)))
        m = ndimage.sum(v, labels, np.arange(1, n + 1))
        return float(max(m, default=0) / v.sum())

    rows = []
    for checkpoint in sorted((root / "trials").iterdir()):
        control = next((checkpoint / "control").rglob("shooting-perturbation-events.jsonl.gz"))
        ce = load(control)[0]
        cf = load(next((checkpoint / "control").rglob("field-observations.jsonl.gz")))
        assert ce["pre_state_sha256"] == ce["post_state_sha256"]
        for arm in sorted(checkpoint.iterdir()):
            event_path = next(arm.rglob("shooting-perturbation-events.jsonl.gz"))
            e = load(event_path)[0]
            p = next(arm.rglob("field-observations.jsonl.gz"))
            fs = load(p)
            assert e["pre_state_sha256"] == ce["pre_state_sha256"]
            assert all(
                e[k]
                for k in [
                    "matter_cell_inventory_preserved",
                    "parameter_cell_inventory_preserved",
                    "occupancy_support_preserved",
                ]
            )
            assert e["total_mass_absolute_delta"] / e["pre_total_mass"] < 1e-6
            assert (
                [x["step"] for x in cf]
                == [x["step"] for x in fs]
                == list(range(4, plan["future_steps"] + 1, 4))
            )
            delta = np.abs(field(fs[-1]) - field(cf[-1])).sum() / field(cf[-1]).sum()
            rows.append(
                {
                    "checkpoint": checkpoint.name,
                    "arm": arm.name,
                    "intervention_relative_mass_delta": e["total_mass_absolute_delta"]
                    / e["pre_total_mass"],
                    "event_sha256": hashlib.sha256(event_path.read_bytes()).hexdigest(),
                    "field_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    "realized_affected_matter_fraction": e["realized_affected_matter_fraction"],
                    "mass_relative_drift": (fs[-1]["totalMass"] - e["pre_total_mass"])
                    / e["pre_total_mass"],
                    "final_centered_field_l1_over_control_mass": float(delta),
                    "thresholded_component_mass_min": min(component(t) for t in fs),
                    "thresholded_component_mass_final": component(fs[-1]),
                }
            )
    summary = {
        "schema": "coherent_body_pilot_summary_v1",
        "trials": len(rows),
        "paired_pre_states_verified": True,
        "all_cell_inventories_preserved": True,
        "intervention_relative_mass_delta_max": max(
            r["intervention_relative_mass_delta"] for r in rows
        ),
        "coherence_threshold": 0.001,
        "field_comparison": "Independently centered native-grid Float16 total-matter fields, L1 difference divided by control mass; not the original report estimator",
        "rows": rows,
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--replay-root", type=Path, required=True)
    parser.add_argument("--candidate", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    runner = args.runner.resolve()
    roster = []
    for candidate in args.candidate:
        source = args.replay_root / candidate
        entry = json.loads((source / "library/index.jsonl").read_text())
        creature = entry["creature"]
        base = json.loads((source / "config.json").read_text())
        base["params"] = {"mode": "explicit", **creature["genotype"]}
        base["init"] = creature["initialCondition"]
        if base["channels"] != 2 or base["connectivity"] != [[5, 5], [5, 5]]:
            raise ValueError("Pilot requires the existing two-channel, twenty-kernel regime")
        if base["parameter_embedding"]["enabled"] or base["interventions"]:
            raise ValueError("Pilot requires a static genotype with no scheduled interventions")
        src = out / "sources" / candidate
        write(src / "base.json", base)
        search = json.loads((source / "search.json").read_text())
        write(src / "search.json", search)
        write(src / "library-entry.json", entry)
        roster.append(
            {
                "candidate": candidate,
                "creature_id": creature["id"],
                "source_config_sha256": digest(source / "config.json"),
                "source_library_sha256": digest(source / "library/index.jsonl"),
            }
        )
    # This plan is written before any perturbed outcomes exist.
    write(
        out / "plan.json",
        {
            "schema": "coherent_body_cell_swap_pilot_v1",
            "selection": "Visual body persistence in an independent 3600-step replay; not intervention response",
            "runner_sha256": digest(runner),
            "ages": AGES,
            "future_steps": STEPS,
            "swap_fraction": DOSE,
            "swap_seeds": SWAP_SEEDS,
            "specimens": roster,
        },
    )
    for row in roster:
        ident = row["candidate"]
        source = out / "sources" / ident
        original = json.loads((source / "base.json").read_text())
        for age in AGES:
            key = f"{ident}-a{age}"
            root = out / "inputs" / key
            root.mkdir(parents=True)
            base = deepcopy(original)
            base["run"]["steps"] = age
            search = json.loads((source / "search.json").read_text())
            search.update(
                steps=age,
                warmup_steps=0,
                record_interval=30,
                count=1,
                seed_start=base["init"]["seed"],
            )
            write(root / "capture-base.json", base)
            write(root / "capture-search.json", search)
            print("capture", key, flush=True)
            call(
                [
                    runner,
                    "discover",
                    "local",
                    "--config",
                    root / "capture-base.json",
                    "--search",
                    root / "capture-search.json",
                    "--backend",
                    "metal-full",
                    "--output",
                    out / "capture",
                    "--no-promotion",
                    "--terminal-state-patch",
                    "--run-id",
                    key,
                    "--no-log-console",
                ],
                root / "capture.log",
            )
            patch = json.loads((out / "capture" / key / "terminal_state_patch.json").read_text())
            n = base["grid"]["sx"]
            if (patch["width"], patch["height"], patch["channels"]) != (n, n, 2):
                raise ValueError("Expected a full native-grid checkpoint")
            values = np.frombuffer(base64.b64decode(patch["data"]), dtype="<f4")
            sources, targets = [], []
            for s, counts in enumerate(base["connectivity"]):
                for t, count in enumerate(counts):
                    sources.extend([s] * count)
                    targets.extend([t] * count)
            seed = {
                "sourceID": key,
                "name": key,
                "width": n,
                "height": n,
                "channels": 2,
                "data": values.tolist(),
                "runID": key,
                "campaignID": "coherent-body-pilot-v1",
                "kernelParams": {k: v for k, v in base["params"].items() if k != "mode"},
                "kernelSources": sources,
                "kernelTargets": targets,
            }
            (root / "patches.jsonl").write_text(json.dumps(seed) + "\n")
            base["init"] = {"seed": 0, "a_uniform": {"low": 0.0, "high": 0.0}, "patches": []}
            base["run"]["steps"] = STEPS
            # The ecology validator requires this profile for an explicitly disabled beam.
            base["profile"] = "experimental"
            base["beam_mutation"] = {
                "enabled": False,
                "probability": 0.0,
                "patch_size": 1,
                "std": 1.0,
                "seed": 0,
            }
            write(root / "base.json", base)
            for swap_seed in (None, *SWAP_SEEDS):
                arm = "control" if swap_seed is None else f"swap-{swap_seed}"
                cfg = root / arm
                shooting = {
                    "operator": "untouched_v1"
                    if swap_seed is None
                    else "local_coupled_cell_swap_v1",
                    "after_step": 1,
                    "swap_fraction": 0.0 if swap_seed is None else DOSE,
                    "occupancy_threshold": 0.001,
                }
                if swap_seed is not None:
                    shooting["seed"] = swap_seed
                write(
                    cfg / "simulation.json",
                    {
                        "paper": "flow-lenia-emergent-evolutionary-dynamics-2025",
                        "grid_size": n,
                        "total_steps": STEPS,
                        "record_every_steps": 4,
                        "observation_field_resolution": n,
                        "observation_window_size": n,
                        "artifact_encoding": "gzip_json_v1",
                        "channels": 2,
                        "kernels_per_channel_pair": 5,
                        "repeats": 1,
                        "mutation_probabilities": [0.0],
                        "variants": ["vanilla"],
                        "activity": {
                            "enabled": True,
                            "interval": 4,
                            "threshold": 0.01,
                            "maxComponents": 256,
                            "matchThreshold": 1.5,
                            "positionWeight": 0.05,
                            "paramWeight": 1.0,
                        },
                    },
                )
                write(
                    cfg / "vanilla.json",
                    {
                        "name": "vanilla",
                        "base_config": "../base.json",
                        "init_patch_count": 1,
                        "init_patch_size": 1,
                        "init_param_mean": 0.0,
                        "init_param_std": 0.1,
                        "shooting_perturbation": shooting,
                    },
                )
                print("trial", key, arm, flush=True)
                call(
                    [
                        runner,
                        "discover",
                        "ecology-2025",
                        "--config-dir",
                        cfg,
                        "--seed-library",
                        root / "patches.jsonl",
                        "--seed-id",
                        key,
                        "--backend",
                        "metal-full",
                        "--border",
                        base["reintegration"]["border"],
                        "--diagnostic-config",
                        "--run-id",
                        f"{key}-{arm}",
                        "--no-log-console",
                        "--output",
                        out / "trials" / key / arm,
                    ],
                    cfg / "trial.log",
                )
    analyze(out)
    write(
        out / "completion.json",
        {
            "plan_sha256": digest(out / "plan.json"),
            "trials": len(roster) * len(AGES) * (len(SWAP_SEEDS) + 1),
        },
    )


if __name__ == "__main__":
    main()
