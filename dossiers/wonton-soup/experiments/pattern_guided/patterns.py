from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class PatternStream:
    labels: list[int]

    def label_at(self, iteration: int) -> int:
        if iteration < 0 or iteration >= len(self.labels):
            raise IndexError(
                f"PatternStream out of range: iteration={iteration}, size={len(self.labels)}"
            )
        return self.labels[iteration]

    @property
    def size(self) -> int:
        return len(self.labels)


def make_pattern_stream(
    kind: str,
    length: int,
    label_count: int,
    seed: int,
    *,
    freq_a: float = 0.13,
    freq_b: float = 0.031,
    phase_scale: float = 0.17,
) -> PatternStream:
    if length <= 0:
        raise ValueError("pattern length must be > 0")
    if label_count <= 0:
        raise ValueError("label_count must be > 0")

    if kind == "structured":
        labels = _structured_labels(
            length,
            label_count,
            seed,
            freq_a=freq_a,
            freq_b=freq_b,
            phase_scale=phase_scale,
        )
    elif kind == "shuffled":
        labels = _structured_labels(
            length,
            label_count,
            seed,
            freq_a=freq_a,
            freq_b=freq_b,
            phase_scale=phase_scale,
        )
        rng = random.Random(seed)
        rng.shuffle(labels)
    elif kind == "noise":
        rng = random.Random(seed)
        labels = [rng.randrange(label_count) for _ in range(length)]
    else:
        raise ValueError(f"Unknown pattern kind: {kind}")

    return PatternStream(labels=labels)


def _structured_labels(
    length: int,
    label_count: int,
    seed: int,
    *,
    freq_a: float = 0.13,
    freq_b: float = 0.031,
    phase_scale: float = 0.17,
) -> list[int]:
    labels: list[int] = []
    phase = seed * phase_scale
    for idx in range(length):
        t = idx + phase
        raw = math.sin(t * freq_a) + 0.5 * math.sin(t * freq_b)
        scaled = (raw + 1.5) / 3.0
        label = int(scaled * label_count)
        if label >= label_count:
            label = label_count - 1
        if label < 0:
            label = 0
        labels.append(label)
    return labels
