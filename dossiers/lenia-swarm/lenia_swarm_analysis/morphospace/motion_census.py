"""Motion classes of torus replays from the mass centre track of their full-resolution trace fields.

A trace field is the mass recentred by `round(arena/2 - centre)` on the linear centroid, which is
wrong for a body straddling the seam. The circular mean of the recentred field, shifted back,
is the torus mass centre whatever the linear centroid did, so no engine change is needed.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis._io import read_jsonl
from lenia_swarm_analysis.trace_codec import trace_field

from .creature_definition import replay_engine
from .requalification import _body_spec, _lineage

WINDOW = (20000, 40000)
SEGMENT_STEPS = 2000
SEGMENT_MIN = 0.5
CLASSES = ("translating", "stationary", "other_motion")


@dataclass(frozen=True)
class MotionThresholds:
    translate_displacement: float
    heading_min: float
    stationary_displacement: float
    stationary_rg: float


PROVISIONAL_MOTION = MotionThresholds(
    translate_displacement=20.0,
    heading_min=0.9,
    stationary_displacement=10.0,
    stationary_rg=5.0,
)
MOTION_SWEEP_GRID = {
    "translate_displacement": (15.0, 20.0, 30.0),
    "heading_min": (0.8, 0.9, 0.95),
    "stationary_displacement": (5.0, 10.0, 15.0),
    "stationary_rg": (3.0, 5.0, 8.0),
}


def _swift_round(value: np.float32) -> int:
    """Swift's `round` on Float: half away from zero, so ties match the replay's recentring shift."""
    return int(math.copysign(math.floor(abs(float(value)) + 0.5), float(value)))


def _circular_mean(weights: np.ndarray) -> float:
    n = weights.size
    resultant = (weights * np.exp(2j * np.pi * np.arange(n) / n)).sum()
    return float(np.angle(resultant) % (2 * np.pi) * n / (2 * np.pi))


def torus_centre(row: dict[str, Any]) -> tuple[float, float]:
    """Torus (y, x) mass centre, in arena cells, of a trace row recorded at full resolution."""
    width, height = row["width"], row["height"]
    if width != height or row["fieldResolution"] != width:
        raise ValueError(
            f"trace step {row['step']}: field {row['fieldResolution']} on arena {width}x{height}; "
            "the centre is only recoverable from an unresampled field of a square arena"
        )
    field = trace_field(row).astype(np.float64)
    half = np.float32(width) * np.float32(0.5)
    shift_y = _swift_round(half - np.float32(row["centerY"]))
    shift_x = _swift_round(half - np.float32(row["centerX"]))
    y = (_circular_mean(field.sum(axis=1)) - shift_y) % height
    x = (_circular_mean(field.sum(axis=0)) - shift_x) % width
    return y, x


def unwrap(track: np.ndarray, arena: int) -> np.ndarray:
    """Unwrap a torus track by the minimum image; refuse frames too far apart to be unambiguous."""
    steps = (np.diff(track, axis=0) + arena / 2) % arena - arena / 2
    jump = float(np.abs(steps).max()) if len(steps) else 0.0
    if jump > arena / 4:
        raise ValueError(
            f"the centre moved {jump:.1f} cells between frames on arena {arena}; "
            "the minimum image is ambiguous past arena/4, so trace more often"
        )
    return np.vstack([track[:1], track[:1] + np.cumsum(steps, axis=0)])


def motion_metrics(steps: np.ndarray, track: np.ndarray) -> dict[str, Any]:
    """D, P, S, Rg and heading persistence H of an unwrapped track sampled at `steps`.

    H is undefined when any segment moves less than SEGMENT_MIN cells, because a heading below
    that is dominated by shape jitter rather than motion.
    """
    bounds = np.arange(steps[0], steps[-1] + 1, SEGMENT_STEPS)
    if bounds[-1] != steps[-1] or not np.isin(bounds, steps).all():
        raise ValueError(f"trace steps do not hold every {SEGMENT_STEPS}-step segment boundary")
    points = track[np.searchsorted(steps, bounds)]
    segments = np.diff(points, axis=0)
    lengths = np.hypot(segments[:, 0], segments[:, 1])
    displacement = float(np.hypot(*(track[-1] - track[0])))
    path = float(np.hypot(*np.diff(track, axis=0).T).sum())
    heading = None
    if (lengths >= SEGMENT_MIN).all():
        units = segments / lengths[:, None]
        heading = float(np.hypot(*units.mean(axis=0)))
    return {
        "D": displacement,
        "P": path,
        "S": displacement / path if path > 0 else None,
        "Rg": float(np.sqrt(((track - track.mean(axis=0)) ** 2).sum(axis=1).mean())),
        "H": heading,
        "min_segment": float(lengths.min()),
    }


def motion_class(metrics: dict[str, Any], thresholds: MotionThresholds) -> str:
    if (
        metrics["D"] >= thresholds.translate_displacement
        and metrics["H"] is not None
        and metrics["H"] >= thresholds.heading_min
    ):
        return "translating"
    if (
        metrics["D"] < thresholds.stationary_displacement
        and metrics["Rg"] < thresholds.stationary_rg
    ):
        return "stationary"
    return "other_motion"


def campaign_motion(campaign: Path) -> dict[str, Any]:
    """Torus track and motion metrics of one replay campaign over WINDOW."""
    rows = [
        r
        for r in read_jsonl(campaign / "development-trace.jsonl")
        if WINDOW[0] <= r["step"] <= WINDOW[1]
    ]
    steps = np.array([r["step"] for r in rows])
    if not len(rows) or steps[0] != WINDOW[0] or steps[-1] != WINDOW[1]:
        raise ValueError(f"{campaign}: trace does not span steps {WINDOW[0]} to {WINDOW[1]}")
    config = json.loads((campaign / "config.json").read_text())
    if config["reintegration"]["border"] != "torus":
        raise ValueError(f"{campaign}: motion classes are defined on the torus only")
    arena = rows[0]["width"]
    track = unwrap(np.array([torus_centre(r) for r in rows]), arena)
    return {
        "body": json.loads((campaign / "replay-manifest.json").read_text())["sourceCreatureId"],
        "campaign": campaign.name,
        "arena": arena,
        "steps": steps.tolist(),
        "track": track.round(4).tolist(),
        "metrics": motion_metrics(steps, track),
    }


def _sweep_settings() -> list[tuple[str, float, MotionThresholds]]:
    return [
        (knob, value, replace(PROVISIONAL_MOTION, **{knob: value}))
        for knob, values in MOTION_SWEEP_GRID.items()
        for value in values
    ]


def _effective(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Bodies that share a rule or a lineage are not independent; hill1 weighs lineages by size."""
    lineages = Counter(r["lineage"] for r in rows)
    p = np.array(list(lineages.values()), dtype=float) / max(len(rows), 1)
    return {
        "bodies": len(rows),
        "rules": len({r["params_sha256"] for r in rows}),
        "lineages": len(lineages),
        "lineages_hill1": float(np.exp(-(p * np.log(p)).sum())) if len(rows) else 0.0,
    }


def _crosstab(rows: list[dict[str, Any]], a: str, b: str) -> dict[str, dict[str, int]]:
    out: dict[str, Counter] = {}
    for r in rows:
        out.setdefault(str(r[a]), Counter())[str(r[b])] += 1
    return {k: dict(sorted(v.items())) for k, v in sorted(out.items())}


def motion_census(
    *,
    replay_roots: list[Path],
    index_path: Path,
    sweeps: list[Path],
    members_path: Path,
    output_path: Path,
    workers: int,
) -> dict[str, Any]:
    """Classify every body's motion on each torus arena and join it with creature verdicts.

    The native arena gives the class; other arenas are agreement. Bodies are counted next to the
    distinct rules and lineages behind them, and panel candidates are sweep-stable creatures that
    translate on every arena, one per lineage, highest native H first.
    """
    engines, campaigns = set(), []
    for root in replay_roots:
        found = sorted((root / "campaigns").iterdir())
        engines.add(replay_engine(root, found, legacy_engine_id=None))
        campaigns += found
    if len(engines) != 1:
        raise ValueError(f"replay roots come from several engines: {sorted(engines)}")
    engine = engines.pop()
    with ProcessPoolExecutor(workers) as pool:
        runs = list(pool.map(campaign_motion, campaigns))

    specs = {}
    for row in read_jsonl(index_path):
        base = json.loads((Path(row["exportDir"]) / "base.json").read_text())
        specs[row["creatureId"]] = {**_body_spec(base), "lineage": _lineage(row)}
    by_body: dict[str, dict[int, dict[str, Any]]] = {}
    for run in runs:
        arenas = by_body.setdefault(run["body"], {})
        if run["arena"] in arenas:
            raise ValueError(f"{run['body']} replayed twice on arena {run['arena']}")
        arenas[run["arena"]] = run
    if set(by_body) != set(specs):
        raise ValueError(
            f"replays and index disagree: {len(set(by_body) - set(specs))} replayed bodies not indexed, "
            f"{len(set(specs) - set(by_body))} indexed bodies not replayed"
        )

    verdicts: dict[str, dict[str, Any]] = {}
    for path in sweeps:
        data = json.loads(path.read_text())
        if data["engine"] != engine:
            raise ValueError(f"{path} judged engine {data['engine']}, the replays ran {engine}")
        for body, v in data["bodies"].items():
            if body in verdicts:
                raise ValueError(f"{body} appears in two sweeps")
            verdicts[body] = v
    if set(verdicts) != set(specs):
        raise ValueError("the sweeps do not cover exactly the indexed bodies")
    prior = {
        m["body"]: m["original"].get("motion_class")
        for m in json.loads(members_path.read_text())["members"]
    }

    settings = _sweep_settings()
    bodies = []
    for body in sorted(specs):
        spec, arenas = specs[body], by_body[body]
        native = spec["native_arena"]
        if native not in arenas:
            raise ValueError(f"{body} has no replay on its native arena {native}")
        classes = {
            a: motion_class(r["metrics"], PROVISIONAL_MOTION) for a, r in sorted(arenas.items())
        }
        flips = [
            {"knob": knob, "value": value, "class": c}
            for knob, value, t in settings
            if (c := motion_class(arenas[native]["metrics"], t)) != classes[native]
        ]
        bodies.append(
            {
                "body": body,
                "params_sha256": spec["params_sha256"],
                "lineage": spec["lineage"],
                "native_arena": native,
                "verdict": verdicts[body]["provisional"],
                "sweep_stable": verdicts[body]["stable"],
                "prior_motion_class": prior.get(body) or "none_recorded",
                "motion_class": classes[native],
                "classes_by_arena": {str(a): c for a, c in classes.items()},
                "arenas_agree": len(set(classes.values())) == 1,
                "motion_stable": not flips,
                "motion_flips": flips,
                "arenas": {
                    str(a): {k: r[k] for k in ("campaign", "metrics", "steps", "track")}
                    for a, r in sorted(arenas.items())
                },
            }
        )

    adults = [b for b in bodies if b["verdict"] == "creature" and b["sweep_stable"]]

    def counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {c: _effective([r for r in rows if r["motion_class"] == c]) for c in CLASSES}

    candidates = sorted(
        (b for b in adults if set(b["classes_by_arena"].values()) == {"translating"}),
        key=lambda b: (
            -b["arenas"][str(b["native_arena"])]["metrics"]["H"],
            -b["arenas"][str(b["native_arena"])]["metrics"]["D"],
            b["body"],
        ),
    )
    panel, taken = [], set()
    for b in candidates:
        if b["lineage"] not in taken:
            taken.add(b["lineage"])
            panel.append(b)
    sweep_counts = [
        {
            "knob": knob,
            "value": value,
            "adults": dict(
                Counter(
                    motion_class(b["arenas"][str(b["native_arena"])]["metrics"], t) for b in adults
                )
            ),
        }
        for knob, value, t in settings
    ]
    summary = {
        "engine": engine,
        "window": list(WINDOW),
        "segment_steps": SEGMENT_STEPS,
        "thresholds": asdict(PROVISIONAL_MOTION),
        "sweep_grid": {k: list(v) for k, v in MOTION_SWEEP_GRID.items()},
        "bodies": len(bodies),
        "verdicts": _crosstab(bodies, "verdict", "sweep_stable"),
        "all_bodies": counts(bodies),
        "sweep_stable_creatures": counts(adults),
        "sweep_stable_creatures_motion_stable": counts([b for b in adults if b["motion_stable"]]),
        "native_vs_other_arenas": _crosstab(
            [{**b, "agree": b["arenas_agree"]} for b in adults], "motion_class", "agree"
        ),
        "prior_vs_native_all": _crosstab(bodies, "prior_motion_class", "motion_class"),
        "prior_vs_native_adults": _crosstab(adults, "prior_motion_class", "motion_class"),
        "verdict_vs_native": _crosstab(bodies, "verdict", "motion_class"),
        "motion_sweep_adults": sweep_counts,
        "panel_candidates": [
            {
                "body": b["body"],
                "lineage": b["lineage"],
                "params_sha256": b["params_sha256"],
                "native_arena": b["native_arena"],
                "metrics_by_arena": {a: r["metrics"] for a, r in b["arenas"].items()},
                "motion_stable": b["motion_stable"],
            }
            for b in panel
        ],
        "translating_adults_per_lineage": dict(Counter(b["lineage"] for b in candidates)),
    }
    output_path.write_text(json.dumps({**summary, "per_body": bodies}, indent=1))
    return {k: summary[k] for k in ("engine", "bodies", "verdicts", "sweep_stable_creatures")} | {
        "output": str(output_path),
        "panel_candidates": [b["body"] for b in panel],
    }
