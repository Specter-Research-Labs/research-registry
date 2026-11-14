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

import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

import numpy as np
from scipy import ndimage

from lenia_swarm_analysis.trace_codec import trace_field

from .provenance import RECEIPT_FILE, read_run_provenance

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

# One knob moves at a time while the others stay at PROVISIONAL; "band_scale" multiplies every
# band_abs and band_rel entry. The grid is part of the sweep's output, so a changed grid is visible.
SWEEP_GRID: dict[str, tuple[float, ...]] = {
    "band_scale": (0.5, 0.75, 1.5, 2.0),
    "terminal_window": (0.15, 0.2, 0.3, 0.35),
    "smoothing_steps": (1000, 1500, 3000, 4000),
    "max_onset_fraction": (0.3, 0.4, 0.6, 0.7),
    "min_captured": (0.9, 0.925, 0.975, 0.99),
    "min_lifetime_runs": (2.5, 4.0, 7.5, 10.0),
}
VERDICTS = ("creature", "unstable", "not_creature")


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


def intrinsic_criteria(
    steps: np.ndarray,
    series: dict[str, np.ndarray],
    *,
    border: Border,
    scale: float,
    thresholds: Thresholds,
) -> tuple[dict[str, Any], dict[str, bool]]:
    """Adult phase and intrinsic criteria of measured frames; the frames do not depend on thresholds."""
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
    return adult, criteria


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
            trace_field(r).astype(np.float64),
            reach=reach,
            border=border,
            arena=trace_arena_mask(r) if border == "wall" else None,
        )
        for r in rows
    ]
    steps = np.array([r["step"] for r in rows], dtype=float)
    series = {k: np.array([f[k] for f in frames]) for k in frames[0]}
    adult, criteria = intrinsic_criteria(
        steps, series, border=border, scale=scale, thresholds=thresholds
    )
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


def replay_engine(
    replay_root: Path, campaigns: list[Path], *, legacy_engine_id: str | None
) -> str:
    """A TT replay names its engine in every replay-manifest.json; a LeniaCLI replay in its receipt."""
    declared = [
        manifest["engine"]
        for manifest in (json.loads((c / "replay-manifest.json").read_text()) for c in campaigns)
        if "engine" in manifest
    ]
    if not declared:
        return read_run_provenance(replay_root, legacy_engine_id=legacy_engine_id).engine_id
    if len(declared) != len(campaigns) or len(set(declared)) != 1:
        raise ValueError(
            f"{replay_root}: campaigns disagree on their replay-manifest engine: "
            f"{sorted(Counter(declared).items())} of {len(campaigns)} campaigns"
        )
    if (replay_root / RECEIPT_FILE).is_file():
        raise ValueError(
            f"{replay_root} has both a {RECEIPT_FILE} and manifest engine {declared[0]}; "
            "one replay has one engine record"
        )
    if legacy_engine_id is not None and legacy_engine_id != declared[0]:
        raise ValueError(
            f"--engine-id {legacy_engine_id} contradicts manifest engine {declared[0]} in {replay_root}"
        )
    return declared[0]


def assess_replay(
    *,
    replay_root: Path,
    output_path: Path,
    horizon: int,
    workers: int,
    legacy_engine_id: str | None = None,
) -> dict[str, Any]:
    """Assess every campaign of a replay run whose trace reaches `horizon`; refuse partial runs."""
    campaigns = sorted((replay_root / "campaigns").iterdir())
    engine = replay_engine(replay_root, campaigns, legacy_engine_id=legacy_engine_id)
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
            {
                "engine": engine,
                "thresholds": asdict(PROVISIONAL),
                "core_level": CORE_LEVEL,
                "bodies": results,
            }
        )
    )
    return {
        "output": str(output_path),
        "engine": engine,
        "bodies": len(results),
        "creatures": sorted(r["body"] for r in results if r["intrinsic_creature"]),
        "failures": {
            r["body"]: [k for k, v in r["criteria"].items() if not v]
            for r in results
            if not r["intrinsic_creature"]
        },
    }


def load_assessment(path: Path, *, legacy_engine_id: str | None) -> dict[str, Any]:
    """An assess-creatures output; one written before engines were recorded needs --engine-id."""
    data = json.loads(path.read_text())
    if "engine" not in data:
        if legacy_engine_id is None:
            raise ValueError(
                f"{path} names no engine; re-run assess-creatures, or pass --engine-id <id> "
                "for an assessment written before engines were recorded"
            )
        return {**data, "engine": legacy_engine_id}
    if legacy_engine_id is not None and legacy_engine_id != data["engine"]:
        raise ValueError(f"--engine-id {legacy_engine_id} contradicts {path}, which names engine {data['engine']}")
    return data


def definition_of(data: dict[str, Any], *, source: str) -> dict[str, Any]:
    """What a verdict depends on besides the trace: the engine that ran it and the thresholds that judged it."""
    missing = [k for k in ("engine", "thresholds", "core_level") if k not in data]
    if missing:
        raise ValueError(
            f"{source} has no {', '.join(missing)}; regenerate it with assess-creatures or "
            "classify-creatures (classify-creatures --engine-id names the engine of assessments "
            "written before engines were recorded)"
        )
    return {"engine": data["engine"], "thresholds": data["thresholds"], "core_level": data["core_level"]}


def require_same_thresholds(
    reference: dict[str, Any], definition: dict[str, Any], *, source: str
) -> None:
    if (definition["thresholds"], definition["core_level"]) != (
        reference["thresholds"],
        reference["core_level"],
    ):
        raise ValueError(
            f"{source} was judged with other thresholds or core level than the other inputs; "
            "re-assess so every input uses one definition"
        )


def _torus_runs(
    assessments: list[Path], *, legacy_engine_id: str | None
) -> tuple[dict[str, Any], dict[int, dict[str, dict[str, Any]]]]:
    """Assessed bodies per torus arena size, refusing any input that would make the join ambiguous."""
    runs: dict[int, dict[str, dict[str, Any]]] = {}
    reference: dict[str, Any] | None = None
    for path in assessments:
        data = load_assessment(path, legacy_engine_id=legacy_engine_id)
        definition = definition_of(data, source=str(path))
        if reference is None:
            reference = definition
        if definition["engine"] != reference["engine"]:
            raise ValueError(
                f"{path} comes from engine {definition['engine']}, not {reference['engine']}; "
                "an ensemble verdict combines runs of one engine"
            )
        require_same_thresholds(reference, definition, source=str(path))
        bodies = data["bodies"]
        borders = {b["border"] for b in bodies}
        arenas = {b["arena"] for b in bodies}
        if borders != {"torus"} or len(arenas) != 1:
            raise ValueError(
                f"{path}: need one torus arena size, got borders {borders} and arenas {arenas}"
            )
        repeated = sorted(b for b, n in Counter(b["body"] for b in bodies).items() if n > 1)
        if repeated:
            raise ValueError(
                f"{path}: bodies assessed more than once: {repeated}; a body needs one run per arena"
            )
        arena = arenas.pop()
        if arena in runs:
            raise ValueError(f"{path}: arena {arena} given twice")
        runs[arena] = {b["body"]: b for b in bodies}
    if reference is None or len(runs) < 2:
        raise ValueError("need torus assessments at two or more arena sizes")
    if len({frozenset(r) for r in runs.values()}) != 1:
        raise ValueError("assessments cover different bodies")
    return reference, runs


def _ensemble_verdict(passes: list[bool]) -> str:
    return "creature" if all(passes) else "unstable" if any(passes) else "not_creature"


def classify_ensemble(
    *, assessments: list[Path], output_path: Path, legacy_engine_id: str | None = None
) -> dict[str, Any]:
    """Combine assess-creatures outputs for the same bodies on the torus at different arena sizes."""
    definition, runs = _torus_runs(assessments, legacy_engine_id=legacy_engine_id)
    arenas = sorted(runs)
    verdicts = {}
    for body in sorted(runs[arenas[0]]):
        passes = {a: runs[a][body]["intrinsic_creature"] for a in arenas}
        verdicts[body] = {
            "verdict": _ensemble_verdict(list(passes.values())),
            "passes_by_arena": passes,
        }
    output_path.write_text(
        json.dumps({**definition, "arenas": arenas, "bodies": verdicts}, indent=1)
    )
    counts = {v: sum(b["verdict"] == v for b in verdicts.values()) for v in VERDICTS}
    return {"output": str(output_path), "engine": definition["engine"], "arenas": arenas, **counts}


def _sweep_settings() -> list[tuple[str, float, Thresholds]]:
    settings = []
    for knob, values in SWEEP_GRID.items():
        for value in values:
            if knob == "band_scale":
                thresholds = replace(
                    PROVISIONAL,
                    band_abs={k: v * value for k, v in PROVISIONAL.band_abs.items()},
                    band_rel={k: v * value for k, v in PROVISIONAL.band_rel.items()},
                )
            elif knob == "smoothing_steps":
                thresholds = replace(PROVISIONAL, smoothing_steps=int(value))
            else:
                thresholds = replace(PROVISIONAL, **{knob: value})
            settings.append((knob, value, thresholds))
    return settings


def _intrinsic_pass(body: dict[str, Any], thresholds: Thresholds) -> bool:
    series = {k: np.asarray(v, dtype=float) for k, v in body["series"].items()}
    _, criteria = intrinsic_criteria(
        np.asarray(body["steps"], dtype=float),
        series,
        border=body["border"],
        scale=body["field_scale"],
        thresholds=thresholds,
    )
    return all(criteria.values())


def sweep_thresholds(
    *, assessments: list[Path], output_path: Path, legacy_engine_id: str | None = None
) -> dict[str, Any]:
    """Re-classify torus assessments with one threshold at a time moved over SWEEP_GRID.

    The frame series in each assessment do not depend on the thresholds, so no trace is re-read. A
    body is stable when no setting changes its ensemble verdict from the PROVISIONAL one.
    """
    definition, runs = _torus_runs(assessments, legacy_engine_id=legacy_engine_id)
    if definition["thresholds"] != asdict(PROVISIONAL) or definition["core_level"] != CORE_LEVEL:
        raise ValueError(
            "assessments were judged with other thresholds than PROVISIONAL; the sweep is centred "
            "on PROVISIONAL, so re-assess them first"
        )
    arenas = sorted(runs)
    bodies = sorted(runs[arenas[0]])
    provisional = {}
    for body in bodies:
        for a in arenas:
            if _intrinsic_pass(runs[a][body], PROVISIONAL) != runs[a][body]["intrinsic_creature"]:
                raise ValueError(
                    f"{body} at arena {a}: PROVISIONAL no longer reproduces the stored verdict; "
                    "the criteria changed since this assessment, so re-assess it"
                )
        provisional[body] = _ensemble_verdict([runs[a][body]["intrinsic_creature"] for a in arenas])
    flips: dict[str, list[dict[str, Any]]] = {body: [] for body in bodies}
    settings = []
    for knob, value, thresholds in _sweep_settings():
        verdicts = {
            body: _ensemble_verdict([_intrinsic_pass(runs[a][body], thresholds) for a in arenas])
            for body in bodies
        }
        for body, verdict in verdicts.items():
            if verdict != provisional[body]:
                flips[body].append({"knob": knob, "value": value, "verdict": verdict})
        settings.append(
            {
                "knob": knob,
                "value": value,
                "counts": {v: sum(x == v for x in verdicts.values()) for v in VERDICTS},
                "flipped": sum(verdicts[b] != provisional[b] for b in bodies),
            }
        )
    per_body = {
        body: {
            "provisional": provisional[body],
            "flips": len(flips[body]),
            "stable": not flips[body],
            "flipped_settings": flips[body],
        }
        for body in bodies
    }
    output_path.write_text(
        json.dumps(
            {
                **definition,
                "arenas": arenas,
                "grid": {k: list(v) for k, v in SWEEP_GRID.items()},
                "settings": settings,
                "bodies": per_body,
            },
            indent=1,
        )
    )
    return {
        "output": str(output_path),
        "engine": definition["engine"],
        "arenas": arenas,
        "settings": len(settings),
        "bodies": len(bodies),
        "stable": sum(b["stable"] for b in per_body.values()),
        "provisional": {v: sum(x == v for x in provisional.values()) for v in VERDICTS},
        "flips_by_count": dict(sorted(Counter(b["flips"] for b in per_body.values()).items())),
        "flipped_by_knob": {
            knob: sum(s["flipped"] for s in settings if s["knob"] == knob) for knob in SWEEP_GRID
        },
    }
