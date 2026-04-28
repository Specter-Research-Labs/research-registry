from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .config import CompiledKernels, KernelParams


def load_reference_arrays(ref_dir: str | Path) -> dict[str, np.ndarray]:
    path = Path(ref_dir)
    arrays: dict[str, np.ndarray] = {}
    for file_path in path.glob("*.npy"):
        arrays[file_path.stem] = np.load(file_path)
    return arrays


def load_reference_manifest(ref_dir: str | Path) -> dict | None:
    path = Path(ref_dir) / "reference_manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_initial_mass_from_reference(ref: dict[str, np.ndarray]) -> np.ndarray:
    if "mass_in" not in ref:
        raise KeyError("Reference bundle is missing mass_in.npy.")
    return ref["mass_in"].astype(np.float32, copy=False)


def load_kernels_from_reference(ref: dict[str, np.ndarray]) -> CompiledKernels:
    required = [
        "kernel_fK_re",
        "kernel_fK_im",
        "kernel_m",
        "kernel_s",
        "kernel_h",
        "kernel_c0",
        "kernel_c1_mask",
    ]
    missing = [name for name in required if name not in ref]
    if missing:
        joined = ", ".join(sorted(missing))
        raise KeyError(f"Reference bundle is missing required kernel arrays: {joined}")

    fK = ref["kernel_fK_re"] + 1j * ref["kernel_fK_im"]
    return CompiledKernels(
        fK=fK,
        m=ref["kernel_m"].astype(np.float32, copy=False),
        s=ref["kernel_s"].astype(np.float32, copy=False),
        h=ref["kernel_h"].astype(np.float32, copy=False),
        c0_idxs=ref["kernel_c0"].astype(np.int32, copy=False),
        c1_mask=ref["kernel_c1_mask"].astype(np.float32, copy=False),
    )


def load_resolved_params(path: str | Path) -> tuple[int | None, KernelParams]:
    raw = json.loads(Path(path).read_text())
    seed = raw.get("seed")
    params_raw = raw.get("params", raw)
    return seed, KernelParams(
        r=params_raw["r"],
        b=params_raw["b"],
        w=params_raw["w"],
        a=params_raw["a"],
        m=params_raw["m"],
        s=params_raw["s"],
        h=params_raw["h"],
        R=params_raw["R"],
    )
