from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PatternPolicy:
    label_count: int
    top_k: int | None = None

    def choose_index(self, label: int, n: int) -> int:
        if label < 0 or label >= self.label_count:
            raise ValueError(f"label out of range: {label}")
        if n <= 0:
            raise ValueError("candidate count must be > 0")
        k = n if self.top_k is None else min(self.top_k, n)
        if k <= 0:
            raise ValueError("top_k must be > 0")
        return label % k
