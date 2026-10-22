"""Execute the generated SFPU statements in numpy float32 and compare each pass with metal.py.

The emulator runs the same straight-line code the device runs, with every vector holding
many lanes at once, so it checks the transform algebra, the layouts and the summation order
without hardware. SFPMAD fusion is the one device effect it does not model.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

from tt_lenia.numpy_ref import metal
from tt_lenia.sfpu import codegen
from tt_lenia.sfpu.codegen import PassSpec, bitrev

F32 = np.float32


def _exp_neg(x):
    x = np.asarray(x, F32)
    t = x * F32(1.44269504) + F32(12582912.0)
    nf = t - F32(12582912.0)
    r = (x - nf * F32(0.693359375)) - nf * F32(-2.12194440e-4)
    p = F32(1.0 / 5040)
    for c in (1.0 / 720, 1.0 / 120, 1.0 / 24, 1.0 / 6, 0.5, 1.0, 1.0):
        p = p * r + F32(c)
    n = t.view(np.int32) - np.int32(0x4B400000)
    out = (p.view(np.int32) + (n << 23)).view(F32)
    return np.where(x < F32(-86.0), F32(0.0), out).astype(F32)


def _clamp(x, lo, hi):
    return np.where(x < lo, F32(lo), np.where(x > hi, F32(hi), x)).astype(F32)


ENV = {
    "abs": lambda x: np.abs(x).astype(F32),
    "clamp": _clamp,
    "max0": lambda x: np.where(x < 0, F32(0.0), x).astype(F32),
    "exp_neg": _exp_neg,
}


def compile_lines(code: codegen.Code):
    stmts = []
    for line in codegen.flatten(code):
        line = re.sub(r"vFloat (\w+);", "", line).replace("vFloat ", "")
        line = line.replace("{", "").replace("}", "").replace("dst_reg[", "D[")
        line = re.sub(r"(\d)f\b", r"\1", line)
        stmts += [s.strip() for s in line.split(";") if s.strip()]
    code = compile("\n".join(stmts), "<sfpu>", "exec")

    def run(D, **consts):
        exec(code, {**ENV, **consts}, {"D": D})

    return run


class Emulator:
    """Each DST vector is a float32 array over lanes; a list keeps reads from aliasing writes."""

    def __init__(self, spec: PassSpec):
        self.spec = spec
        self.fn = {}

    def __call__(self, name: str, lines: list[str], D, **consts):
        if name not in self.fn:
            self.fn[name] = compile_lines(lines)
        self.fn[name](D, **{k: F32(v) for k, v in consts.items()})
        return D


def dst(shape) -> list:
    return [np.zeros(shape, F32) for _ in range(codegen.DST_VECTORS)]


def spec_for(size, c0, weights, dd=5) -> PassSpec:
    return PassSpec(
        sx=size,
        sy=size,
        channels=len(weights),
        c0=tuple(c0),
        output_weights=tuple(tuple(r) for r in weights),
        dt=0.2,
        dd=dd,
        sigma=0.65,
        theta_a=2.0,
        n=2,
    )


# Vectors of one half chunk of a split stage: SPLIT complex positions.
CHUNK = 2 * codegen.SPLIT


def twiddles(span: int) -> list:
    return [np.full((1, 1), v, F32) for v in codegen.split_twiddles(span)]


def split_stage(em, name, code, vecs, span):
    """One split stage of `span` complex positions over `vecs` in natural order, chunk by
    chunk as the kernels run it. Returns the chunks in DST after the stage; `vecs` receives
    them in place."""
    tw = twiddles(span)
    pad = [np.zeros((1, 1), F32)] * (codegen.DST_VECTORS - 3 * CHUNK)
    out = []
    for b in range(0, len(vecs), 2 * span):
        for q in range(0, span, CHUNK):
            a, c = b + q, b + span + q
            D = vecs[a : a + CHUNK] + vecs[c : c + CHUNK] + tw[q : q + CHUNK] + pad
            em(name, code, D)
            vecs[a : a + CHUNK], vecs[c : c + CHUNK] = D[:CHUNK], D[CHUNK : 2 * CHUNK]
            out.append(D)
    return out


def blocks(em, name, code, vecs):
    """`code` on every 128-point block of `vecs` in place."""
    n = codegen.DST_VECTORS
    for b in range(0, len(vecs), n):
        vecs[b : b + n] = em(name, code, vecs[b : b + n])
    return vecs


def row_forward(em: Emulator, row: list) -> list:
    spec = em.spec
    if not spec.row_split:
        return em("p1", codegen.p1_row(spec), row + dst(row[0].shape)[len(row) :])
    split_stage(em, "p1_split", codegen.split_forward(), row, spec.half)
    for h in range(2):
        n = codegen.DST_VECTORS
        row[n * h : n * h + n] = em(
            f"p1_half_{h}", codegen.p1_half(spec, h), row[n * h : n * h + n]
        )
    return row


def row_inverse(em: Emulator, row: list) -> list:
    spec = em.spec
    if not spec.row_split:
        return em("p3_row", codegen.p3_row(spec), row + dst(row[0].shape)[len(row) :])
    for h in range(2):
        n = codegen.DST_VECTORS
        row[n * h : n * h + n] = em(
            f"p3_half_{h}", codegen.p3_half(spec, h), row[n * h : n * h + n]
        )
    split_stage(em, "p3_split", codegen.split_inverse(), row, spec.half)
    return row


def potential(em: Emulator, mass: np.ndarray, H: np.ndarray) -> np.ndarray:
    """mass [L, sx, sy, C], H [L, sx, sy//2 + 1, K] already scaled; returns [L, sx, sy, K]."""
    spec = em.spec
    L, sx, sy, C = mass.shape
    M, K = spec.half, spec.kernels
    D = row_forward(
        em, [np.ascontiguousarray(mass[:, :, y, :].transpose(0, 2, 1)) for y in range(sy)]
    )
    S = np.empty((L, C, M, sx), np.complex64)
    for p in range(M):
        S[:, :, bitrev(p, M)] = D[2 * p] + 1j * D[2 * p + 1]

    Hv = np.empty((L, K, M + 1, sx), F32)
    for p in range(sx):
        Hv[..., p] = H[:, bitrev(p, sx), :, :].transpose(0, 2, 1)

    R = np.empty((L, K, M, sx), np.complex64)
    spans = codegen.split_spans(sx)
    # Chunks leave the last inverse stage holding w vectors from each column half.
    w = codegen.chunk_positions(spec)
    pad = [np.zeros((1, 1), F32)] * (2 * w)

    def natural(parts):
        out = [None] * (2 * sx)
        for c, D in enumerate(parts):
            out[w * c : w * c + w] = D[:w]
            out[sx + w * c : sx + w * c + w] = D[w : 2 * w]
        return out

    def forward(col, name, prep):
        col = list(col)
        if not spans:
            return em(f"fw_{name}", prep + codegen.p2_forward(spec), col)
        for i, span in enumerate(spans):
            code = (prep if i == 0 else []) + codegen.split_forward()
            split_stage(em, f"split_{name}{i}", code, col, span)
        return blocks(em, "fw", codegen.p2_forward(spec), col)

    def inverse(F, Hcol, compact):
        T = []
        for b in range(sx // codegen.BLOCK):
            Dh = F[128 * b : 128 * b + 128] + [Hcol[..., 64 * b + p] for p in range(64)]
            Dh += [np.zeros_like(F[0])] * 64
            em("p2_block", codegen.p2_block(spec), Dh)
            T += Dh[:128]
        tail = codegen.p2_compact(spec) if compact else []
        if not spans:
            return [em(f"final{compact}", codegen.p2_final(spec) + tail, T)]
        blocks(em, "final", codegen.p2_final(spec), T)
        for span in spans[:0:-1]:
            split_stage(em, "isplit", codegen.split_inverse(), T, span)
        return split_stage(em, f"isplit{compact}", codegen.split_inverse() + tail, T, sx)

    col = [None] * (2 * sx)
    for x in range(sx):
        col[2 * x] = S[:, :, 1:, x].real.copy()
        col[2 * x + 1] = S[:, :, 1:, x].imag.copy()
    for c in range(C):
        F = forward([v[:, c] for v in col], "plain", [])
        for k in [k for k in range(K) if spec.c0[k] == c]:
            out = natural(inverse(F, Hv[:, k, 1:M], False))
            for x in range(sx):
                R[:, k, 1:, x] = out[2 * x] + 1j * out[2 * x + 1]
        col0 = [None] * (2 * sx)
        for x in range(sx):
            col0[2 * x] = S[:, c, 0, x].real.copy()
            col0[2 * x + 1] = S[:, c, 0, x].imag.copy()
        FA = forward(col0, "re", codegen.p2_zero_imag(spec))
        FB = forward(col0, "im", codegen.p2_imag_to_real(spec))
        for k in [k for k in range(K) if spec.c0[k] == c]:
            ra = inverse(FA, Hv[:, k, 0], True)
            rb = inverse(FB, Hv[:, k, M], True)
            parts = [
                em(
                    "p2_merge",
                    codegen.p2_merge(spec),
                    list(rb[i][:w]) + list(ra[i][:w]) + pad[: 256 - 2 * w],
                )
                for i in range(len(ra))
            ]
            out = natural(parts)
            for x in range(sx):
                R[:, k, 0, x] = out[2 * x] + 1j * out[2 * x + 1]

    D = [None] * sy
    for ky in range(M):
        p = bitrev(ky, M)
        D[2 * p] = R[:, :, ky, :].real.copy()
        D[2 * p + 1] = R[:, :, ky, :].imag.copy()
    D = row_inverse(em, D)
    return np.stack(D[:sy], axis=-1).transpose(0, 2, 3, 1)


def affinity(em: Emulator, pot: np.ndarray, m, s, h) -> np.ndarray:
    spec = em.spec
    L, sx, sy, K = pot.shape
    T = sy // 32
    tiles = pot.reshape(L, sx, T, 32, K)
    params = [np.zeros((L, 1, 1), F32) for _ in range(64)]
    for k in range(K):
        params[3 * k] = m[:, k, None, None]
        params[3 * k + 1] = (F32(1) / s[:, k])[:, None, None]
        params[3 * k + 2] = h[:, k, None, None]
    out = np.empty((L, sx, sy, spec.channels), F32)
    zero = np.zeros((L, sx, T), F32)
    for c in range(spec.channels):
        acc = [zero] * 32
        for i, ks in enumerate(spec.growth_chunks(c)):
            D = list(acc)
            for k in ks:
                D += [tiles[..., v, k] for v in range(32)]
            D += [zero] * (32 * (codegen.GROWTH_CHUNK - len(ks)))
            D += [np.broadcast_to(p, (L, sx, T)) for p in params]
            em(f"g{c}{i}", codegen.growth_chunk(ks, i == 0), D)
            acc = D[:32]
        out[..., c] = np.stack(acc, axis=-1).reshape(L, sx, sy)
    return out


def flow(em: Emulator, u: np.ndarray, mass: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    spec = em.spec
    L, sx, sy, C = u.shape
    matter = np.zeros_like(mass[..., 0])
    for c in range(C):
        matter = matter + mass[..., c]
    T = sy // 32
    raw = np.empty((L, sx, sy, C, 2), F32)
    shift = np.empty((L, sx, sy, C, 2), F32)
    for c in range(C):
        rows = [np.roll(u[..., c], 1 - r, axis=1) for r in range(3)]
        rows += [np.roll(matter, 1 - r, axis=1) for r in range(3)]
        D = []
        for r in range(6):
            tiles = rows[r].reshape(L, sx, T, 32)
            D += [tiles[..., y] for y in range(32)]
        halo = [np.zeros((L, sx, T), F32) for _ in range(32)]
        for r in range(6):
            tiles = rows[r].reshape(L, sx, T, 32)
            halo[4 * r + 1] = np.roll(tiles[..., 31], 1, axis=2)
            halo[4 * r + 2] = np.roll(tiles[..., 0], -1, axis=2)
        for axis, name in ((0, "flow_x"), (1, "flow_y")):
            Dc = D + list(halo) + [np.zeros((L, sx, T), F32)] * 32
            em(name, codegen.flow_component(spec, axis), Dc)
            raw[..., c, axis] = np.stack(Dc[224:256], axis=-1).reshape(L, sx, sy)
            shift[..., c, axis] = np.stack(Dc[192:224], axis=-1).reshape(L, sx, sy)
    return raw, shift


def reintegrate(em: Emulator, mass: np.ndarray, shift: np.ndarray) -> np.ndarray:
    """Every (block, segment, channel) is one batch entry. Unread window vectors and scratch
    start as NaN, so a read outside the reader's window poisons the result."""
    spec = em.spec
    L, sx, sy, C = mass.shape
    R, S = codegen.ROWS, codegen.SEGMENT
    nb, ns = sx // R, sy // S
    shape = (L, nb, ns, C)
    cells = (np.arange(ns)[:, None] * S - codegen.window_halo(spec) + np.arange(32)) % sy
    valid = np.arange(32) < S + 2 * codegen.window_halo(spec)
    D = [np.full(shape, np.nan, F32) for _ in range(codegen.DST_VECTORS)]
    em("zero", codegen.reint_zero(), D)
    for k in range(codegen.source_rows(spec)):
        rows = (np.arange(nb) * R + R - 1 + spec.dd - k) % sx
        for base, field in (
            (codegen.WIN_MASS, mass),
            (codegen.WIN_SHIFT_X, shift[..., 0]),
            (codegen.WIN_SHIFT_Y, shift[..., 1]),
        ):
            win = field[:, rows][:, :, cells].transpose(0, 1, 2, 4, 3)
            for w in range(32):
                D[base + w] = win[..., w] if valid[w] else np.full(shape, np.nan, F32)
        em(f"weights{k}", codegen.reint_weights(spec, k), D)
        live = tuple(codegen.row_offsets(spec, k))
        em(f"terms{live}", codegen.reint_terms(spec, live), D)
    em("scale", codegen.reint_scale(spec), D)
    acc = np.stack(D[: codegen.ACC_VECTORS], axis=-1).reshape(L, nb, ns, C, R, S)
    return acc.transpose(0, 1, 4, 2, 5, 3).reshape(L, sx, sy, C)


@pytest.fixture(scope="module", params=codegen.SIDES)
def case(request):
    rng = np.random.default_rng(7)
    L, sx, sy, C = 4, request.param, request.param, 2
    c0 = [0] * 4 + [1] * 4
    weights = [[1, 1, 0, 1, 1, 0, 1, 1], [0, 0, 1, 0, 0, 1, 0, 0]]
    spec = spec_for(sx, c0, weights)
    K = len(c0)
    blob = np.zeros((L, sx, sy, C), F32)
    xx, yy = np.meshgrid(np.arange(sx), np.arange(sy), indexing="ij")
    for b in range(L):
        for c in range(C):
            cx, cy = rng.uniform(30, sx - 30, 2)
            blob[b, ..., c] = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 12.0**2))
    mass = (blob * rng.uniform(0.0, 1.5, blob.shape)).astype(F32)
    d = np.minimum(xx, sx - xx) ** 2 + np.minimum(yy, sy - yy) ** 2
    spectra = np.empty((L, sx, sy, K), F32)
    for b in range(L):
        for k in range(K):
            r = rng.uniform(4, 12)
            ker = np.exp(-d / (2 * r * r)) * (1 + 0.3 * np.cos(np.sqrt(d) / r * 3))
            ker /= ker.sum()
            spectra[b, ..., k] = np.fft.fft2(ker).real.astype(F32)
    m = rng.uniform(0.1, 0.3, (L, K)).astype(F32)
    s = rng.uniform(0.02, 0.1, (L, K)).astype(F32)
    h = rng.uniform(0.2, 1.0, (L, K)).astype(F32)
    return spec, mass, spectra, m, s, h


def _ref(spec, mass, spectra, m, s, h, b):
    kern = metal.MetalKernels(
        spectra=spectra[b],
        c0=np.array(spec.c0),
        output_weights=np.array(spec.output_weights, F32),
        m=m[b],
        s=s[b],
        h=h[b],
    )
    cfg = metal.MetalStepConfig(
        dt=spec.dt, dd=spec.dd, sigma=spec.sigma, theta_a=spec.theta_a, n=spec.n, clip_flow=False
    )
    return kern, cfg


def rel_rms(a, b):
    return float(
        np.sqrt(np.mean((a.astype(np.float64) - b) ** 2) / np.mean(np.square(b, dtype=np.float64)))
    )


def test_step_matches_metal_reference(case):
    spec, mass, spectra, m, s, h = case
    em = Emulator(spec)
    scale = F32(1.0 / (2 * spec.sx * spec.sy))
    H = (spectra[:, :, : spec.half + 1] * scale).astype(F32)
    pot = potential(em, mass, H)
    u = affinity(em, pot, m, s, h)
    raw, shift = flow(em, u, mass)
    new = reintegrate(em, mass, shift)
    for b in range(mass.shape[0]):
        kern, cfg = _ref(spec, mass, spectra, m, s, h, b)
        ref = metal.step(mass[b : b + 1].astype(np.float64), kern, cfg)
        ref32 = metal.step(mass[b : b + 1], kern, cfg, dtype=F32)
        errs = {
            "potential": (
                rel_rms(pot[b : b + 1], ref["potential"]),
                rel_rms(ref32["potential"], ref["potential"]),
            ),
            "affinity": (
                rel_rms(u[b : b + 1], ref["affinity"]),
                rel_rms(ref32["affinity"], ref["affinity"]),
            ),
            "flow": (rel_rms(raw[b : b + 1], ref["flow"]), rel_rms(ref32["flow"], ref["flow"])),
            "mass": (rel_rms(new[b : b + 1], ref["mass"]), rel_rms(ref32["mass"], ref["mass"])),
        }
        print(b, {k: f"{v[0]:.2e} (np32 {v[1]:.2e})" for k, v in errs.items()})
        for name, (got, np32) in errs.items():
            assert got < max(4 * np32, 1e-6), (name, got, np32)


def test_exp_neg_is_accurate():
    x = -np.linspace(0, 80, 200001).astype(F32)
    got = _exp_neg(x).astype(np.float64)
    want = np.exp(x.astype(np.float64))
    assert np.max(np.abs(got - want) / want) < 3e-7
