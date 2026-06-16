"""Perturbation/canalization experiment: the direct Waddington test.

Ablate a square patch of each creature's state mid-development (zero_state_patch at PERTURB_STEP),
let it continue, and measure whether it returns to the attractor it would have reached unperturbed.
We replay the same sampled creatures twice (baseline, no intervention; perturbed, with the ablation)
and compare terminal morphology. The canalization claim: deeper valleys (denser, more attracting
endpoints) recover better, i.e. valley depth predicts recovery.

Stages: perturb-inputs -> LeniaCLI replay (both variants) -> ingest-perturb -> perturb-analyze.
"""

from __future__ import annotations

import json
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
from .landscape import GRID, RESULT_PATH, smooth2d
from .study import (
    CONFIGS,
    PERTURB_SIZE,
    PERTURB_SPECIMENS_PER_CONFIG,
    PERTURB_STEP,
    RUN_ROOT,
    STUDY_ROOT,
    WAREHOUSE_DB,
    RuleConfig,
    perturb_replay_path,
    perturb_scout_path,
)

PERTURB_STUDY_MAP = STUDY_ROOT / "perturb_study_map.json"
PERTURB_SUMMARY = STUDY_ROOT / "perturb_analyze.json"
VARIANTS = ("baseline", "perturbed")


def _intervention(variant: str):
    if variant == "baseline":
        return []
    return [{
        "version": 1,
        "type": "zero_state_patch",
        "step": PERTURB_STEP,
        "patch": {"center": [64, 64], "size": PERTURB_SIZE},
    }]


def build_config_perturb_inputs(config: RuleConfig, target: int) -> int:
    shards = sorted(RUN_ROOT.glob(config.shard_glob))
    per_shard = -(-target // len(shards))
    templates: list[str] = []
    for shard in shards:
        index_path = shard / "library" / "index.jsonl"
        rows = []
        with index_path.open() as fh:
            for line in fh:
                if not line.strip():
                    continue
                rows.append((stable_rank(json.loads(line)["creature"]["id"]), line.rstrip("\n")))
        rows.sort(key=lambda r: r[0])
        templates.extend(line for _, line in rows[:per_shard])
    templates = templates[:target]

    base_config = json.loads((shards[0] / "config.json").read_text())
    for variant in VARIANTS:
        scout = perturb_scout_path(variant, config.config_hash)
        (scout / "library").mkdir(parents=True, exist_ok=True)
        (scout / "library" / "index.jsonl").write_text("\n".join(templates) + "\n")
        shutil.copy(shards[0] / "search.json", scout / "search.json")
        cfg = dict(base_config)
        cfg["profile"] = "experimental"
        cfg["interventions"] = _intervention(variant)
        (scout / "config.json").write_text(json.dumps(cfg))
    return len(templates)


def build_perturb_inputs() -> None:
    for config in CONFIGS:
        n = build_config_perturb_inputs(config, PERTURB_SPECIMENS_PER_CONFIG)
        print(f"{config.label}: {n} perturbation templates (baseline + perturbed)")


def ingest_perturb() -> dict:
    conn = connect_database(WAREHOUSE_DB)
    mapping: dict[str, dict[str, str]] = {}
    for config in CONFIGS:
        mapping[config.config_hash] = {}
        for variant in VARIANTS:
            run = perturb_replay_path(variant, config.config_hash)
            if not run.exists():
                raise SystemExit(f"missing {variant} replay for {config.label}: {run}")
            study_id = ingest_replay_batch(
                conn, development_traces_path=run,
                label=f"waddington-perturb-{variant}-{config.label}",
            )
            mapping[config.config_hash][variant] = study_id
            print(f"{config.label}/{variant}: study {study_id}")
    conn.close()
    PERTURB_STUDY_MAP.write_text(json.dumps(mapping, indent=2))
    return mapping


def _terminals_by_source(conn, study_id, mean, std, comps):
    rows = conn.execute(
        """
        SELECT s.source_creature_id AS src, ds.terminal_descriptor_json AS term FROM (
            SELECT ds.specimen_id, ds.step, ds.terminal_descriptor_json,
                   row_number() OVER (PARTITION BY ds.specimen_id ORDER BY ds.step DESC) AS rn
            FROM development_samples ds
            JOIN study_specimens ss USING (specimen_id)
            WHERE ss.study_id = ?
        ) ds JOIN specimens s USING (specimen_id) WHERE ds.rn = 1
        """,
        [study_id],
    ).fetchall()
    out = {}
    for src, term in rows:
        if src is None:
            continue
        terminal = json.loads(term)
        raw = extract_terminal_raw_axes_from_descriptors(
            terminal=terminal, trajectory={"centerVelocity": 0.0, "pathTortuosity": 0.0},
            specimen_id=str(src),
        )
        vec = np.array([float(transform_axes(raw)[a]) for a in TERMINAL_AXIS_IDS])
        out[str(src)] = ((vec - mean) / std, ((vec - mean) / std) @ comps.T)
    return out


def analyze() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.stats import spearmanr

    from .study import FIGURES_DIR

    mapping = json.loads(PERTURB_STUDY_MAP.read_text())
    d = np.load(RESULT_PATH)
    mean, std, comps, ex, ey = d["mean"], d["std"], d["components"], d["edges_x"], d["edges_y"]
    conn = duckdb.connect(str(WAREHOUSE_DB), read_only=True)
    conn.execute("SET memory_limit='8GB'")
    conn.execute("SET threads=4")

    summary = {}
    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    for ax, config in zip(axes.ravel(), CONFIGS, strict=True):
        h = config.config_hash
        base = _terminals_by_source(conn, mapping[h]["baseline"], mean, std, comps)
        pert = _terminals_by_source(conn, mapping[h]["perturbed"], mean, std, comps)
        shared = sorted(set(base) & set(pert))
        base_coords = np.array([base[s][1] for s in shared])
        # valley depth proxy: local density of baseline terminals (deep valley = high density)
        hist, _, _ = np.histogram2d(base_coords[:, 0], base_coords[:, 1], bins=[ex, ey])
        dens = smooth2d(hist, 1.4)
        dens /= dens.max()
        depth, recovery = [], []
        for s in shared:
            bz, bc = base[s]
            pz, _ = pert[s]
            recovery.append(float(np.linalg.norm(pz - bz)))  # 16-axis z-space distance
            gi = int(np.clip(np.digitize(bc[0], ex) - 1, 0, GRID - 1))
            gj = int(np.clip(np.digitize(bc[1], ey) - 1, 0, GRID - 1))
            depth.append(float(dens[gi, gj]))
        depth = np.array(depth)
        recovery = np.array(recovery)
        r, p = spearmanr(depth, recovery)
        summary[config.label] = {
            "n_matched": len(shared),
            "median_recovery_distance": round(float(np.median(recovery)), 3),
            "spearman_depth_vs_distance": round(float(r), 3),
            "p_value": float(f"{p:.2e}"),
            "interpretation": (
                "deeper valleys recover better" if r < 0 else "no depth->recovery link"
            ),
        }
        ax.scatter(depth, recovery, s=5, alpha=0.25, c="purple", lw=0)
        ax.set_title(f"{config.label}: rho(depth, divergence)={r:.2f}")
        ax.set_xlabel("baseline valley depth (local density)")
        ax.set_ylabel("post-ablation divergence (16-axis)")
        print(f"{config.label}: n={len(shared)} median_div={np.median(recovery):.3f} rho={r:.3f}")

    fig.suptitle(
        f"Canalization: does valley depth predict recovery from mid-development ablation "
        f"(step {PERTURB_STEP}, size {PERTURB_SIZE})?"
    )
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURES_DIR / "perturbation_recovery.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    PERTURB_SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out} and {PERTURB_SUMMARY}")
