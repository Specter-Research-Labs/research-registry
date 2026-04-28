from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class ImplementationSettings:
    mode: str
    border: str
    gradient_boundary: str
    alpha_mode: str
    kernel_profile: str
    flow_clip: str


@dataclass(frozen=True)
class BatchedConfig:
    sx: int
    sy: int
    channels: int
    nb_k: int
    dt: float
    dd: int
    sigma: float
    n: int
    theta_a: float
    border: str
    implementation: ImplementationSettings
    chem_channel: int | None
    chem_include_in_mass: bool


@dataclass(frozen=True)
class KernelParams:
    r: list[float]
    b: list[list[float]]
    w: list[list[float]]
    a: list[list[float]]
    m: list[float]
    s: list[float]
    h: list[float]
    R: float


@dataclass(frozen=True)
class CompiledKernels:
    fK: np.ndarray
    m: np.ndarray
    s: np.ndarray
    h: np.ndarray
    c0_idxs: np.ndarray
    c1_mask: np.ndarray


def _resolve_impl(raw: dict, profile: str) -> ImplementationSettings:
    mode = raw.get("mode", "paper")
    defaults = {
        "paper": ("periodic", "mass", "gaussian", "none"),
        "notebook": ("periodic", "mass", "notebook", "none"),
        "custom": (
            raw.get("gradient_boundary", "periodic"),
            raw.get("alpha_mode", "mass"),
            raw.get("kernel_profile", "gaussian"),
            raw.get("flow_clip", "none"),
        ),
    }
    gb, am, kp, fc = defaults.get(mode, defaults["paper"])
    if mode == "custom":
        gb, am, kp, fc = gb, am, kp, fc
    return ImplementationSettings(
        mode=mode,
        border=raw.get("border", "torus"),
        gradient_boundary=raw.get("gradient_boundary", gb),
        alpha_mode=raw.get("alpha_mode", am),
        kernel_profile=raw.get("kernel_profile", kp),
        flow_clip=raw.get("flow_clip", fc),
    )


def load_config(path: str | Path) -> tuple[BatchedConfig, dict]:
    raw = json.loads(Path(path).read_text())

    grid = raw["grid"]
    conn = raw["connectivity"]
    nb_k = sum(sum(row) for row in conn)

    reint = raw["reintegration"]
    flow = raw["flow"]
    impl_raw = raw.get("implementation", {"mode": "paper"})
    profile = raw.get("profile", "paper")
    impl = _resolve_impl({**impl_raw, "border": reint["border"]}, profile)

    chem_cfg = raw.get("chemotaxis")
    chem_channel = None
    chem_include = True
    if chem_cfg and chem_cfg.get("enabled"):
        chem_channel = chem_cfg["channel_index"]
        chem_include = chem_cfg.get("include_in_mass", True)

    config = BatchedConfig(
        sx=grid["sx"],
        sy=grid["sy"],
        channels=raw["channels"],
        nb_k=nb_k,
        dt=flow["dt"],
        dd=reint["dd"],
        sigma=reint["sigma"],
        n=flow["n"],
        theta_a=flow["theta_A"],
        border=reint["border"],
        implementation=impl,
        chem_channel=chem_channel,
        chem_include_in_mass=chem_include,
    )

    return config, raw


def resolve_connectivity(raw: dict) -> tuple[list[int], list[list[int]]]:
    conn = raw["connectivity"]
    channels = raw["channels"]
    c0: list[int] = []
    c1: list[list[int]] = [[] for _ in range(channels)]
    k = 0
    for src_ch, row in enumerate(conn):
        for dst_ch, count in enumerate(row):
            for _ in range(count):
                c0.append(src_ch)
                c1[dst_ch].append(k)
                k += 1
    return c0, c1


def resolve_params(raw: dict, nb_k: int, seed: int | None = None) -> KernelParams:
    params_cfg = raw["params"]
    mode = params_cfg.get("mode", "random")
    if mode == "random":
        resolved_seed = params_cfg.get("seed") if seed is None else seed
        if resolved_seed is None:
            raise ValueError("params.seed is required when params.mode='random'.")
        rng = np.random.default_rng(resolved_seed)
        ranges = params_cfg["ranges"]

        def sample(key: str) -> list[float]:
            lo, hi = ranges[key]
            return rng.uniform(lo, hi, size=nb_k).tolist()

        return KernelParams(
            r=sample("r"),
            b=[[rng.uniform(*ranges["b"])] for _ in range(nb_k)],
            w=[[rng.uniform(*ranges["w"])] for _ in range(nb_k)],
            a=[[rng.uniform(*ranges["a"])] for _ in range(nb_k)],
            m=sample("m"),
            s=sample("s"),
            h=sample("h"),
            R=rng.uniform(*ranges["R"]),
        )
    else:
        return KernelParams(
            r=params_cfg["r"],
            b=params_cfg["b"],
            w=params_cfg["w"],
            a=params_cfg["a"],
            m=params_cfg["m"],
            s=params_cfg["s"],
            h=params_cfg["h"],
            R=params_cfg["R"],
        )


def compile_kernels(params: KernelParams, config: BatchedConfig, c0: list[int], c1: list[list[int]]) -> CompiledKernels:
    sx, sy = config.sx, config.sy
    mid_x, mid_y = sx // 2, sy // 2

    coords_x = np.arange(sx, dtype=np.float32) - mid_x
    coords_y = np.arange(sy, dtype=np.float32) - mid_y
    X, Y = np.meshgrid(coords_x, coords_y, indexing="ij")
    d_base = np.sqrt(X * X + Y * Y)

    kernels = []
    for k in range(config.nb_k):
        r_k = params.r[k]
        a_k = np.array(params.a[k], dtype=np.float32)
        w_k = np.array(params.w[k], dtype=np.float32)
        b_k = np.array(params.b[k], dtype=np.float32)

        radius_base = (params.R + 15.0) if config.implementation.kernel_profile == "notebook" else params.R
        D = d_base / (radius_base * r_k)

        D_exp = D[..., np.newaxis]
        diff = D_exp - a_k
        if config.implementation.kernel_profile == "notebook":
            exponent = -(diff * diff) / w_k
        else:
            exponent = -(diff * diff) / (2.0 * w_k * w_k)
        gaussian = b_k * np.exp(exponent)
        kernel = gaussian.sum(axis=-1)

        if config.implementation.kernel_profile == "notebook":
            gate = 1.0 / (1.0 + np.exp(-(-(D - 1.0) * 10.0)))
            kernel = gate * kernel

        kernels.append(kernel)

    stacked = np.stack(kernels, axis=2)
    sum_k = stacked.sum(axis=(0, 1), keepdims=True)
    normalized = stacked / sum_k

    shifted = np.roll(np.roll(normalized, mid_x, axis=0), mid_y, axis=1)
    fK = np.fft.fft2(shifted, axes=(0, 1))
    fK = fK[np.newaxis, ...]

    c0_idxs = np.array(c0, dtype=np.int32)

    mask = np.zeros((config.channels, config.nb_k), dtype=np.float32)
    for c in range(config.channels):
        for k_idx in c1[c]:
            mask[c, k_idx] = 1.0

    return CompiledKernels(
        fK=fK,
        m=np.array(params.m, dtype=np.float32),
        s=np.array(params.s, dtype=np.float32),
        h=np.array(params.h, dtype=np.float32),
        c0_idxs=c0_idxs,
        c1_mask=mask,
    )
