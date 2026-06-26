"""Uniform-random-genotype control experiment.

The main study replays search-discovered, filter-passing creatures, so its landscape is biased by
survivorship (only viable creatures) and discovery (where the optimizer looked). This control
replays genotypes sampled uniformly over the full Flow-Lenia parameter ranges, with no filter, so
the result maps the unfiltered outcome distribution. Comparing the two shows how small a slice of
parameter space the discovered creatures occupy.

Stages: random-inputs (synthesize scout dirs) -> LeniaCLI replay --development-trace ->
ingest-random -> compare (project random terminals onto the harvest basis and contrast densities).
"""

from __future__ import annotations

import json
import random
import shutil

import duckdb
import numpy as np

from ..morphospace.ingest_replay import ingest_replay_batch
from ..morphospace.warehouse import connect_database
from ..transformation_metrics import (
    TERMINAL_AXIS_IDS,
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)
from ._common import stable_rank
from .ingest import STUDY_MAP_PATH
from .landscape import RESULT_PATH, SMOOTH_SIGMA, smooth2d
from .study import (
    CONFIGS,
    PARAM_RANGES,
    RANDOM_SPECIMENS_PER_CONFIG,
    RUN_ROOT,
    STUDY_ROOT,
    WAREHOUSE_DB,
    RuleConfig,
    random_replay_path,
    random_scout_path,
)

RANDOM_STUDY_MAP = STUDY_ROOT / "random_study_map.json"
COMPARE_SUMMARY = STUDY_ROOT / "random_compare.json"


def _resample(value, lo: float, hi: float, rng: random.Random):
    if isinstance(value, list):
        return [_resample(v, lo, hi, rng) for v in value]
    return rng.uniform(lo, hi)


def _sync_randomized_manifest(entry: dict, creature_id: str, genotype: dict) -> None:
    manifest = entry.get("specimen_manifest")
    if not isinstance(manifest, dict):
        return
    manifest["creatureID"] = creature_id
    manifest["specimenID"] = creature_id
    snapshots = manifest.get("snapshots")
    if not isinstance(snapshots, dict):
        snapshots = {}
        manifest["snapshots"] = snapshots
    snapshots["genotype"] = genotype


def build_config_random_inputs(config: RuleConfig, target: int) -> int:
    shards = sorted(RUN_ROOT.glob(config.shard_glob))
    if not shards:
        raise SystemExit(f"{config.label}: no shards match {config.shard_glob}")
    per_shard = -(-target // len(shards))
    templates: list[tuple[int, str]] = []
    for shard in shards:
        index_path = shard / "library" / "index.jsonl"
        if not index_path.exists():
            raise SystemExit(f"missing library index: {index_path}")
        rows = []
        with index_path.open() as fh:
            for line in fh:
                if not line.strip():
                    continue
                entry = json.loads(line)
                rows.append((stable_rank(entry["creature"]["id"]), line.rstrip("\n")))
        rows.sort(key=lambda r: r[0])
        templates.extend(rows[:per_shard])
    templates = templates[:target]

    scout = random_scout_path(config.config_hash)
    (scout / "library").mkdir(parents=True, exist_ok=True)
    shutil.copy(shards[0] / "config.json", scout / "config.json")
    shutil.copy(shards[0] / "search.json", scout / "search.json")
    rng = random.Random(int(config.config_hash[:8], 16))
    out_path = scout / "library" / "index.jsonl"
    with out_path.open("w") as out:
        for i, (_, line) in enumerate(templates):
            entry = json.loads(line)
            genotype = entry["creature"]["genotype"]
            for key, (lo, hi) in PARAM_RANGES.items():
                genotype[key] = _resample(genotype[key], lo, hi, rng)
            creature_id = str(__import__("uuid").UUID(int=rng.getrandbits(128)))
            entry["creature"]["id"] = creature_id
            entry["creature"]["name"] = f"random-{config.label}-{i}"
            _sync_randomized_manifest(entry, creature_id, genotype)
            out.write(json.dumps(entry) + "\n")
    return len(templates)


def build_random_inputs() -> None:
    for config in CONFIGS:
        n = build_config_random_inputs(config, RANDOM_SPECIMENS_PER_CONFIG)
        print(f"{config.label}: {n} random templates -> {random_scout_path(config.config_hash)}")


def ingest_random() -> dict[str, str]:
    conn = connect_database(WAREHOUSE_DB)
    mapping: dict[str, str] = {}
    for config in CONFIGS:
        run = random_replay_path(config.config_hash)
        if not run.exists():
            raise SystemExit(f"missing random replay run for {config.label}: {run}")
        study_id = ingest_replay_batch(
            conn, development_traces_path=run, label=f"waddington-random-{config.label}"
        )
        mapping[config.config_hash] = study_id
        print(f"{config.label}: random study {study_id}")
    conn.close()
    RANDOM_STUDY_MAP.write_text(json.dumps(mapping, indent=2))
    return mapping


def _load_terminals(conn, study_id, mean, std, comps):
    rows = conn.execute(
        """
        SELECT terminal_descriptor_json, specimen_id FROM (
            SELECT ds.specimen_id, ds.step, ds.terminal_descriptor_json,
                   row_number() OVER (PARTITION BY ds.specimen_id ORDER BY ds.step DESC) AS rn
            FROM development_samples ds
            JOIN study_specimens ss USING (specimen_id)
            WHERE ss.study_id = ?
        ) WHERE rn = 1
        """,
        [study_id],
    ).fetchall()
    coords, occ, gyr = [], [], []
    for terminal_json, sid in rows:
        terminal = json.loads(terminal_json)
        raw = extract_terminal_raw_axes_from_descriptors(
            terminal=terminal, trajectory={"centerVelocity": 0.0, "pathTortuosity": 0.0},
            specimen_id=sid,
        )
        vec = np.array([float(transform_axes(raw)[a]) for a in TERMINAL_AXIS_IDS])
        coords.append(((vec - mean) / std) @ comps.T)
        occ.append(float(terminal["finalOccupancy"]))
        gyr.append(float(terminal["finalGyration"]))
    return np.array(coords), np.array(occ), np.array(gyr)


def _density(coords, ex, ey):
    h, _, _ = np.histogram2d(coords[:, 0], coords[:, 1], bins=[ex, ey])
    p = smooth2d(h, SMOOTH_SIGMA)
    return p / p.sum()


def _motion_metrics(replay_dir, cap: int):
    """Pull canonical terminal motion metrics from a replay run's results.jsonl files."""
    import glob

    vel, disp, directed = [], [], []
    files = sorted(glob.glob(str(replay_dir / "campaigns" / "*" / "results.jsonl")))[:cap]
    for f in files:
        try:
            with open(f) as fh:
                r = json.loads(fh.readline())
        except (OSError, json.JSONDecodeError):
            continue
        m = r.get("metrics", {})
        v = m.get("center_velocity")
        d = m.get("displacement")
        pl = m.get("path_length")
        if v is not None:
            vel.append(float(v))
        if d is not None:
            disp.append(float(d))
        if d is not None and pl:
            directed.append(float(d) / float(pl) if float(pl) > 1e-9 else 0.0)
    return np.array(vel), np.array(disp), np.array(directed)


def motion_compare() -> None:
    """Compare the motion the search SCORE rewarded (center velocity, displacement, directedness)
    between harvest-discovered and uniform-random genotypes. The shape morphospace overlapped; if
    score-selection biased motion, harvest should be shifted toward faster, more directed movers."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from .study import FIGURES_DIR, replay_run_path

    cap = 5000
    summary = {}
    fig, axes = plt.subplots(2, 2, figsize=(13, 10.5))
    for ax, config in zip(axes.ravel(), CONFIGS, strict=True):
        h = config.config_hash
        hv_vel, hv_disp, hv_dir = _motion_metrics(replay_run_path(h), cap)
        rd_vel, rd_disp, rd_dir = _motion_metrics(random_replay_path(h), cap)
        bins = np.linspace(0, np.percentile(np.concatenate([hv_vel, rd_vel]), 99), 50)
        ax.hist(rd_vel, bins=bins, density=True, alpha=0.5, color="crimson", label="random")
        ax.hist(hv_vel, bins=bins, density=True, alpha=0.5, color="navy", label="harvest")
        ax.axvline(np.median(rd_vel), color="crimson", ls="--", lw=1)
        ax.axvline(np.median(hv_vel), color="navy", ls="--", lw=1)
        ax.set_title(f"{config.label}: center velocity")
        ax.set_xlabel("center velocity")
        ax.legend(fontsize=8)
        summary[config.label] = {
            "harvest_median_velocity": round(float(np.median(hv_vel)), 4),
            "random_median_velocity": round(float(np.median(rd_vel)), 4),
            "velocity_ratio_harvest_over_random": round(
                float(np.median(hv_vel) / max(np.median(rd_vel), 1e-9)), 3
            ),
            "harvest_median_displacement": round(float(np.median(hv_disp)), 3),
            "random_median_displacement": round(float(np.median(rd_disp)), 3),
            "harvest_median_directedness": (
                round(float(np.median(hv_dir)), 3) if len(hv_dir) else None
            ),
            "random_median_directedness": (
                round(float(np.median(rd_dir)), 3) if len(rd_dir) else None
            ),
        }
    fig.suptitle("Motion the score rewarded: harvest vs uniform-random genotypes")
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURES_DIR / "random_vs_harvest_motion.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    (STUDY_ROOT / "random_motion_compare.json").write_text(json.dumps(summary, indent=2))
    print(f"wrote {out}")
    for label, s in summary.items():
        print(f"{label}: {s}")


def compare() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from .study import FIGURES_DIR

    harvest_map = json.loads(STUDY_MAP_PATH.read_text())
    random_map = json.loads(RANDOM_STUDY_MAP.read_text())
    d = np.load(RESULT_PATH)
    mean, std, comps = d["mean"], d["std"], d["components"]
    conn = duckdb.connect(str(WAREHOUSE_DB), read_only=True)
    conn.execute("SET memory_limit='8GB'")
    conn.execute("SET threads=4")

    loaded = {}
    lo = np.array([1e9, 1e9])
    hi = np.array([-1e9, -1e9])
    for config in CONFIGS:
        hv = _load_terminals(conn, harvest_map[config.config_hash], mean, std, comps)
        rd = _load_terminals(conn, random_map[config.config_hash], mean, std, comps)
        loaded[config.config_hash] = (hv, rd)
        for c in (hv[0], rd[0]):
            lo = np.minimum(lo, np.percentile(c, 0.5, axis=0))
            hi = np.maximum(hi, np.percentile(c, 99.5, axis=0))
    ex = np.linspace(lo[0], hi[0], 80)
    ey = np.linspace(lo[1], hi[1], 80)

    summary = {}
    fig, axes = plt.subplots(2, 2, figsize=(13, 11.5))
    for ax, config in zip(axes.ravel(), CONFIGS, strict=True):
        (hv_c, hv_occ, hv_gyr), (rd_c, rd_occ, rd_gyr) = loaded[config.config_hash]
        ax.scatter(rd_c[:, 0], rd_c[:, 1], s=3, c="crimson", alpha=0.15, lw=0, label="random")
        ax.scatter(hv_c[:, 0], hv_c[:, 1], s=3, c="navy", alpha=0.2, lw=0, label="harvest")
        # fraction of random terminals landing in harvest-occupied cells
        ph = _density(hv_c, ex, ey)
        occupied = ph > ph.max() * 0.02
        rx = np.clip(np.digitize(rd_c[:, 0], ex) - 1, 0, len(ex) - 2)
        ry = np.clip(np.digitize(rd_c[:, 1], ey) - 1, 0, len(ey) - 2)
        in_harvest = float(occupied[rx, ry].mean())
        summary[config.label] = {
            "random_in_harvest_region_frac": round(in_harvest, 3),
            "harvest_median_occupancy": round(float(np.median(hv_occ)), 3),
            "random_median_occupancy": round(float(np.median(rd_occ)), 3),
            "harvest_median_gyration": round(float(np.median(hv_gyr)), 1),
            "random_median_gyration": round(float(np.median(rd_gyr)), 1),
        }
        ax.set_title(f"{config.label}: {in_harvest*100:.0f}% of random in harvest zone")
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
        ax.legend(markerscale=3, loc="upper right", fontsize=8)
    fig.suptitle("Harvest (discovered, viable) vs uniform-random genotypes in the same morphospace")
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURES_DIR / "random_vs_harvest.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    COMPARE_SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out} and {COMPARE_SUMMARY}")
    for label, s in summary.items():
        print(f"{label}: {s}")
