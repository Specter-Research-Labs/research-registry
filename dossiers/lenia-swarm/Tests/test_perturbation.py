import hashlib

import numpy as np
import pytest

from lenia_swarm_analysis.perturbation import one_ulp_member

# Hashes of the encounter-lineage-001 ulp() reference on this field, role A (index 0).
REFERENCE = {
    1: "23ff12125b6642f72caa2e5d2313b2ed887295d997833aead5921760f5968e8c",
    2: "06f0ba2387f472c96a7f2fc20f54565ec18b0ca625a4392ff417bf731a1b5657",
    3: "e4c90d226ab84e49c5f3d1801947fe33878b231f43b8012b39a699d253ae86c6",
}


@pytest.fixture
def field() -> np.ndarray:
    a = np.random.default_rng(7).uniform(0, 1, (24, 20, 2)).astype(np.float32)
    a[a < 0.5] = 0
    return a


@pytest.mark.parametrize("seed", sorted(REFERENCE))
def test_member_matches_reference_bit_for_bit(field: np.ndarray, seed: int) -> None:
    member = one_ulp_member(field, seed, 0)
    assert hashlib.sha256(member.tobytes()).hexdigest() == REFERENCE[seed]
    changed = member != field
    assert changed.any()
    assert np.all(np.abs(member.view(np.int32) - field.view(np.int32))[changed] == 1)


def test_seed_zero_is_the_field(field: np.ndarray) -> None:
    member = one_ulp_member(field, 0, 0)
    assert member is not field and member.tobytes() == field.tobytes()


def test_role_index_changes_the_draw(field: np.ndarray) -> None:
    assert one_ulp_member(field, 1, 0).tobytes() != one_ulp_member(field, 1, 1).tobytes()
