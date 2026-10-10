"""Compact per-frame measurements from the organism-birth-signal-v1 frame archive.

Reads the hash-verified 128x128 grayscale frames (restored from the campaign's
verified archive), checks every run's frame digest against the original completion
receipts, and writes block masses, body-centred quadrant masses, centroid, radius
and per-frame SHA-256 to one compressed npz. The full frames are not retained.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

FRAMES = 900
SIZE = 128
GRIDS = (2, 3, 4, 8)
PHASES = (("calibration", "calibration-completion.json"), ("test", "test-completion.json"),
          ("prospective", "prospective-completion.json"))


def block_masses(field: np.ndarray, grid: int) -> np.ndarray:
    edges = np.linspace(0, SIZE, grid + 1).round().astype(int)
    return np.array([[field[edges[i]:edges[i + 1], edges[j]:edges[j + 1]].sum()
                      for j in range(grid)] for i in range(grid)]).ravel()


def circular_centre(profile: np.ndarray) -> float:
    angles = 2 * np.pi * np.arange(SIZE) / SIZE
    angle = np.arctan2((profile * np.sin(angles)).sum(), (profile * np.cos(angles)).sum())
    return float((angle % (2 * np.pi)) * SIZE / (2 * np.pi))


def frame_row(path: Path) -> tuple[np.ndarray, str]:
    raw = path.read_bytes()
    with Image.open(path) as image:
        field = np.asarray(image.convert("L"), dtype=np.float64) / 255.0
    if field.shape != (SIZE, SIZE) or field.sum() <= 0:
        raise ValueError(f"invalid frame {path}")
    mass = field.sum()
    cy = circular_centre(field.sum(axis=1))
    cx = circular_centre(field.sum(axis=0))
    rolled = np.roll(field, (SIZE // 2 - int(round(cy)), SIZE // 2 - int(round(cx))), axis=(0, 1))
    half = SIZE // 2
    body_quadrants = np.array([rolled[:half, :half].sum(), rolled[:half, half:].sum(),
                               rolled[half:, :half].sum(), rolled[half:, half:].sum()])
    axis = np.arange(SIZE, dtype=np.float64)
    ry = (rolled.sum(axis=1) * axis).sum() / mass
    rx = (rolled.sum(axis=0) * axis).sum() / mass
    radius = np.sqrt((rolled * ((axis[:, None] - ry) ** 2 + (axis[None, :] - rx) ** 2)).sum() / mass)
    blocks = [block_masses(field, grid) for grid in GRIDS]
    row = np.concatenate([*blocks, body_quadrants, [cy, cx, radius, mass]])
    return row, hashlib.sha256(raw).hexdigest()


def run_rows(frame_root: Path) -> tuple[np.ndarray, list[str]]:
    results = [frame_row(frame_root / f"frame_{step:06d}.png") for step in range(1, FRAMES + 1)]
    return np.stack([row for row, _ in results]), [digest for _, digest in results]


def receipt_digest(digests: list[str]) -> str:
    """Reproduces the campaign's framesSHA256: name, NUL, raw frame digest, per frame."""
    digest = hashlib.sha256()
    for step, frame_digest in enumerate(digests, start=1):
        digest.update(f"frame_{step:06d}.png".encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(frame_digest))
    return digest.hexdigest()


def load_detector(path: Path):
    spec = importlib.util.spec_from_file_location("frozen_birth_detector", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-root", type=Path, required=True)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    detector = load_detector(args.campaign_dir / "birth_detector.py")
    plan = json.loads((args.campaign_dir / "prospective-plan.json").read_text())
    family = {run["runId"]: run["familyId"] for run in plan["runs"]}
    runs: list[tuple[str, str, str]] = []
    for phase, receipt_name in PHASES:
        receipt = json.loads((args.campaign_dir / receipt_name).read_text())
        runs.extend((phase, run["runId"], run["framesSHA256"]) for run in receipt["runs"])
    roots = [args.frames_root / phase / run_id / "frames" for phase, run_id, _ in runs]
    with ProcessPoolExecutor(max_workers=8) as pool:
        measured = list(pool.map(run_rows, roots))
    data, events, frame_hashes = [], [], []
    for (phase, run_id, expected), (rows, digests) in zip(runs, measured, strict=True):
        digest = receipt_digest(digests)
        if digest != expected:
            raise ValueError(f"{run_id}: frame digest {digest} != receipt {expected}")
        rect = [detector.frame_rectangularity(root / f"frame_{s:06d}.png")
                for root in [args.frames_root / phase / run_id / "frames"] for s in range(1, FRAMES + 1)]
        event = detector.detect(rect)
        data.append(rows)
        events.append(-1 if event is None else int(event))
        frame_hashes.append(digests)
    columns = [f"g{g}_{i}" for g in GRIDS for i in range(g * g)] + [
        "body_q0", "body_q1", "body_q2", "body_q3", "centre_y", "centre_x", "radius", "mass"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        data=np.stack(data).astype(np.float64),
        columns=np.array(columns),
        phase=np.array([phase for phase, _, _ in runs]),
        run_id=np.array([run_id for _, run_id, _ in runs]),
        family=np.array([family.get(run_id, "") for _, run_id, _ in runs]),
        event_step=np.array(events),
        frame_sha256=np.array(frame_hashes),
    )
    print(json.dumps({"runs": len(runs), "output": str(args.output),
                      "censored": [r for (_, r, _), e in zip(runs, events, strict=True) if e < 0]}))


if __name__ == "__main__":
    main()
