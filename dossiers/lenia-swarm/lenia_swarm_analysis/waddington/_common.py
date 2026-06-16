"""Shared primitives for the Waddington analyses.

These were duplicated across the analysis modules; they live here once. Everything operates on the
canonical 16 terminal morphospace axes (`AXIS` maps axis id -> column).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from ..transformation_metrics import TERMINAL_AXIS_IDS

AXIS = {a: i for i, a in enumerate(TERMINAL_AXIS_IDS)}


def stable_rank(creature_id: str) -> int:
    """Deterministic shard-independent ordering key, so replay/sampling sets rerun identically."""
    return int.from_bytes(hashlib.sha256(creature_id.encode()).digest()[:8], "big")


def zscore(matrix: np.ndarray) -> np.ndarray:
    std = matrix.std(0)
    std[std == 0] = 1.0
    return (matrix - matrix.mean(0)) / std


def pca2(z: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For an already z-scored matrix: returns (coords[N,2], components[2,D], variance_ratio[2])."""
    _, s, vt = np.linalg.svd(z, full_matrices=False)
    comps = vt[:2]
    return z @ comps.T, comps, (s**2 / (s**2).sum())[:2]


def silhouette(z: np.ndarray, labels: np.ndarray) -> float:
    """Mean silhouette over the label classes: +1 tight, 0 at the border, negative if intermixed."""
    from scipy.spatial.distance import cdist

    uniq = sorted(set(labels.tolist()))
    idx = np.array([uniq.index(x) for x in labels])
    intra, nearest = [], []
    for i in range(len(z)):
        intra.append(float(np.mean(cdist([z[i]], z[idx == idx[i]])[0])))
        others = [float(np.mean(cdist([z[i]], z[idx == k])[0]))
                  for k in range(len(uniq)) if k != idx[i] and (idx == k).any()]
        nearest.append(min(others) if others else np.nan)
    with np.errstate(invalid="ignore"):
        return float(np.nanmean((np.array(nearest) - np.array(intra))
                                / np.maximum(np.array(intra), np.array(nearest))))


def is_coherent(axes: np.ndarray) -> bool:
    """The automated eyeball criterion: a settled, localized, undissolved creature. `axes` is the
    per-step [T,16] trajectory. Invariant: ends with mass, never blows up, never shatters."""
    cov = axes[:, AXIS["coverage"]]
    frag = axes[:, AXIS["fragmentation"]]
    return bool(cov[-1] > 0.0008 and cov.max() < 0.18 and np.median(frag) < 8)


def iter_family_traces(replay_dir: Path, family_map: dict) -> Iterator[tuple[str, str, list[dict]]]:
    """Yield (family, source_creature_id, rows-sorted-by-step) for each replayed family creature."""
    for camp in sorted(replay_dir.glob("campaigns/*")):
        manifest = camp / "replay-manifest.json"
        trace = camp / "development-trace.jsonl"
        if not (manifest.exists() and trace.exists()):
            continue
        src = str(json.loads(manifest.read_text()).get("sourceCreatureId"))
        fam = family_map.get(src)
        if fam is None:
            continue
        rows = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
        rows.sort(key=lambda r: int(r["step"]))
        yield fam, src, rows
