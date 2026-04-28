from __future__ import annotations

import random
from typing import Mapping, TypeVar


T = TypeVar("T")


def sample_weighted(weights: Mapping[T, float], rng: random.Random) -> T:
    total = sum(float(weight) for weight in weights.values())
    if total <= 0:
        raise ValueError("weights must have positive total mass")

    threshold = rng.random() * total
    cumulative = 0.0
    last_item: T | None = None
    for item, weight in weights.items():
        cumulative += float(weight)
        last_item = item
        if threshold <= cumulative:
            return item
    if last_item is None:
        raise RuntimeError("weighted sampling failed")
    return last_item
