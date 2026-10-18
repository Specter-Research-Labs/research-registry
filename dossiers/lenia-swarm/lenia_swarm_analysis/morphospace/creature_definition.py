"""Operational definition of a Flow Lenia creature as a body with an adult phase.

A frame is reduced to a body and its capture zone. The core is the superlevel set at
`CORE_LEVEL` of the frame peak. Core components closer than the kernel reach act on each other
through the potential, so they are grouped into one body, and the body B is the most massive
group. The capture zone C is B dilated by the kernel reach, the distance over which the body's
own potential can still act on matter. Matter outside C sees a flat potential and is moved only by reintegration diffusion, so
the captured fraction measures how much of the matter the body still holds.

A trajectory has an adult phase when every descriptor, as a rolling median over
`smoothing_steps` so that breathing and chaotic bodies are judged by their running level, settles
into a band around its terminal value and stays there to the horizon. The intrinsic verdict asks for an adult phase that starts
early enough, holds nearly all matter, never brings the capture zone to a wall, and is long-lived:
at its adult-phase rate of change, no descriptor would move by half its adult value within
`min_lifetime_runs` horizons. Flow Lenia conserves mass and has no intake, so a body that sheds
matter or spreads only ever loses it, and its lifetime is the persistence measure.

A single trajectory can sit near a transition (budding, a ring metamorphosis) that the arena
boundary tips either way, so the ensemble verdict asks for the intrinsic verdict on the torus at
more than one arena size: a creature passes in every run, an unstable body in some, and a
non-creature in none. Walled arenas let bodies lean on or park against a wall and are excluded.
"""

from __future__ import annotations

import base64
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from scipy import ndimage

Border = Literal["wall", "torus"]

CORE_LEVEL = 0.1
RING_REACH_WIDTHS = 3.0
FREE_VARIANCE_RATE = 0.2308
SUBSTANTIAL_BODY_SHARE = 0.05
DESCRIPTORS = ("captured", "body_share", "body_radius", "captured_radius95")


@dataclass(frozen=True)
class Thresholds:
    """Provisional values; the adult thresholds are a value choice still under review."""

    band_abs: dict[str, float]
    band_rel: dict[str, float]
    terminal_window: float
    smoothing_steps: int
    max_onset_fraction: float
    min_captured: float
    min_lifetime_runs: float


PROVISIONAL = Thresholds(
    band_abs={"captured": 0.02, "body_share": 0.05, "body_radius": 1.0, "captured_radius95": 1.0},
    band_rel={"captured": 0.0, "body_share": 0.0, "body_radius": 0.1, "captured_radius95": 0.1},
    terminal_window=0.25,
    smoothing_steps=2000,
    max_onset_fraction=0.5,
    min_captured=0.95,
    min_lifetime_runs=5.0,
)


def kernel_reach(params: dict[str, Any]) -> float:
    """Reach in arena cells: R r (a + 3 w) of the outermost ring with nonzero weight.

    Paper-mode kernels are b exp(-(D - a)^2 / (2 w^2)) with D = |x| / (r R) and no cutoff, so
    three ring widths past the ring centre the kernel has fallen to exp(-4.5) of that ring's peak.
    """
    reach = 0.0
    for r, rings_a, rings_b, rings_w in zip(
        params["r"], params["a"], params["b"], params["w"], strict=True
    ):
        for a, b, w in zip(rings_a, rings_b, rings_w, strict=True):
            if b > 0:
                reach = max(reach, params["R"] * r * (a + RING_REACH_WIDTHS * w))
    if reach <= 0:
        raise ValueError("kernel has no ring with positive weight")
    return reach


def trace_field(row: dict[str, Any]) -> np.ndarray:
    n = row["fieldResolution"]
    return (
        np.frombuffer(base64.b64decode(row["fieldF16Base64"]), dtype=np.float16)
        .astype(np.float64)
        .reshape(n, n)
    )


def trace_arena_mask(row: dict[str, Any]) -> np.ndarray:
    """Cells of a recentred wall-arena trace field that lie inside the arena.

    The trace shifts the native field by round(size / 2 - centre) without wrapping and box-resamples
    it, so the arena occupies a shifted square whose edges are the walls.
    """
    if row["width"] != row["height"]:
        raise ValueError("non-square arena")
    size, n = row["width"], row["fieldResolution"]
    scale = n / size
    inside = np.zeros((n, n), dtype=bool)
    sy = int(round(size * 0.5 - row["centerY"]))
    sx = int(round(size * 0.5 - row["centerX"]))
    y0, y1 = max(0, sy), min(size, sy + size)
    x0, x1 = max(0, sx), min(size, sx + size)
    inside[
        int(np.floor(y0 * scale)) : int(np.ceil(y1 * scale)),
        int(np.floor(x0 * scale)) : int(np.ceil(x1 * scale)),
    ] = True
    return inside


def _labels(mask: np.ndarray, border: Border) -> np.ndarray:
    labels, _ = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    if border == "torus":
        parent = {i: i for i in range(labels.max() + 1)}

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for a, b in ((labels[0], labels[-1]), (labels[:, 0], labels[:, -1])):
            for shift in (-1, 0, 1):
                bb = np.roll(b, shift)
                for i, j in zip(a, bb, strict=True):
                    if i and j:
                        parent[find(int(i))] = find(int(j))
        labels = np.vectorize(find)(labels)
    return labels


def _dilate(mask: np.ndarray, radius: float, border: Border) -> np.ndarray:
    k = int(np.ceil(radius))
    padded = np.pad(mask, k, mode="wrap" if border == "torus" else "constant")
    return (ndimage.distance_transform_edt(~padded) <= radius)[k:-k, k:-k]


def _offsets(
    mask_weights: np.ndarray, border: Border
) -> tuple[np.ndarray, np.ndarray, tuple[float, float]]:
    """Per-cell displacement from the weighted centroid, using the minimum image on a torus."""
    n0, n1 = mask_weights.shape
    w = mask_weights / mask_weights.sum()
    if border == "torus":
        centre = []
        for axis, n in ((0, n0), (1, n1)):
            theta = 2 * np.pi * np.arange(n) / n
            marginal = w.sum(axis=1 - axis)
            centre.append(
                float(
                    np.angle((marginal * np.exp(1j * theta)).sum()) % (2 * np.pi) * n / (2 * np.pi)
                )
            )
    else:
        centre = [float((w.sum(1) * np.arange(n0)).sum()), float((w.sum(0) * np.arange(n1)).sum())]
    dy = np.arange(n0)[:, None] - centre[0]
    dx = np.arange(n1)[None, :] - centre[1]
    if border == "torus":
        dy = (dy + n0 / 2) % n0 - n0 / 2
        dx = (dx + n1 / 2) % n1 - n1 / 2
    return np.broadcast_to(dy, (n0, n1)), np.broadcast_to(dx, (n0, n1)), (centre[0], centre[1])


def frame_measures(
    field: np.ndarray, *, reach: float, border: Border, arena: np.ndarray | None
) -> dict[str, float]:
    """Measures of one frame. `reach` is in field cells; `arena` marks in-arena cells of a wall field."""
    if (border == "wall") != (arena is not None):
        raise ValueError("a wall field needs its arena mask and a torus field must not have one")
    total = field.sum()
    if not total > 0:
        raise ValueError("empty field")
    p = field / total
    core = field >= CORE_LEVEL * field.max()
    groups = np.where(core, _labels(_dilate(core, reach / 2, border), border), 0)
    ids = np.unique(groups[groups > 0])
    masses = np.asarray(ndimage.sum(p, groups, ids))
    body = groups == ids[int(np.argmax(masses))]
    capture = _dilate(body, reach, border)
    dy, dx, _ = _offsets(np.where(body, p, 0.0), border)
    d2 = dy * dy + dx * dx
    captured = float(p[capture].sum())
    inside = np.where(capture, p, 0.0)
    order = np.argsort(d2[capture])
    cumulative = np.cumsum(inside[capture][order]) / captured
    haze = 1.0 - captured
    out = {
        "captured": captured,
        "body_share": float(masses.max()),
        "body_radius": float(np.sqrt((np.where(body, p, 0.0) * d2).sum() / p[body].sum())),
        "captured_radius95": float(np.sqrt(d2[capture][order][np.searchsorted(cumulative, 0.95)])),
        "substantial_bodies": int((masses >= SUBSTANTIAL_BODY_SHARE).sum()),
        "body_core_components": int(ndimage.label(body, structure=np.ones((3, 3), dtype=bool))[1]),
        "second_moment": float((p * d2).sum()),
        "haze_second_moment": float((np.where(capture, 0.0, p) * d2).sum() / haze)
        if haze > 0
        else 0.0,
    }
    if arena is not None:
        outside = ~arena
        out["wall_clearance"] = (
            float(ndimage.distance_transform_edt(~outside)[capture].min())
            if outside.any()
            else float("inf")
        )
    return out


def _band(name: str, reference: float, thresholds: Thresholds) -> float:
    return max(thresholds.band_abs[name], thresholds.band_rel[name] * abs(reference))


def adult_phase(
    steps: np.ndarray, series: dict[str, np.ndarray], thresholds: Thresholds
) -> dict[str, Any]:
    """Settling onset: the first frame from which every smoothed descriptor stays within its band of the terminal median.

    Lifetime is the time, in horizons, that the fitted adult-window trend would take to move a
    descriptor by half its terminal value, so a body that creeps through its band without leaving it
    before the horizon is still caught.
    """
    n = len(steps)
    cadence = np.unique(np.diff(steps))
    if len(cadence) != 1:
        raise ValueError("adult phase needs a uniform sampling cadence")
    width = max(1, int(round(thresholds.smoothing_steps / cadence[0])))
    tail = max(2, int(np.ceil(thresholds.terminal_window * n)))
    onset = 0
    reference, lifetime = {}, {}
    for name in DESCRIPTORS:
        x = ndimage.median_filter(series[name], size=width, mode="nearest")
        reference[name] = float(np.median(x[-tail:]))
        outside = np.nonzero(
            np.abs(x - reference[name]) > _band(name, reference[name], thresholds)
        )[0]
        if len(outside):
            onset = max(onset, int(outside[-1]) + 1)
    if onset > n - tail:
        return {"onset_step": None, "reference": reference, "lifetime_runs": None}
    window = slice(onset, n)
    for name in DESCRIPTORS:
        slope = abs(np.polyfit(steps[window], series[name][window], 1)[0])
        lifetime[name] = (
            float(0.5 * abs(reference[name]) / slope / steps[-1]) if slope > 0 else float("inf")
        )
    return {"onset_step": int(steps[onset]), "reference": reference, "lifetime_runs": lifetime}


def assess(
    rows: list[dict[str, Any]],
    *,
    params: dict[str, Any],
    border: Border,
    thresholds: Thresholds,
) -> dict[str, Any]:
    """Assess a development trace (rows with recentred trace fields) against the intrinsic criteria."""
    size = rows[0]["width"]
    n = rows[0]["fieldResolution"]
    scale = n / size
    reach = kernel_reach(params) * scale
    frames = [
        frame_measures(
            trace_field(r),
            reach=reach,
            border=border,
            arena=trace_arena_mask(r) if border == "wall" else None,
        )
        for r in rows
    ]
    steps = np.array([r["step"] for r in rows], dtype=float)
    series = {k: np.array([f[k] for f in frames]) for k in frames[0]}
    adult = adult_phase(steps, series, thresholds)
    criteria: dict[str, bool] = {"adult_phase": adult["onset_step"] is not None}
    if criteria["adult_phase"]:
        onset = adult["onset_step"]
        window = steps >= onset
        criteria["early_onset"] = bool(onset <= thresholds.max_onset_fraction * steps[-1])
        criteria["holds_matter"] = bool(adult["reference"]["captured"] >= thresholds.min_captured)
        criteria["single_body"] = bool((series["substantial_bodies"][window] == 1).all())
        criteria["long_lived"] = bool(
            min(adult["lifetime_runs"].values()) >= thresholds.min_lifetime_runs
        )
        if border == "wall":
            criteria["clear_of_walls"] = bool((series["wall_clearance"][window] > 0).all())
        late = steps >= steps[-1] * (1 - thresholds.terminal_window)
        haze_rate = np.polyfit(steps[late], series["second_moment"][late], 1)[0] / scale**2
        adult["second_moment_rate_over_free"] = float(haze_rate / (2 * FREE_VARIANCE_RATE))
    return {
        "reach_cells": reach / scale,
        "field_scale": scale,
        "steps": steps.astype(int).tolist(),
        "series": {k: v.tolist() for k, v in series.items()},
        "adult": adult,
        "criteria": criteria,
        "intrinsic_creature": all(criteria.values()),
    }


def assess_campaign(campaign: Path) -> dict[str, Any]:
    """Assess one replay campaign directory (config.json, replay-manifest.json, development-trace.jsonl)."""
    config = json.loads((campaign / "config.json").read_text())
    rows = [
        json.loads(line) for line in (campaign / "development-trace.jsonl").read_text().splitlines()
    ]
    result = assess(
        rows,
        params=config["params"],
        border=config["reintegration"]["border"],
        thresholds=PROVISIONAL,
    )
    result["body"] = json.loads((campaign / "replay-manifest.json").read_text())["sourceCreatureId"]
    result["campaign"] = campaign.name
    result["border"] = config["reintegration"]["border"]
    result["arena"] = rows[0]["width"]
    return result


def assess_replay(
    *, replay_root: Path, output_path: Path, horizon: int, workers: int
) -> dict[str, Any]:
    """Assess every campaign of a replay run whose trace reaches `horizon`; refuse partial runs."""
    campaigns = sorted((replay_root / "campaigns").iterdir())
    last = {
        c: json.loads((c / "development-trace.jsonl").read_text().splitlines()[-1])["step"]
        for c in campaigns
    }
    short = [c.name for c, step in last.items() if step != horizon]
    if short:
        raise ValueError(f"campaigns not at horizon {horizon}: {short}")
    with ProcessPoolExecutor(workers) as pool:
        results = list(pool.map(assess_campaign, campaigns))
    output_path.write_text(
        json.dumps(
            {"thresholds": PROVISIONAL.__dict__, "core_level": CORE_LEVEL, "bodies": results}
        )
    )
    return {
        "output": str(output_path),
        "bodies": len(results),
        "creatures": sorted(r["body"] for r in results if r["intrinsic_creature"]),
        "failures": {
            r["body"]: [k for k, v in r["criteria"].items() if not v]
            for r in results
            if not r["intrinsic_creature"]
        },
    }


def classify_ensemble(*, assessments: list[Path], output_path: Path) -> dict[str, Any]:
    """Combine assess-creatures outputs for the same bodies on the torus at different arena sizes."""
    runs: dict[int, dict[str, bool]] = {}
    for path in assessments:
        bodies = json.loads(path.read_text())["bodies"]
        borders = {b["border"] for b in bodies}
        arenas = {b["arena"] for b in bodies}
        if borders != {"torus"} or len(arenas) != 1:
            raise ValueError(
                f"{path}: need one torus arena size, got borders {borders} and arenas {arenas}"
            )
        arena = arenas.pop()
        if arena in runs:
            raise ValueError(f"{path}: arena {arena} given twice")
        runs[arena] = {b["body"]: b["intrinsic_creature"] for b in bodies}
    if len(runs) < 2:
        raise ValueError("need torus assessments at two or more arena sizes")
    names = {frozenset(r) for r in runs.values()}
    if len(names) != 1:
        raise ValueError("assessments cover different bodies")
    verdicts = {}
    for body in sorted(names.pop()):
        passes = [runs[a][body] for a in sorted(runs)]
        verdicts[body] = {
            "verdict": "creature" if all(passes) else "unstable" if any(passes) else "not_creature",
            "passes_by_arena": {a: runs[a][body] for a in sorted(runs)},
        }
    output_path.write_text(json.dumps({"arenas": sorted(runs), "bodies": verdicts}, indent=1))
    counts = {
        v: sum(b["verdict"] == v for b in verdicts.values())
        for v in ("creature", "unstable", "not_creature")
    }
    return {"output": str(output_path), "arenas": sorted(runs), **counts}
