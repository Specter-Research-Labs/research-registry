from __future__ import annotations

import argparse
import gzip
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass(frozen=True)
class DatasetRow:
    key: tuple[str, str, str, str]  # (run_id, theorem, variant, node_mvar_id)
    features: np.ndarray
    on_path: bool


def _iter_rows(path: Path):
    with gzip.open(path, "rt") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                yield obj


def load_node_dataset(path: Path) -> list[DatasetRow]:
    nodes: dict[tuple[str, str, str, str], DatasetRow] = {}
    for obj in _iter_rows(path):
        run_id = obj.get("run_id")
        theorem = obj.get("theorem")
        variant = obj.get("variant")
        node_mvar_id = obj.get("node_mvar_id")
        if not all(isinstance(x, str) for x in (run_id, theorem, variant, node_mvar_id)):
            continue
        feats = obj.get("goal_features")
        if not isinstance(feats, list) or not feats:
            continue
        try:
            x = np.asarray([float(v) for v in feats], dtype=np.float32)
        except (TypeError, ValueError):
            continue
        label = obj.get("node_on_solution_path")
        if not isinstance(label, bool):
            continue
        key = (run_id, theorem, variant, node_mvar_id)
        row = DatasetRow(key=key, features=x, on_path=label)
        prev = nodes.get(key)
        if prev is None:
            nodes[key] = row
            continue
        if prev.on_path != row.on_path:
            raise ValueError(f"Inconsistent node_on_solution_path for {key}")
    items = list(nodes.values())
    items.sort(key=lambda r: r.key)
    return items


def train_logreg(
    rows: list[DatasetRow],
    *,
    epochs: int,
    lr: float,
    l2: float,
) -> tuple[np.ndarray, float, dict]:
    if not rows:
        raise ValueError("Empty dataset")

    d = rows[0].features.shape[0]
    x_all = np.stack([r.features for r in rows], axis=0).astype(np.float32)
    y_all = np.asarray([1.0 if r.on_path else 0.0 for r in rows], dtype=np.float32)

    mean = x_all.mean(axis=0)
    std = x_all.std(axis=0)
    std = np.where(std > 1e-6, std, 1.0).astype(np.float32)
    x_all = (x_all - mean) / std

    w = np.zeros(d, dtype=np.float32)
    b = 0.0

    for _ in range(epochs):
        z = x_all @ w + b
        p = 1.0 / (1.0 + np.exp(-z))
        err = p - y_all
        grad_w = (x_all.T @ err) / len(rows) + (l2 * w)
        grad_b = float(err.mean())
        w -= lr * grad_w
        b -= lr * grad_b

    z = x_all @ w + b
    p = 1.0 / (1.0 + np.exp(-z))
    preds = (p >= 0.5).astype(np.float32)
    acc = float((preds == y_all).mean())
    pos_rate = float(y_all.mean())
    metrics = {"train_acc": round(acc, 4), "train_pos_rate": round(pos_rate, 4)}

    meta = {
        "scaler": {
            "mean": [float(v) for v in mean.tolist()],
            "std": [float(v) for v in std.tolist()],
        },
        "metrics": metrics,
    }
    return w, float(b), meta


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Train a simple value model from exported learning dataset"
    )
    parser.add_argument("--dataset", required=True, help="Path to dataset.jsonl.gz")
    parser.add_argument("--out", required=True, help="Output model path (.json)")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--lr", type=float, default=0.1)
    parser.add_argument("--l2", type=float, default=1e-3)
    args = parser.parse_args(argv)

    dataset_path = Path(args.dataset)
    out_path = Path(args.out)
    rows = load_node_dataset(dataset_path)
    if not rows:
        raise SystemExit("No labeled nodes found (need node_on_solution_path=true/false)")

    w, b, meta = train_logreg(rows, epochs=args.epochs, lr=args.lr, l2=args.l2)
    model = {
        "schema_version": 1,
        "model": "value_logreg",
        "feature_dim": int(w.shape[0]),
        "weights": [float(v) for v in w.tolist()],
        "bias": float(b),
        "meta": {
            "trained_at": datetime.now().isoformat(timespec="seconds"),
            "dataset_path": str(dataset_path),
            "examples": len(rows),
            "hyperparams": {"epochs": args.epochs, "lr": args.lr, "l2": args.l2},
            **meta,
        },
    }
    out_path.write_text(json.dumps(model, indent=2))
    print(f"Wrote: {out_path}")

