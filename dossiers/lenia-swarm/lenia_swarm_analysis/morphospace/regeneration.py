"""Cut a body's recorded state and restart it, to test whether its adult shape is a set point.

A replay run with `--development-state --development-raw-steps <S>` records each body's full
multi-channel state at step S. `regeneration-inputs` removes a mass fraction of that state behind a
straight cut through the body and writes one restart bundle per body and cut, with the cut state as
init.state_patch. `publish replay --batch-size N` runs all of them as one batch, from step 0 of the
restart, which is step S of the body. Flow Lenia conserves mass, so a cut body cannot regrow what was
removed; the question is whether the remaining mass reorganises into the same shape at a smaller size.

A reshape condition keeps the mass and redraws the body: `reshape_state` spreads each channel's
total over one smooth profile with the body's centre, size and major axis, so the restart asks
whether the rule rebuilds its adult from a body of the same matter in another shape.

The shape of a frame is the twelve common_morphology_v1 axes on the native positive-density cloud
(cells above 1/255 of the frame peak, weighted by density), after rolling the torus so the circular
centre of mass sits at the arena centre so that a body crossing the seam is measured whole.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import shutil
from pathlib import Path

import numpy as np

from lenia_swarm_analysis._io import sha256_bytes
from lenia_swarm_analysis.anatomical_compiler.forward_sim import state_patch_config
from lenia_swarm_analysis.observer.states import load_states

from .common_morphology import AXIS_IDS, point_cloud_shape_features
from .requalification import strip_trace_fields

CONTROL = "control"


def circular_centre(mass: np.ndarray) -> tuple[float, float]:
    """Centre of mass on the torus along array axes 0 and 1, in cell coordinates."""
    centre = []
    for axis in (0, 1):
        n = mass.shape[axis]
        profile = mass.sum(axis=1 - axis)
        angle = np.angle(np.sum(profile * np.exp(2j * np.pi * np.arange(n) / n)))
        centre.append(float((angle % (2 * np.pi)) * n / (2 * np.pi)))
    return centre[0], centre[1]


def circular_roll(mass: np.ndarray) -> np.ndarray:
    for axis, centre in enumerate(circular_centre(mass)):
        mass = np.roll(mass, int(np.floor(mass.shape[axis] / 2 - centre + 0.5)), axis=axis)
    return mass


def native_shape_vector(mass: np.ndarray) -> tuple[list[float], int]:
    """The twelve axes of one torus frame, and the number of cells in its cloud."""
    mass = circular_roll(mass)
    mask = mass >= mass.max() / 255
    y, x = np.nonzero(mask)
    features = point_cloud_shape_features(np.column_stack([x, y]), weights=mass[mask])
    return [features[k] for k in AXIS_IDS], len(x)


def trace_shapes(trace_path: Path) -> dict[str, list]:
    """Shape, cloud size, centre of mass (row, column) and state hash of every trace frame that carries a field.

    The trace field is the channel sum scaled to peak 1 and rolled so the body sits at the arena centre, so the
    centre comes from the frame's own centerY and centerX."""
    out: dict[str, list] = {"step": [], "vector": [], "cells": [], "centre": [], "state_sha256": []}
    with trace_path.open() as handle:
        for line in handle:
            frame = json.loads(line)
            if "fieldF16Base64" not in frame:
                continue
            res = frame["fieldResolution"]
            if not res == frame["width"] == frame["height"]:
                raise ValueError(f"{trace_path}: field at step {frame['step']} is not at the arena resolution")
            mass = np.frombuffer(base64.b64decode(frame["fieldF16Base64"]), dtype="<f2").reshape(res, res).astype(np.float64)
            vector, cells = native_shape_vector(mass)
            out["step"].append(frame["step"])
            out["vector"].append(vector)
            out["cells"].append(cells)
            out["centre"].append((frame["centerY"], frame["centerX"]))
            out["state_sha256"].append(frame["stateSha256"])
    return out


def cut_state(state: np.ndarray, angle: float, removed_fraction: float) -> tuple[np.ndarray, float]:
    """Zero every channel beyond a straight cut whose normal points at `angle` (radians, array axes
    0 and 1), placed so that the removed side holds `removed_fraction` of the mass. Distances are
    measured on the torus from the circular centre of mass. Returns the cut state and the removed
    fraction actually achieved, which differs from the target by at most one cell's share."""
    if not 0 < removed_fraction < 1:
        raise ValueError(f"removed fraction must lie in (0, 1), got {removed_fraction}")
    mass = state.sum(axis=-1, dtype=np.float64)
    offsets = [(np.arange(n) - c + n / 2) % n - n / 2 for n, c in zip(mass.shape, circular_centre(mass), strict=True)]
    projection = math.cos(angle) * offsets[0][:, None] + math.sin(angle) * offsets[1][None, :]
    order = np.argsort(-projection, axis=None, kind="stable")
    removed_mass = np.cumsum(mass.ravel()[order])
    count = int(np.searchsorted(removed_mass, removed_fraction * removed_mass[-1]))
    removed = np.zeros(mass.size, dtype=bool)
    removed[order[:count]] = True
    removed = removed.reshape(mass.shape)
    cut = state.copy()
    cut[removed] = 0
    return cut, float(mass[removed].sum() / mass.sum())


PROFILES = ("gauss", "ellipse")


def reshape_state(state: np.ndarray, profile: str, aspect: float) -> np.ndarray:
    """Spread each channel's total mass over one profile centred on the body's circular centre of
    mass, with the body's radius of gyration and its principal axis as the long axis, `aspect` times
    the short one. `gauss` falls off as a Gaussian, `ellipse` is uniform inside an ellipse; every cell
    carries the body's overall channel mix."""
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {PROFILES}, got {profile!r}")
    if aspect < 1:
        raise ValueError(f"aspect must be at least 1, got {aspect}")
    mass = state.sum(axis=-1, dtype=np.float64)
    offsets = [(np.arange(n) - c + n / 2) % n - n / 2 for n, c in zip(mass.shape, circular_centre(mass), strict=True)]
    d0, d1 = np.meshgrid(offsets[0], offsets[1], indexing="ij")
    weights = mass / mass.sum()
    covariance = np.array([[np.sum(weights * a * b) for b in (d0, d1)] for a in (d0, d1)])
    gyration = math.sqrt(np.trace(covariance))
    values, vectors = np.linalg.eigh(covariance)
    major = vectors[:, int(np.argmax(values))]
    along = major[0] * d0 + major[1] * d1
    across = -major[1] * d0 + major[0] * d1
    if profile == "gauss":
        short = gyration / math.sqrt(aspect**2 + 1)
        shape = np.exp(-0.5 * ((along / (aspect * short)) ** 2 + (across / short) ** 2))
    else:
        short = 2 * gyration / math.sqrt(aspect**2 + 1)
        shape = ((along / (aspect * short)) ** 2 + (across / short) ** 2 <= 1).astype(np.float64)
    totals = state.sum(axis=(0, 1), dtype=np.float64)
    return (shape[..., None] / shape.sum() * totals).astype(state.dtype)


def cut_conditions(angles_deg: list[float], fractions: list[float], reshapes: list[tuple[str, float]]) -> list[dict]:
    return (
        [{"name": CONTROL}]
        + [{"name": f"cut-a{a:g}-f{f:g}", "angle_deg": a, "removed_fraction": f} for f in fractions for a in angles_deg]
        + [{"name": f"reshape-{p}-a{a:g}", "profile": p, "aspect": a} for p, a in reshapes]
    )


def write_regeneration_inputs(
    *,
    replay_root: Path,
    source_index: Path,
    step: int,
    restart_steps: int,
    angles_deg: list[float],
    fractions: list[float],
    reshapes: list[tuple[str, float]],
    output_dir: Path,
) -> dict:
    """One restart bundle per (body of `replay_root`, condition) from the body's state at `step`. The
    control restarts the uncut state, so comparing it with the uninterrupted replay checks the
    restart itself."""
    rows = {}
    for line in source_index.read_text().splitlines():
        row = json.loads(line)
        rows[row["specimenManifest"]["creatureID"]] = row
    campaigns = {}
    for campaign in sorted((replay_root / "campaigns").iterdir()):
        campaigns[json.loads((campaign / "replay-manifest.json").read_text())["sourceCreatureId"]] = campaign
    bodies = list(campaigns)
    missing = [b for b in bodies if b not in rows]
    if missing:
        raise ValueError(f"replayed bodies without a row in {source_index}: {missing}")

    conditions = cut_conditions(angles_deg, fractions, reshapes)
    output_dir.mkdir(parents=True, exist_ok=False)
    index_lines, manifest = [], []
    for body in bodies:
        states = load_states(campaigns[body])
        frames = {int(s): i for i, s in enumerate(states.steps)}
        if step not in frames:
            raise ValueError(f"{campaigns[body]}: no recorded state at step {step}; recorded {sorted(frames)}")
        state = states.values[frames[step]]
        source_row = rows[body]
        source_dir = Path(source_row["exportDir"])
        base = json.loads((source_dir / "base.json").read_text())
        search = json.loads((source_dir / "search.json").read_text())
        search["steps"] = restart_steps
        sx, sy = base["grid"]["sx"], base["grid"]["sy"]
        if state.shape[:2] != (sx, sy):
            raise ValueError(f"{campaigns[body]}: state shape {state.shape} does not match the {sx} x {sy} grid")
        for condition in conditions:
            if condition["name"] == CONTROL:
                field, achieved = state, 0.0
            elif "profile" in condition:
                field, achieved = reshape_state(state, condition["profile"], condition["aspect"]), 0.0
            else:
                field, achieved = cut_state(state, math.radians(condition["angle_deg"]), condition["removed_fraction"])
            bundle = output_dir / f"{source_dir.name}-{condition['name']}"
            bundle.mkdir()
            shutil.copy(source_dir / "meta.json", bundle / "meta.json")
            config = state_patch_config(base, field, center=(sx // 2, sy // 2), seed=base["init"]["seed"])
            (bundle / "base.json").write_text(json.dumps(config))
            (bundle / "search.json").write_text(json.dumps(search))
            row = dict(source_row, exportDir=str(bundle), baseConfigPath=str(bundle / "base.json"), searchConfigPath=str(bundle / "search.json"))
            index_lines.append(json.dumps(row))
            manifest.append({
                "position": len(manifest),
                "body": body,
                "condition": condition["name"],
                "angle_deg": condition.get("angle_deg"),
                "target_removed_fraction": condition.get("removed_fraction"),
                "removed_fraction": achieved,
                "profile": condition.get("profile"),
                "aspect": condition.get("aspect"),
                "cut_step": step,
                "source_state_sha256": hashlib.sha256(state.tobytes()).hexdigest(),
                "restart_state_sha256": hashlib.sha256(np.ascontiguousarray(field, dtype="<f4").tobytes()).hexdigest(),
            })
    (output_dir / "index.jsonl").write_text("\n".join(index_lines) + "\n")
    receipt = {"replay_root": str(replay_root), "source_index": str(source_index), "cut_step": step,
               "restart_steps": restart_steps, "conditions": conditions, "restarts": manifest}
    (output_dir / "regeneration-inputs.json").write_text(json.dumps(receipt, indent=1) + "\n")
    return {"restarts": len(manifest), "bodies": len(bodies), "conditions": len(conditions), "output": str(output_dir)}


def retire_restart_fields(
    *, replay_root: Path, shapes: Path, keep: list[str], manifest_path: Path, apply: bool
) -> dict:
    """Strip raw fields from the restart traces of one replay cell once their shapes are measured.

    `shapes` is the cell's shape record, an npz whose rows follow the campaign order with arrays body,
    condition and state_sha256. A trace is stripped only if its body and the state hashes of its field
    frames match its row, so that no trace loses its fields before it was measured. Restarts named in
    `keep` as body:condition stay whole. Every trace and keep name is checked before any trace is stripped.
    Without `apply` only the manifest is written."""
    record = np.load(shapes)
    campaigns = sorted((replay_root / "campaigns").iterdir())
    if len(campaigns) != len(record["body"]):
        raise ValueError(f"{replay_root}: {len(campaigns)} campaigns against {len(record['body'])} rows in {shapes}")
    checked = []
    for campaign, body, condition, hashes in zip(
        campaigns, record["body"], record["condition"], record["state_sha256"], strict=True
    ):
        trace = campaign / "development-trace.jsonl"
        if json.loads((campaign / "replay-manifest.json").read_text())["sourceCreatureId"] != body:
            raise ValueError(f"{campaign}: body differs from row {body} of {shapes}")
        raw = trace.read_bytes()
        frames = [json.loads(line) for line in raw.decode().splitlines()]
        measured = [f["stateSha256"] for f in frames if "fieldF16Base64" in f]
        if measured != list(hashes):
            raise ValueError(f"{trace}: field frames do not match the measured row of {shapes}")
        checked.append((f"{body}:{condition}", trace, raw, frames))
    missing = set(keep) - {name for name, *_ in checked}
    if missing:
        raise ValueError(f"restarts to keep not in {replay_root}: {sorted(missing)}")
    rows, kept = [], []
    for name, trace, raw, frames in checked:
        if name in keep:
            kept.append({"restart": name, "path": str(trace), "sha256": sha256_bytes(raw), "bytes": len(raw)})
        else:
            rows.append({"restart": name, **strip_trace_fields(trace, raw, frames, apply=apply)})
    manifest_path.write_text(json.dumps({"applied": apply, "shapes_sha256": sha256_bytes(shapes.read_bytes()),
                                         "stripped": rows, "kept": kept}, indent=1))
    return {
        "manifest": str(manifest_path),
        "applied": apply,
        "stripped": len(rows),
        "kept": len(kept),
        "freed_bytes": sum(r["bytes"] - r["stripped_bytes"] for r in rows),
    }
