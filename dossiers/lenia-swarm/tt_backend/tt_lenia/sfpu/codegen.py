"""Straight-line SFPU code for the fp32 Flow Lenia passes.

Every SFPU vector holds one value for 32 bodies, so an FFT butterfly or a stencil tap is a
fixed DST address. The generators below emit those addresses as literal `dst_reg[...]`
statements; DST vector v is vector v % 32 of tile slot v // 32. A complex value sits at
vectors (p, p + 1) as (re, im), and positions name the vector of the real part.

The emitted statements use a small C++ subset (vFloat locals, + - *, unary minus, `abs`,
`clamp`, `max0`, `exp_neg`) so that tests can execute them in numpy. Straight-line code for
a whole step does not fit the kernel binary budget, so work that repeats at a fixed DST
stride is a `Loop` whose body is written for its first iteration and which advances the DST
base between iterations.
"""

from __future__ import annotations

import cmath
import hashlib
import math
import re
from dataclasses import dataclass

import numpy as np

DST_VECTORS = 256
TILE_VECTORS = 32
GROWTH_CHUNK = 5
# INCRWC takes a signed 4-bit row increment and one SFPU vector spans two rows.
MAX_INCRWC = 3


@dataclass(frozen=True)
class Loop:
    count: int
    stride: int
    body: tuple[str, ...]


Code = list["str | Loop"]


def _repeat(count: int, stride: int, body: list[str]) -> Code:
    return list(body) if count == 1 else [Loop(count, stride, tuple(body))]


def _shift(stmt: str, offset: int) -> str:
    return re.sub(r"dst_reg\[(\d+)\]", lambda m: f"dst_reg[{int(m.group(1)) + offset}]", stmt)


def flatten(code: Code) -> list[str]:
    """Unrolled statements with absolute DST addresses, for host emulation."""
    out: list[str] = []
    for item in code:
        if isinstance(item, Loop):
            out += [_shift(st, it * item.stride) for it in range(item.count) for st in item.body]
        else:
            out.append(item)
    return out


def render(code: Code) -> str:
    """C++ body. A loop moves the DST read/write counter, whose increment field holds at most
    MAX_INCRWC vectors, and resets it to zero afterwards; outside loops the base is zero."""
    lines: list[str] = []
    for item in code:
        if not isinstance(item, Loop):
            lines.append(item)
            continue
        steps = [MAX_INCRWC] * (item.stride // MAX_INCRWC)
        if item.stride % MAX_INCRWC:
            steps.append(item.stride % MAX_INCRWC)
        lines += [
            "#pragma GCC unroll 1",
            f"for (uint32_t it = 0; it < {item.count}; it++) {{",
            *item.body,
            *(f"dst_reg += {n};" for n in steps),
            "}",
            "math::clear_dst_reg_addr();",
        ]
    return "\n".join(lines)


def bitrev(i: int, n: int) -> int:
    bits = n.bit_length() - 1
    return int(format(i, f"0{bits}b")[::-1], 2) if bits else 0


def lit(x: float) -> str:
    v = float(np.float32(x))
    if v == 0.0:
        return "0.0f"
    return f"{v!r}f"


def _twiddle(sign: int, k: int, span: int) -> complex | str | None:
    if k == 0:
        return None
    if 4 * k == span:
        return "-i" if sign < 0 else "+i"
    return cmath.exp(sign * 2j * math.pi * k / span)


@dataclass(frozen=True)
class TwiddleAt:
    """A twiddle read from DST position `pos`, conjugated when `conj`."""

    pos: int
    conj: bool


Twiddle = complex | str | TwiddleAt | None


def _rotate(dst: str, re: str, im: str, w: Twiddle) -> str:
    if isinstance(w, TwiddleAt):
        load = f"vFloat wr = dst_reg[{w.pos}]; vFloat wi = dst_reg[{w.pos + 1}]; "
        if w.conj:
            return (
                load
                + f"vFloat {dst}r = {re} * wr + {im} * wi; vFloat {dst}i = {im} * wr - {re} * wi;"
            )
        return (
            load + f"vFloat {dst}r = {re} * wr - {im} * wi; vFloat {dst}i = {re} * wi + {im} * wr;"
        )
    if w is None:
        return f"vFloat {dst}r = {re}; vFloat {dst}i = {im};"
    if w == "-i":
        return f"vFloat {dst}r = {im}; vFloat {dst}i = -{re};"
    if w == "+i":
        return f"vFloat {dst}r = -{im}; vFloat {dst}i = {re};"
    wr, wi = lit(w.real), lit(w.imag)
    return f"vFloat {dst}r = {re} * {wr} - {im} * {wi}; vFloat {dst}i = {re} * {wi} + {im} * {wr};"


def _pair(pa: int, pb: int) -> str:
    return (
        f"vFloat ar = dst_reg[{pa}]; vFloat ai = dst_reg[{pa + 1}]; "
        f"vFloat br = dst_reg[{pb}]; vFloat bi = dst_reg[{pb + 1}]; "
    )


def _dif_butterfly(pi: int, pj: int, w: Twiddle) -> str:
    return (
        "{ "
        + _pair(pi, pj)
        + f"dst_reg[{pi}] = ar + br; dst_reg[{pi + 1}] = ai + bi; "
        + "vFloat dr = ar - br; vFloat di = ai - bi; "
        + _rotate("t", "dr", "di", w)
        + f" dst_reg[{pj}] = tr; dst_reg[{pj + 1}] = ti; }}"
    )


def _dit_butterfly(pi: int, pj: int, w: Twiddle) -> str:
    return (
        "{ "
        + _pair(pi, pj)
        + _rotate("t", "br", "bi", w)
        + f" dst_reg[{pi}] = ar + tr; dst_reg[{pi + 1}] = ai + ti;"
        + f" dst_reg[{pj}] = ar - tr; dst_reg[{pj + 1}] = ai - ti; }}"
    )


def _check_contiguous(pos: list[int]) -> None:
    if any(p != pos[0] + 2 * i for i, p in enumerate(pos)):
        raise ValueError("loop-form transforms need consecutive complex positions")


def dif(pos: list[int], sign: int) -> Code:
    """Radix-2 decimation in frequency in place: natural order in, bit-reversed order out."""
    _check_contiguous(pos)
    n = len(pos)
    code: Code = []
    h = n // 2
    while h >= 1:
        body = [_dif_butterfly(pos[k], pos[k + h], _twiddle(sign, k, 2 * h)) for k in range(h)]
        code += _repeat(n // (2 * h), 4 * h, body)
        h //= 2
    return code


def dit(pos: list[int], sign: int, first_span: int = 2, last_span: int | None = None) -> Code:
    """Radix-2 decimation in time in place: bit-reversed order in, natural order out.

    Restricting the butterfly spans lets a transform that does not fit DST run its early
    stages on blocks and its late stages afterwards.
    """
    _check_contiguous(pos)
    n = len(pos)
    last = n if last_span is None else last_span
    code: Code = []
    span = first_span
    while span <= last:
        h = span // 2
        body = [_dit_butterfly(pos[k], pos[k + h], _twiddle(sign, k, span)) for k in range(h)]
        code += _repeat(n // span, 2 * span, body)
        span *= 2
    return code


def real_forward_post(pos: list[int], n_real: int) -> list[str]:
    """Turn the half-length FFT Z of a packed real row into X' = 2 rfft(row), in place.

    `pos[k]` holds Z[k] and receives X'[k] for k < n_real / 2; slot 0 packs the two real
    bins as (X'[0], X'[n_real / 2]).
    """
    m = n_real // 2
    p, q = pos[0], pos[m // 2]
    lines = [
        f"{{ vFloat zr = dst_reg[{p}]; vFloat zi = dst_reg[{p + 1}]; vFloat s = zr + zi; "
        f"vFloat d = zr - zi; dst_reg[{p}] = s + s; dst_reg[{p + 1}] = d + d; }}",
        f"{{ vFloat zr = dst_reg[{q}]; vFloat zi = -dst_reg[{q + 1}]; "
        f"dst_reg[{q}] = zr + zr; dst_reg[{q + 1}] = zi + zi; }}",
    ]
    for k in range(1, m // 2):
        pa, pb = pos[k], pos[m - k]
        lines.append(
            "{ "
            + _pair(pa, pb)
            + "vFloat er = ar + br; vFloat ei = ai - bi; vFloat orr = ai + bi; "
            + "vFloat oi = br - ar; "
            + _rotate("t", "orr", "oi", cmath.exp(-2j * math.pi * k / n_real))
            + f" dst_reg[{pa}] = er + tr; dst_reg[{pa + 1}] = ei + ti;"
            + f" dst_reg[{pb}] = er - tr; dst_reg[{pb + 1}] = ti - ei; }}"
        )
    return lines


def real_inverse_pre(pos: list[int], n_real: int) -> list[str]:
    """Inverse of `real_forward_post` in place: Z' whose half-length inverse FFT packs the row."""
    m = n_real // 2
    p, q = pos[0], pos[m // 2]
    lines = [
        f"{{ vFloat x0 = dst_reg[{p}]; vFloat xm = dst_reg[{p + 1}]; "
        f"dst_reg[{p}] = x0 + xm; dst_reg[{p + 1}] = x0 - xm; }}",
        f"{{ vFloat xr = dst_reg[{q}]; vFloat xi = -dst_reg[{q + 1}]; "
        f"dst_reg[{q}] = xr + xr; dst_reg[{q + 1}] = xi + xi; }}",
    ]
    for k in range(1, m // 2):
        pa, pb = pos[k], pos[m - k]
        lines.append(
            "{ "
            + _pair(pa, pb)
            + "vFloat er = ar + br; vFloat ei = ai - bi; vFloat dr = ar - br; "
            + "vFloat di = ai + bi; "
            + _rotate("t", "dr", "di", cmath.exp(2j * math.pi * k / n_real))
            + f" dst_reg[{pa}] = er - ti; dst_reg[{pa + 1}] = ei + tr;"
            + f" dst_reg[{pb}] = er + ti; dst_reg[{pb + 1}] = tr - ei; }}"
        )
    return lines


def _move(dst: int, src: int) -> str:
    """DST to DST assignment through a register, because sfpi has no direct dst_reg copy."""
    return f"{{ vFloat mv = dst_reg[{src}]; dst_reg[{dst}] = mv; }}"


def permute(src: dict[int, int]) -> list[str]:
    """In place `dst_new[i] = dst_old[src[i]]`; `src` must be a bijection on its keys."""
    if sorted(src) != sorted(src.values()):
        raise ValueError("permutation must map its key set onto itself")
    lines = []
    seen = set()
    for start in sorted(src):
        if start in seen or src[start] == start:
            seen.add(start)
            continue
        body = [f"vFloat t = dst_reg[{start}];"]
        i = start
        seen.add(i)
        while src[i] != start:
            body.append(_move(i, src[i]))
            i = src[i]
            seen.add(i)
        body.append(f"dst_reg[{i}] = t;")
        lines.append("{ " + " ".join(body) + " }")
    return lines


# A row of SY reals packs into SY / 2 complex values that must fit DST at once. A column of
# COLUMN complex values fits whole; a column of 2 COLUMN runs its outermost radix-2 stage in
# chunks of SPLIT positions from each half next to their SPLIT twiddles.
SIDES = (128, 256)
COLUMN = DST_VECTORS // 2
BLOCK = COLUMN // 2
SPLIT = 32


@dataclass(frozen=True)
class PassSpec:
    """Compile-time shape of one engine: everything the generated code depends on."""

    sx: int
    sy: int
    channels: int
    c0: tuple[int, ...]
    output_weights: tuple[tuple[int, ...], ...]
    dt: float
    dd: int
    sigma: float
    theta_a: float
    n: int

    def __post_init__(self) -> None:
        if self.sx not in SIDES or self.sy not in SIDES:
            raise ValueError(
                f"the SFPU engine supports tori with sides in {SIDES}, got {self.sx}x{self.sy}"
            )
        if len(self.output_weights) != self.channels:
            raise ValueError("output_weights needs one row per channel")
        if any(len(row) != len(self.c0) for row in self.output_weights):
            raise ValueError("output_weights rows need one entry per kernel")
        if any(w not in (0, 1) for row in self.output_weights for w in row):
            raise ValueError("output_weights must be a 0/1 mask")
        if 3 * len(self.c0) > 2 * TILE_VECTORS:
            raise ValueError(f"growth parameters for {len(self.c0)} kernels do not fit two tiles")
        if not 1 <= self.dd <= 8:
            raise ValueError(f"reintegration window needs 1 <= dd <= 8, got {self.dd}")
        if self.n < 1:
            raise ValueError(f"alpha exponent must be a positive integer, got {self.n}")

    @property
    def kernels(self) -> int:
        return len(self.c0)

    @property
    def half(self) -> int:
        return self.sy // 2

    @property
    def row_tiles(self) -> int:
        return self.sy // TILE_VECTORS

    @property
    def max_shift(self) -> np.float32:
        return np.float32(self.dd) - np.float32(self.sigma)

    def growth_chunks(self, c: int) -> list[list[int]]:
        ks = [k for k, w in enumerate(self.output_weights[c]) if w]
        if not ks:
            raise ValueError(f"channel {c} receives no kernels")
        return [ks[i : i + GROWTH_CHUNK] for i in range(0, len(ks), GROWTH_CHUNK)]


def p1_row(spec: PassSpec) -> list[str]:
    m = spec.half
    pos = [2 * q for q in range(m)]
    return dif(pos, -1) + real_forward_post([2 * bitrev(k, m) for k in range(m)], spec.sy)


def chunk_positions(spec: PassSpec) -> int:
    """Complex column positions in DST while pass 2 prepares, compacts or merges a column."""
    return COLUMN if spec.sx == COLUMN else 2 * SPLIT


def p2_forward(spec: PassSpec) -> Code:
    return dif([2 * p for p in range(COLUMN)], -1)


def split_twiddles(spec: PassSpec) -> np.ndarray:
    """exp(-2 pi i k / sx) for k < sx / 2 as (re, im) vectors, with the k = 0 and k = sx / 4
    entries exact so that they match the literal rotations of `dif` and `dit`."""
    n = spec.sx
    w = np.empty(n, np.float32)
    for k in range(n // 2):
        t = _twiddle(-1, k, n)
        if t is None:
            t = 1.0
        elif t == "-i":
            t = -1j
        w[2 * k], w[2 * k + 1] = np.float32(t.real), np.float32(t.imag)
    return w


def p2_split_forward(spec: PassSpec) -> Code:
    """First DIF stage of a 2 COLUMN-point column on one chunk: DST holds SPLIT positions of
    each column half and their twiddles, and the a/b outputs replace the two halves."""
    return [Loop(SPLIT, 2, (_dif_butterfly(0, 2 * SPLIT, TwiddleAt(4 * SPLIT, conj=False)),))]


def p2_split_inverse(spec: PassSpec) -> Code:
    """Last DIT stage of a 2 COLUMN-point column on the chunk layout of `p2_split_forward`."""
    return [Loop(SPLIT, 2, (_dit_butterfly(0, 2 * SPLIT, TwiddleAt(4 * SPLIT, conj=True)),))]


def p2_zero_imag(spec: PassSpec) -> Code:
    return [Loop(chunk_positions(spec), 2, ("dst_reg[1] = 0.0f;",))]


def p2_imag_to_real(spec: PassSpec) -> Code:
    return [Loop(chunk_positions(spec), 2, (f"{_move(0, 1)} dst_reg[1] = 0.0f;",))]


def p2_block(spec: PassSpec) -> list[str]:
    base = 2 * BLOCK
    mul = [
        f"{{ vFloat g = dst_reg[{base + p}]; dst_reg[{2 * p}] = dst_reg[{2 * p}] * g; "
        f"dst_reg[{2 * p + 1}] = dst_reg[{2 * p + 1}] * g; }}"
        for p in range(BLOCK)
    ]
    return mul + dit([2 * p for p in range(BLOCK)], +1)


def p2_final(spec: PassSpec) -> Code:
    return dit([2 * p for p in range(COLUMN)], +1, first_span=COLUMN)


def p2_compact(spec: PassSpec) -> list[str]:
    return [_move(j, 2 * j) for j in range(1, chunk_positions(spec))]


def p2_merge(spec: PassSpec) -> list[str]:
    n = chunk_positions(spec)
    src = {}
    for x in range(n):
        src[2 * x] = n + x
        src[2 * x + 1] = x
    return permute(src)


def p3_row(spec: PassSpec) -> list[str]:
    m = spec.half
    return real_inverse_pre([2 * bitrev(k, m) for k in range(m)], spec.sy) + dit(
        [2 * p for p in range(m)], +1
    )


PARAM_BASE = 6 * TILE_VECTORS


def growth_chunk(kernels: list[int], first: bool) -> Code:
    """Accumulate growth of up to five kernels into slot 0; potentials sit in slots 1..5.

    Each kernel's parameters stay in registers across its loop, so the work runs as three
    in-place sweeps (scaled distance, exponential, weighted sum) to bound register pressure.
    """
    code: Code = []
    for j, k in enumerate(kernels):
        pot, pm = (1 + j) * TILE_VECTORS, PARAM_BASE + 3 * k
        code += [
            f"vFloat gm{j} = dst_reg[{pm}]; vFloat gs{j} = dst_reg[{pm + 1}];",
            Loop(
                TILE_VECTORS,
                1,
                (
                    f"{{ vFloat d = (dst_reg[{pot}] - gm{j}) * gs{j}; dst_reg[{pot}] = -0.5f * d * d; }}",
                ),
            ),
        ]
    code.append(
        Loop(
            TILE_VECTORS * len(kernels),
            1,
            (f"dst_reg[{TILE_VECTORS}] = exp_neg(dst_reg[{TILE_VECTORS}]);",),
        )
    )
    for j, k in enumerate(kernels):
        pot, ph = (1 + j) * TILE_VECTORS, PARAM_BASE + 3 * k + 2
        term = "(e + e - 1.0f) * gh" + str(j)
        acc = term if first and j == 0 else f"dst_reg[0] + {term}"
        body = f"{{ vFloat e = dst_reg[{pot}]; dst_reg[0] = {acc}; }}"
        code += [f"vFloat gh{j} = dst_reg[{ph}];", Loop(TILE_VECTORS, 1, (body,))]
    return code


def matter(spec: PassSpec) -> Code:
    body = "vFloat a = dst_reg[0];"
    for c in range(1, spec.channels):
        body += f" a = a + dst_reg[{c * TILE_VECTORS}];"
    return [Loop(TILE_VECTORS, 1, (f"{{ {body} dst_reg[0] = a; }}",))]


HALO_SLOT = 6
FLOW_SLOT = 7


def _flow_cell(row: int, y: int) -> int:
    if y == -1:
        return HALO_SLOT * TILE_VECTORS + 4 * row + 1
    if y == TILE_VECTORS:
        return HALO_SLOT * TILE_VECTORS + 4 * row + 2
    return row * TILE_VECTORS + y


def _sobel(rows: int, y: int, axis: int) -> str:
    def c(r: int, yy: int) -> str:
        return f"dst_reg[{_flow_cell(rows + r, yy)}]"

    if axis == 0:
        plus = f"({c(2, y - 1)} + 2.0f * {c(2, y)} + {c(2, y + 1)})"
        minus = f"({c(0, y - 1)} + 2.0f * {c(0, y)} + {c(0, y + 1)})"
    else:
        plus = f"({c(0, y + 1)} + 2.0f * {c(1, y + 1)} + {c(2, y + 1)})"
        minus = f"({c(0, y - 1)} + 2.0f * {c(1, y - 1)} + {c(2, y - 1)})"
    return f"{plus} - {minus}"


def flow_component(spec: PassSpec, axis: int) -> Code:
    """Flow along `axis` at slot 7 and its clipped advection shift at slot 6.

    Slots 0-2 hold the affinity rows x-1..x+1, slots 3-5 the matter rows, and slot 6 the
    y halo: row r keeps cell y0-1 at vector 4r+1 and cell y0+32 at vector 4r+2.
    """
    inv_theta = lit(1.0 / spec.theta_a)

    def cell(y: int) -> str:
        q = f"dst_reg[{_flow_cell(4, y)}] * {inv_theta}"
        alpha = "q" + " * q" * (spec.n - 1)
        return (
            f"{{ vFloat q = {q}; vFloat al = clamp({alpha}, 0.0f, 1.0f); "
            f"vFloat gu = {_sobel(0, y, axis)}; vFloat ga = {_sobel(3, y, axis)}; "
            f"dst_reg[{FLOW_SLOT * TILE_VECTORS + y}] = gu * (1.0f - al) - ga * al; }}"
        )

    lim = lit(spec.max_shift)
    clip = (
        f"dst_reg[{HALO_SLOT * TILE_VECTORS}] = "
        f"clamp(dst_reg[{FLOW_SLOT * TILE_VECTORS}] * {lit(spec.dt)}, -{lim}, {lim});"
    )
    return [
        cell(0),
        cell(TILE_VECTORS - 1),
        Loop(TILE_VECTORS - 2, 1, (cell(1),)),
        Loop(TILE_VECTORS, 1, (clip,)),
    ]


SEGMENT = 16
ROWS = 4
ACC_VECTORS = ROWS * SEGMENT
WIN_MASS = 2 * TILE_VECTORS
WIN_SHIFT_X = 3 * TILE_VECTORS
WIN_SHIFT_Y = 4 * TILE_VECTORS
# Row r's weighted mass replaces the window mass (r = 0) and shift x (r = 1) once a cell has
# been read, so four rows fit next to the accumulators.
WEIGHTED = tuple(s * TILE_VECTORS for s in (2, 3, 5, 6))


def window_halo(spec: PassSpec) -> int:
    """Cells before a segment in its source window: dd rounded up to whole two-cell chunks."""
    return 2 * ((spec.dd + 1) // 2)


def source_rows(spec: PassSpec) -> int:
    return ROWS + 2 * spec.dd


def row_offsets(spec: PassSpec, k: int) -> dict[int, int]:
    """The dx of each target row of a block that source row k reaches.

    Source rows run from x0 + ROWS - 1 + dd down to x0 - dd, so every target row sees its
    dx in ascending order, as in Metal."""
    out = {}
    for r in range(ROWS):
        dx = r - (ROWS - 1) - spec.dd + k
        if -spec.dd <= dx <= spec.dd:
            out[r] = dx
    return out


REACH_CONST = "vConstFloatPrgm0"


def _sz(spec: PassSpec, offset: str, shift: str) -> str:
    """Metal's clamp((0.5 - |offset - shift|) + sigma) with 0.5 + sigma folded into one float32
    constant, which reassociates one sum (within an ulp) and saves a multiply-add per term.
    The constant sits in a programmable register because it has no fp16 immediate."""
    cmax = lit(min(1.0, 2.0 * float(np.float32(spec.sigma))))
    return f"clamp({REACH_CONST} - abs({shift} - {offset}), 0.0f, {cmax})"


def _set_reach(spec: PassSpec) -> str:
    return f"{REACH_CONST} = {lit(np.float32(spec.sigma) + np.float32(0.5))};"


def reint_weights(spec: PassSpec, k: int) -> Code:
    """Weight the clamped mass of source row k by its x overlap with each target row it reaches.

    Metal forms (mass * sz_y) * sz_x; folding sz_x in first reorders one product, which stays
    within an ulp and turns every window term into a single multiply-add. Rows are written
    from the last so that rows 1 and 0 overwrite inputs only after the cell has been read."""
    w = window_halo(spec) - spec.dd
    body = [f"vFloat m = max0(dst_reg[{WIN_MASS + w}]);", f"vFloat s = dst_reg[{WIN_SHIFT_X + w}];"]
    for r, dx in sorted(row_offsets(spec, k).items(), reverse=True):
        body.append(f"dst_reg[{WEIGHTED[r] + w}] = m * {_sz(spec, lit(dx), 's')};")
    return [_set_reach(spec), Loop(SEGMENT + 2 * spec.dd, 1, ("{ " + " ".join(body) + " }",))]


def reint_terms(spec: PassSpec, rows: tuple[int, ...]) -> Code:
    """Add one source row's terms to the target rows it reaches. Each y overlap is shared by
    those rows, and every accumulator still takes its terms in ascending dy."""
    halo = window_halo(spec)
    body = []
    for dy in range(-spec.dd, spec.dd + 1):
        j = halo - dy
        sz = _sz(spec, lit(dy), f"dst_reg[{WIN_SHIFT_Y + j}]")
        adds = " ".join(
            f"dst_reg[{SEGMENT * r}] = dst_reg[{SEGMENT * r}] + dst_reg[{WEIGHTED[r] + j}] * sz;"
            for r in rows
        )
        body.append(f"{{ vFloat sz = {sz}; {adds} }}")
    return [_set_reach(spec), Loop(SEGMENT, 1, ("{ " + " ".join(body) + " }",))]


def reint_zero() -> Code:
    return [Loop(ACC_VECTORS, 1, ("dst_reg[0] = 0.0f;",))]


def reint_scale(spec: PassSpec) -> Code:
    sigma = np.float32(spec.sigma)
    area = lit(np.float32(1.0) / (np.float32(4.0) * sigma * sigma))
    return [Loop(ACC_VECTORS, 1, (f"dst_reg[0] = dst_reg[0] * {area};",))]


def _terms_name(rows: tuple[int, ...]) -> str:
    return f"reint_terms_{rows[0]}_{rows[-1]}"


def _reint_functions(spec: PassSpec) -> list[str]:
    ks = range(source_rows(spec))
    spans = sorted({tuple(row_offsets(spec, k)) for k in ks})
    parts = [_function(f"reint_weights_{k}", reint_weights(spec, k)) for k in ks]
    parts += [_function(_terms_name(rows), reint_terms(spec, rows)) for rows in spans]
    cases = "\n".join(
        f"case {k}: reint_weights_{k}(); {_terms_name(tuple(row_offsets(spec, k)))}(); break;"
        for k in ks
    )
    parts.append(f"inline void reint_source(uint32_t k) {{\nswitch (k) {{\n{cases}\n}}\n}}\n")
    return parts


def _function(name: str, code: Code) -> str:
    # Kernels call some transforms from several places, and inlining each copy overflows the
    # per-program kernel config buffer.
    return f"__attribute__((noinline)) void {name}() {{\n{render(code)}\n}}\n"


def _growth_plan(spec: PassSpec) -> str:
    """Tables that every TRISC reads to drive the growth chunks, channel by channel."""
    chunks = [
        (c, i, ks, i == 0, i == len(spec.growth_chunks(c)) - 1)
        for c in range(spec.channels)
        for i, ks in enumerate(spec.growth_chunks(c))
    ]

    def table(name: str, values: list[str]) -> str:
        return f"constexpr uint32_t {name}[{len(values)}] = {{{', '.join(values)}}};"

    padded = [ks + [0] * (GROWTH_CHUNK - len(ks)) for _, _, ks, _, _ in chunks]
    calls = "\n".join(f"case {j}: growth_{c}_{i}(); break;" for j, (c, i, *_) in enumerate(chunks))
    return "\n".join(
        [
            f"constexpr uint32_t GROWTH_CHUNKS = {len(chunks)};",
            table("growth_first", [str(int(f)) for *_, f, _ in chunks]),
            table("growth_last", [str(int(last)) for *_, last in chunks]),
            table("growth_len", [str(len(ks)) for _, _, ks, _, _ in chunks]),
            f"constexpr uint32_t growth_kernel[{len(chunks)}][{GROWTH_CHUNK}] = {{"
            + ", ".join("{" + ", ".join(map(str, row)) + "}" for row in padded)
            + "};",
            "#ifdef TRISC_MATH",
            f"inline void growth_call(uint32_t i) {{\nswitch (i) {{\n{calls}\n}}\n}}",
            "#endif",
        ]
    )


def header(spec: PassSpec, stage: str) -> str:
    """C++ source of the generated SFPU functions for one pass.

    The functions touch DST, which only the math TRISC can address, so they sit behind
    TRISC_MATH; plan tables stay visible because the unpack and pack TRISCs loop on them too.
    """
    parts: list[str] = []
    plan = ""
    if stage == "p1":
        parts.append(_function("p1_row", p1_row(spec)))
    elif stage == "p2":
        parts += [
            _function("p2_forward", p2_forward(spec)),
            _function("p2_zero_imag", p2_zero_imag(spec)),
            _function("p2_imag_to_real", p2_imag_to_real(spec)),
            _function("p2_block", p2_block(spec)),
            _function("p2_final", p2_final(spec)),
            _function("p2_compact", p2_compact(spec)),
            _function("p2_merge", p2_merge(spec)),
        ]
        if spec.sx == 2 * COLUMN:
            parts.append(_function("p2_split_forward", p2_split_forward(spec)))
            parts.append(_function("p2_split_inverse", p2_split_inverse(spec)))
    elif stage == "p3":
        parts.append(_function("p3_row", p3_row(spec)))
        for c in range(spec.channels):
            for i, ks in enumerate(spec.growth_chunks(c)):
                parts.append(_function(f"growth_{c}_{i}", growth_chunk(ks, i == 0)))
        parts.append(_function("matter", matter(spec)))
        plan = _growth_plan(spec)
    elif stage == "p4":
        parts += [
            _function("flow_x", flow_component(spec, 0)),
            _function("flow_y", flow_component(spec, 1)),
        ]
    elif stage == "p5":
        parts += _reint_functions(spec)
        parts += [
            _function("reint_zero", reint_zero()),
            _function("reint_scale", reint_scale(spec)),
        ]
    else:
        raise ValueError(f"unknown stage {stage!r}")
    return "\n".join(["#pragma once", "#ifdef TRISC_MATH", *parts, "#endif", plan, ""])


def write_header(spec: PassSpec, stage: str, directory) -> str:
    """Write the header under a content-addressed name, because the kernel JIT cache keys on
    the include path and not on the included text."""
    text = header(spec, stage)
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    path = directory / f"{stage}_{digest}.h"
    if not path.exists():
        directory.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text)
        tmp.replace(path)
    return str(path)
