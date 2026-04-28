from __future__ import annotations

import hashlib
import heapq
from dataclasses import dataclass
from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class SelectionMeta:
    method: str  # "head" | "hash_sample"
    seed: int | None
    offset: int
    limit: int | None
    sample: int | None
    selected_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "seed": self.seed,
            "offset": self.offset,
            "limit": self.limit,
            "sample": self.sample,
            "selected_count": self.selected_count,
        }


def _score(seed: int, item_id: str) -> int:
    payload = f"{seed}:{item_id}".encode("utf-8", errors="strict")
    # Use a stable, platform-independent digest->int mapping.
    return int.from_bytes(hashlib.sha256(payload).digest(), byteorder="big", signed=False)


def select_items(
    items: Iterable[T],
    get_id: Callable[[T], str],
    *,
    offset: int = 0,
    limit: int | None = None,
    sample: int | None = None,
    seed: int | None = None,
) -> tuple[list[T], SelectionMeta]:
    """Select a deterministic subset from `items`.

    Semantics:
    - If `sample is None`: order items by `item_id` (lexicographic), then apply `offset`
      and `limit`.
    - If `sample is not None`: order items by `sha256(f"{seed}:{item_id}")` (ascending),
      then apply `offset`, then take `sample` items. (`limit` must be None.)

    This selection is deterministic across Python versions and independent of `random`.
    """
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit is not None and limit < 0:
        raise ValueError("limit must be >= 0")
    if sample is not None and sample <= 0:
        raise ValueError("sample must be >= 1")

    if sample is None:
        materialized: list[tuple[str, T]] = [(get_id(item), item) for item in items]
        materialized.sort(key=lambda t: t[0])
        window = materialized[offset:]
        if limit is not None:
            window = window[:limit]
        selected = [item for _, item in window]
        return (
            selected,
            SelectionMeta(
                method="head",
                seed=None,
                offset=offset,
                limit=limit,
                sample=None,
                selected_count=len(selected),
            ),
        )

    if seed is None:
        raise ValueError("--seed is required when --sample is set")
    if limit is not None:
        raise ValueError("Use --sample or --limit, not both")

    # We need items in positions [offset, offset+sample) after ordering by score.
    # Maintain a max-heap of the best k = offset + sample items.
    k = offset + sample
    heap: list[tuple[int, str, T]] = []  # (-score, item_id, item)
    for item in items:
        item_id = get_id(item)
        score = _score(seed, item_id)
        entry = (-score, item_id, item)
        if len(heap) < k:
            heapq.heappush(heap, entry)
            continue
        worst = heap[0]
        worst_score = -worst[0]
        if score < worst_score or (score == worst_score and item_id < worst[1]):
            heapq.heapreplace(heap, entry)

    # Order the top-k by (score, item_id) and slice the requested window.
    best: list[tuple[int, str, T]] = [(-neg, item_id, item) for (neg, item_id, item) in heap]
    best.sort(key=lambda t: (t[0], t[1]))
    window = best[offset : offset + sample]
    selected = [item for _, _, item in window]
    return (
        selected,
        SelectionMeta(
            method="hash_sample",
            seed=seed,
            offset=offset,
            limit=None,
            sample=sample,
            selected_count=len(selected),
        ),
    )
