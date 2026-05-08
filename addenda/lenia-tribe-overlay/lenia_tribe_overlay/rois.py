from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import paths

FSAVERAGE5_PER_HEMI = 10242
TRIBE_N_VERTICES = 2 * FSAVERAGE5_PER_HEMI

ROI_BUNDLES: dict[str, tuple[str, ...]] = {
    "sts": ("S_temporal_sup",),
    "lateral_ot": ("S_oc-temp_lat", "G_occipital_middle", "G_oc-temp_lat-fusifor"),
    "v1_proxy": ("S_calcarine", "G_cuneus", "Pole_occipital"),
}


@dataclass(frozen=True)
class RoiMask:
    """Boolean mask over TRIBE's 20484-vertex output (fsaverage5, [L|R] stacked).

    invariant: TRIBE concatenates left then right hemisphere (see tribev2.utils_fmri
    L226 `np.vstack([left, right])`); the mask follows the same convention so
    `prediction[mask.indices]` selects the named region.
    """

    name: str
    indices: np.ndarray
    label_names: tuple[str, ...]


def _build_destrieux_mask(name: str, label_names: tuple[str, ...]) -> RoiMask:
    from nilearn import datasets

    atlas = datasets.fetch_atlas_surf_destrieux()
    label_to_id = {lbl: i for i, lbl in enumerate(atlas["labels"])}
    missing = [lbl for lbl in label_names if lbl not in label_to_id]
    if missing:
        raise KeyError(
            f"Destrieux labels not found: {missing}. "
            f"Available labels: {sorted(atlas['labels'])}"
        )
    target_ids = {label_to_id[lbl] for lbl in label_names}
    map_lh = np.asarray(atlas["map_left"], dtype=np.int32)
    map_rh = np.asarray(atlas["map_right"], dtype=np.int32)
    if map_lh.shape != (FSAVERAGE5_PER_HEMI,) or map_rh.shape != (FSAVERAGE5_PER_HEMI,):
        raise ValueError(
            f"Destrieux atlas not on fsaverage5: got lh={map_lh.shape}, rh={map_rh.shape}"
        )
    parcellation = np.concatenate([map_lh, map_rh])
    bool_mask = np.isin(parcellation, list(target_ids))
    indices = np.flatnonzero(bool_mask).astype(np.int32)
    if indices.size == 0:
        raise ValueError(f"ROI {name!r} produced an empty mask from labels {label_names}")
    return RoiMask(name=name, indices=indices, label_names=label_names)


def _cache_path() -> Path:
    return paths.ensure(paths.runtime_root() / "rois") / "destrieux_fsaverage5.npz"


def build_bundle(force_rebuild: bool = False) -> dict[str, RoiMask]:
    """Build (or load) the curated Destrieux bundle on TRIBE's output mesh."""
    cache = _cache_path()
    if cache.exists() and not force_rebuild:
        loaded = np.load(cache, allow_pickle=False)
        masks: dict[str, RoiMask] = {}
        for name in ROI_BUNDLES:
            indices = loaded[f"{name}__indices"]
            label_arr = loaded[f"{name}__labels"]
            label_names = tuple(str(s) for s in label_arr)
            masks[name] = RoiMask(name=name, indices=indices, label_names=label_names)
        return masks

    masks = {name: _build_destrieux_mask(name, labels) for name, labels in ROI_BUNDLES.items()}
    payload: dict[str, np.ndarray] = {}
    for name, mask in masks.items():
        payload[f"{name}__indices"] = mask.indices
        payload[f"{name}__labels"] = np.asarray(mask.label_names)
    np.savez(cache, **payload)  # ty: ignore[invalid-argument-type]
    return masks


def apply(prediction_voxels: np.ndarray, mask: RoiMask) -> float:
    """Mean activation inside `mask` for a TRIBE prediction (shape (20484,))."""
    if prediction_voxels.shape != (TRIBE_N_VERTICES,):
        raise ValueError(
            f"expected prediction shape ({TRIBE_N_VERTICES},); got {prediction_voxels.shape}"
        )
    return float(prediction_voxels[mask.indices].mean())
