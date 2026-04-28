from __future__ import annotations

import pytest

from corpus.artifacts import CorpusArtifactError, compute_build_id, parse_corpus_ref


def test_parse_corpus_ref_round_trip_minimal() -> None:
    ref = parse_corpus_ref("lean:mathlib4")
    assert ref.backend == "lean"
    assert ref.corpus_id == "mathlib4"
    assert ref.build_id is None
    assert ref.derived is None
    assert ref.to_string() == "lean:mathlib4"


def test_parse_corpus_ref_parses_build_and_derived_and_normalizes_slashes() -> None:
    ref = parse_corpus_ref("lean:mathlib4@b123#valid//feasible/")
    assert ref.backend == "lean"
    assert ref.corpus_id == "mathlib4"
    assert ref.build_id == "b123"
    assert ref.derived == "valid/feasible"
    assert ref.to_string() == "lean:mathlib4@b123#valid/feasible"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "lean",  # missing ':'
        "lean:mathlib4@",  # empty build_id
        "lean:mathlib4#",  # empty derived
        "lean:mathlib4#..",  # invalid derived
        "lean:mathlib4#../x",  # traversal
        "lean:mathlib4#x/..",  # traversal
        "lean/evil:mathlib4",  # path separators
        "lean:math/evil",  # path separators
        "lean:mathlib4@..",  # invalid id
        "lean:mathlib4@b/evil",  # path separators
        "lean:mathlib4#x\\y",  # backslash
    ],
)
def test_parse_corpus_ref_rejects_invalid_refs(raw: str) -> None:
    with pytest.raises(CorpusArtifactError):
        parse_corpus_ref(raw)


def test_compute_build_id_is_deterministic_and_order_invariant() -> None:
    a = compute_build_id({"backend": "lean", "corpus_id": "mathlib4", "limit": 10})
    b = compute_build_id({"limit": 10, "corpus_id": "mathlib4", "backend": "lean"})
    c = compute_build_id({"backend": "lean", "corpus_id": "mathlib4", "limit": 11})

    assert a == b
    assert a != c
    assert len(a) == 64

