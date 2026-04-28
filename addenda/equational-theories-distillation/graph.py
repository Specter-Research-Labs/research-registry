import json
from dataclasses import dataclass
from pathlib import Path

TRUE_STATUSES = frozenset({1, 3, 5, 7})
FALSE_STATUSES = frozenset({0, 2, 4, 6})
PROOF_STATUSES = frozenset({2, 3, 6, 7})
CONJECTURE_STATUSES = frozenset({0, 1, 4, 5})
UNKNOWN_STATUS = 8

STATUS_NAMES = {
    0: "explicit_conjecture_false",
    1: "explicit_conjecture_true",
    2: "explicit_proof_false",
    3: "explicit_proof_true",
    4: "implicit_conjecture_false",
    5: "implicit_conjecture_true",
    6: "implicit_proof_false",
    7: "implicit_proof_true",
    8: "unknown",
}


@dataclass(frozen=True)
class ImplicationGraph:
    law_count: int
    statuses: bytes
    equivalence_classes: tuple[tuple[int, ...], ...]

    def status(self, source_id: int, target_id: int) -> int:
        if source_id < 1 or source_id > self.law_count:
            raise IndexError(f"source_id out of range: {source_id}")
        if target_id < 1 or target_id > self.law_count:
            raise IndexError(f"target_id out of range: {target_id}")
        offset = (source_id - 1) * self.law_count + (target_id - 1)
        return self.statuses[offset]

    def truth(self, source_id: int, target_id: int) -> bool | None:
        status = self.status(source_id, target_id)
        if status in TRUE_STATUSES:
            return True
        if status in FALSE_STATUSES:
            return False
        return None

    def status_name(self, source_id: int, target_id: int) -> str:
        return STATUS_NAMES[self.status(source_id, target_id)]


def decode_rle(rle_encoded_array: list[int], expected_length: int) -> bytes:
    decoded = bytearray(expected_length)
    cursor = 0
    for index in range(0, len(rle_encoded_array), 2):
        value = rle_encoded_array[index]
        count = rle_encoded_array[index + 1]
        decoded[cursor : cursor + count] = bytes((value,)) * count
        cursor += count
    if cursor != expected_length:
        raise ValueError(f"decoded length mismatch: expected {expected_length}, got {cursor}")
    return bytes(decoded)


def load_graph(path: Path, law_count: int) -> ImplicationGraph:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = {"equivalence_classes", "full_entries", "rle_encoded_array"}
    missing = expected_keys - payload.keys()
    if missing:
        joined = ", ".join(sorted(missing))
        raise ValueError(f"graph.json missing keys: {joined}")
    statuses = decode_rle(payload["rle_encoded_array"], law_count * law_count)
    equivalence_classes = tuple(tuple(item) for item in payload["equivalence_classes"])
    return ImplicationGraph(
        law_count=law_count,
        statuses=statuses,
        equivalence_classes=equivalence_classes,
    )


def status_counts(graph: ImplicationGraph) -> dict[str, int]:
    counts: dict[str, int] = {}
    for status in graph.statuses:
        name = STATUS_NAMES[status]
        counts[name] = counts.get(name, 0) + 1
    return counts
