from __future__ import annotations

import numpy as np
import pytest

from lenia_tribe_overlay import rois
from lenia_tribe_overlay.tribe_fake import FakeTribeClient


@pytest.fixture(scope="module")
def bundle() -> dict[str, rois.RoiMask]:
    return rois.build_bundle()


def test_bundle_has_named_rois(bundle: dict[str, rois.RoiMask]) -> None:
    assert set(bundle) == {"sts", "lateral_ot", "v1_proxy"}


def test_masks_are_disjoint_per_pair(bundle: dict[str, rois.RoiMask]) -> None:
    for name_a, mask_a in bundle.items():
        set_a = set(mask_a.indices.tolist())
        for name_b, mask_b in bundle.items():
            if name_a >= name_b:
                continue
            overlap = set_a & set(mask_b.indices.tolist())
            assert not overlap, f"{name_a} and {name_b} overlap on {len(overlap)} vertices"


def test_masks_are_a_strict_subset_of_cortex(bundle: dict[str, rois.RoiMask]) -> None:
    for name, mask in bundle.items():
        assert 0 < mask.indices.size < rois.TRIBE_N_VERTICES, (
            f"{name} mask covers {mask.indices.size}/{rois.TRIBE_N_VERTICES} vertices"
        )
        assert mask.indices.min() >= 0
        assert mask.indices.max() < rois.TRIBE_N_VERTICES


def test_apply_diverges_from_whole_cortex_mean(bundle: dict[str, rois.RoiMask]) -> None:
    rng = np.random.default_rng(0)
    prediction = rng.normal(0.0, 1.0, size=rois.TRIBE_N_VERTICES).astype(np.float32)
    whole = float(prediction.mean())
    for name, mask in bundle.items():
        roi_mean = rois.apply(prediction, mask)
        assert roi_mean != whole, f"{name} mean equals whole-cortex mean (mask is degenerate)"


def test_apply_rejects_wrong_shape(bundle: dict[str, rois.RoiMask]) -> None:
    bad = np.zeros(1024, dtype=np.float32)
    with pytest.raises(ValueError, match="expected prediction shape"):
        rois.apply(bad, bundle["sts"])


def test_fake_client_compatible_shape() -> None:
    client = FakeTribeClient(seed=0)
    assert client.n_voxels != rois.TRIBE_N_VERTICES, (
        "FakeTribeClient mirrors a small mesh by design; ROI helpers expect the real "
        "20484-vertex output. Document the mismatch so we don't silently apply the "
        "wrong mask in tests."
    )
