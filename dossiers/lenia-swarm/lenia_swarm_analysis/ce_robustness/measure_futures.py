"""Compact measurements from the developmental-causal-impedance-v1 future field records.

Each future run stores 60 body-centred 32x32 total-mass fields (one every 4 steps) with
the body centre in arena pixels. This writes, per record, 8x8 block masses of the field,
the centre, total mass and the SHA-256 of the decoded field bytes. Every run's gz file is
checked against the fieldObservationsSHA256 binding of the future completion receipt.
Bodies in these futures drift by about one pixel over 240 steps, so no arena-frame
reconstruction is kept.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

RESOLUTION = 32
ARENA = 128
BLOCKS = 8
RECORDS = 60
RUN_PATH = Path("runs/vanilla/pmut=0_000/repeat=0/field-observations.jsonl.gz")


def blocks(field: np.ndarray) -> np.ndarray:
    size = RESOLUTION // BLOCKS
    return field.reshape(BLOCKS, size, BLOCKS, size).sum(axis=(1, 3)).ravel()


def measure_run(task: tuple[Path, str]) -> tuple[np.ndarray, list[str]]:
    path, expected = task
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"{path}: field observations digest does not match the receipt")
    records = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
    if len(records) != RECORDS:
        raise ValueError(f"{path}: {len(records)} records")
    rows, digests = [], []
    for record in records:
        if record["fieldResolution"] != RESOLUTION or record["windowSize"] != ARENA:
            raise ValueError(f"{path}: unexpected field geometry")
        payload = base64.b64decode(record["fieldF16Base64"])
        field = np.frombuffer(payload, dtype="<f2").astype(np.float64).reshape(RESOLUTION, RESOLUTION)
        rows.append(np.concatenate([blocks(field), [float(record["centerY"]), float(record["centerX"]),
                                                    float(record["totalMass"]), float(record["step"])]]))
        digests.append(hashlib.sha256(payload).hexdigest())
    return np.stack(rows), digests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--future-root", type=Path, required=True)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    receipt = json.loads((args.campaign_dir / "future-completion.json").read_text())
    runs = receipt["runs"]
    tasks = [(args.future_root / run["runId"] / RUN_PATH, run["bindings"]["fieldObservationsSHA256"])
             for run in runs]
    with ProcessPoolExecutor(max_workers=8) as pool:
        measured = list(pool.map(measure_run, tasks, chunksize=16))
    columns = [f"block_{i}" for i in range(BLOCKS * BLOCKS)] + ["center_y", "center_x", "total_mass", "step"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        data=np.stack([rows for rows, _ in measured]).astype(np.float32),
        columns=np.array(columns),
        run_id=np.array([run["runId"] for run in runs]),
        group=np.array([run["groupId"] for run in runs]),
        organism=np.array([run["runId"].split("-")[0] for run in runs]),
        age=np.array([run["age"] for run in runs]),
        arm=np.array([run["arm"] for run in runs]),
        dose=np.array([run["dose"] for run in runs]),
        field_sha256=np.array([digests for _, digests in measured]),
    )
    print(json.dumps({"runs": len(runs), "output": str(args.output)}))


if __name__ == "__main__":
    main()
