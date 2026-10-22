"""fp32 Flow Lenia on Wormhole SFPUs.

Bodies form groups of 32: lane l of every SFPU vector belongs to body l, so all arithmetic
is IEEE fp32 on the SFPU and the matrix unit, which truncates to tf32, is never used. Each
group gets an equal share of the core grid, and each pass splits its rows, columns or
blocks evenly across that share, so a small batch still uses the whole chip. The step is
five programs over the same cores; DRAM tensors between them hold one 4 KB fp32 tile per
page in DST order.

Bodies in one engine share their kernel connectivity (c0 and the c1 mask) and the flow
parameters, because those are compiled into the SFPU code. Spectra and growth parameters
are per body.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import codegen
from .codegen import TILE_VECTORS, PassSpec, bitrev

LANES = 32
PAGE_FLOATS = 1024
KERNEL_DIR = Path(__file__).parent / "kernels"
DOSSIER_ROOT = Path(__file__).resolve().parents[3]


def header_dir() -> Path:
    root = os.environ.get("SPECTER_RUNTIME_ROOT")
    return (Path(root) if root else DOSSIER_ROOT / "tmp") / "tt-sfpu"


def encode(vecs: np.ndarray) -> np.ndarray:
    """[..., 32 vectors, 32 lanes] -> [..., 1024] in the order copy_tile places them in DST."""
    lead = vecs.shape[:-2]
    return np.ascontiguousarray(
        vecs.reshape(*lead, 16, 2, LANES).swapaxes(-1, -2).reshape(*lead, PAGE_FLOATS)
    )


def decode(pages: np.ndarray) -> np.ndarray:
    lead = pages.shape[:-1]
    return pages.reshape(*lead, 16, LANES, 2).swapaxes(-1, -2).reshape(*lead, TILE_VECTORS, LANES)


@dataclass(frozen=True)
class BodyParams:
    """Per-body inputs in Metal layouts: spectra [B, sx, sy, K] (real fK), m, s, h [B, K]."""

    spectra: np.ndarray
    m: np.ndarray
    s: np.ndarray
    h: np.ndarray


class SfpuEngine:
    def __init__(
        self,
        mesh,
        spec: PassSpec,
        mass: np.ndarray,
        params: BodyParams,
        *,
        capture: bool,
    ) -> None:
        import ttnn

        self.ttnn = ttnn
        self.mesh = mesh
        self.spec = spec
        self.capture = capture
        self.devices = int(mesh.get_num_devices())
        bodies, sx, sy, channels = mass.shape
        if (sx, sy, channels) != (spec.sx, spec.sy, spec.channels):
            raise ValueError(f"mass shape {mass.shape} does not match {spec}")
        if bodies % (LANES * self.devices):
            raise ValueError(
                f"batch {bodies} must be a multiple of {LANES * self.devices} "
                f"({LANES} bodies per core on {self.devices} devices)"
            )
        self.bodies = bodies
        self.groups = bodies // (LANES * self.devices)
        grid = mesh.compute_with_storage_grid_size()
        if self.groups > grid.x * grid.y:
            raise ValueError(
                f"{self.groups} groups per device exceed the {grid.x}x{grid.y} core grid"
            )
        self.parts = grid.x * grid.y // self.groups
        self.cores = [
            ttnn.CoreCoord(i % grid.x, i // grid.x) for i in range(self.groups * self.parts)
        ]
        self.core_set = ttnn.CoreRangeSet([ttnn.CoreRange(c, c) for c in self.cores])

        g, C, K = self.groups, spec.channels, spec.kernels
        T, M, CT = spec.row_tiles, spec.half, sx // 16
        self.mass_pages = g * C * sx * T
        self.mass_a = self._upload(self._mass_pages(mass))
        self.mass_b = self._empty(self.mass_pages)
        self.h = self._upload(self._kernel_pages(params.spectra))
        self.par = self._upload(self._param_pages(params))
        self.twiddles = self._upload(self._twiddle_pages()) if sx == 2 * codegen.COLUMN else None
        self.s_spec = self._empty(g * C * M * CT)
        self.resp = self._empty(g * K * M * CT)
        self.u = self._empty(g * C * sx * T)
        self.matter = self._empty(g * sx * T)
        self.shift = self._empty(g * C * 2 * sx * T)
        self.pot = self._empty(g * sx * K * T) if capture else None
        self.flow = self._empty(g * C * 2 * sx * T) if capture else None

        hdir = header_dir()
        self.headers = {
            st: codegen.write_header(spec, st, hdir) for st in ("p1", "p2", "p3", "p4", "p5")
        }
        self.programs = [
            self._step_programs(self.mass_a, self.mass_b),
            self._step_programs(self.mass_b, self.mass_a),
        ]
        self.parity = 0

    def _upload(self, pages: np.ndarray):
        import torch

        ttnn = self.ttnn
        return ttnn.from_torch(
            torch.from_numpy(pages),
            dtype=ttnn.float32,
            layout=ttnn.ROW_MAJOR_LAYOUT,
            device=self.mesh,
            memory_config=ttnn.DRAM_MEMORY_CONFIG,
            mesh_mapper=ttnn.ShardTensorToMesh(self.mesh, dim=0),
        )

    def _empty(self, pages: int):
        ttnn = self.ttnn
        return ttnn.empty(
            [pages, PAGE_FLOATS],
            ttnn.float32,
            ttnn.ROW_MAJOR_LAYOUT,
            self.mesh,
            ttnn.DRAM_MEMORY_CONFIG,
        )

    def _download(self, tensor) -> np.ndarray:
        ttnn = self.ttnn
        return ttnn.to_torch(
            tensor, mesh_composer=ttnn.ConcatMeshToTensor(self.mesh, dim=0)
        ).numpy()

    def _mass_pages(self, mass: np.ndarray) -> np.ndarray:
        spec = self.spec
        T = spec.row_tiles
        v = mass.astype(np.float32, copy=False).reshape(
            -1, LANES, spec.sx, T, TILE_VECTORS, spec.channels
        )
        return encode(v.transpose(0, 5, 2, 3, 4, 1)).reshape(-1, PAGE_FLOATS)

    def _kernel_pages(self, spectra: np.ndarray) -> np.ndarray:
        """H[g, k, column, p] = fK[bitrev(p), column] / (2 sx sy) for columns 0..sy/2, because
        pass 2 multiplies columns in DIF output order and both transforms are unnormalized."""
        spec = self.spec
        sx, M, K = spec.sx, spec.half, spec.kernels
        if spectra.shape != (self.bodies, sx, spec.sy, K):
            raise ValueError(f"spectra shape {spectra.shape} != {(self.bodies, sx, spec.sy, K)}")
        scale = np.float32(1.0 / (2 * sx * spec.sy))
        perm = [bitrev(p, sx) for p in range(sx)]
        h = spectra[:, perm, : M + 1, :].astype(np.float32) * scale
        h = h.reshape(-1, LANES, sx // TILE_VECTORS, TILE_VECTORS, M + 1, K)
        return encode(h.transpose(0, 5, 4, 2, 3, 1)).reshape(-1, PAGE_FLOATS)

    def _twiddle_pages(self) -> np.ndarray:
        """One copy of the pass 2 split twiddles per device, every lane holding the same value."""
        w = codegen.split_twiddles(self.spec).reshape(-1, TILE_VECTORS, 1)
        pages = encode(np.broadcast_to(w, w.shape[:-1] + (LANES,)))
        return np.tile(pages, (self.devices, 1))

    def _param_pages(self, params: BodyParams) -> np.ndarray:
        K = self.spec.kernels
        for name in ("m", "s", "h"):
            if getattr(params, name).shape != (self.bodies, K):
                raise ValueError(
                    f"{name} shape {getattr(params, name).shape} != {(self.bodies, K)}"
                )
        vecs = np.zeros((self.bodies, 2 * TILE_VECTORS), np.float32)
        vecs[:, 0 : 3 * K : 3] = params.m
        vecs[:, 1 : 3 * K : 3] = np.float32(1) / params.s.astype(np.float32)
        vecs[:, 2 : 3 * K : 3] = params.h
        v = vecs.reshape(-1, LANES, 2, TILE_VECTORS)
        return encode(v.transpose(0, 2, 3, 1)).reshape(-1, PAGE_FLOATS)

    def _cbs(self, sizes: dict[int, int]):
        ttnn = self.ttnn
        return [
            ttnn.CBDescriptor(
                total_size=tiles * 4 * PAGE_FLOATS,
                core_ranges=self.core_set,
                format_descriptors=[
                    ttnn.CBFormatDescriptor(
                        buffer_index=index, data_format=ttnn.float32, page_size=4 * PAGE_FLOATS
                    )
                ],
            )
            for index, tiles in sizes.items()
        ]

    def _defines(self, stage: str) -> list[tuple[str, str]]:
        spec = self.spec
        defines = [
            ("GRID_SX", str(spec.sx)),
            ("GRID_SY", str(spec.sy)),
            ("CHANNELS", str(spec.channels)),
            ("KERNELS", str(spec.kernels)),
            ("REINT_DD", str(spec.dd)),
            ("C0_LIST", ",".join(map(str, spec.c0))),
            ("GEN_HEADER", f'"{self.headers[stage]}"'),
        ]
        if self.capture:
            defines.append(("CAPTURE", "1"))
        return defines

    def _units(self, stage: str) -> int:
        """Independent work units of a pass for one group: rows for p1, p3 and p5, columns for
        p2 and tile blocks for p4."""
        spec = self.spec
        return {
            "p1": spec.channels * spec.sx,
            "p2": spec.channels * spec.half,
            "p3": spec.sx,
            "p4": spec.channels * spec.sx * spec.row_tiles,
            "p5": spec.channels * spec.sx,
        }[stage]

    def _ranges(self, stage: str) -> list[list[int]]:
        units, parts = self._units(stage), self.parts
        return [
            [i // parts, i % parts * units // parts, (i % parts + 1) * units // parts]
            for i in range(len(self.cores))
        ]

    def _program(self, stage: str, reader, writer, cbs: dict[int, int]):
        """Runtime args are the group and the unit range, then one address per tensor, so
        capture tensors append cleanly."""
        ttnn = self.ttnn
        kd = ttnn.KernelDescriptor
        defines = self._defines(stage)
        ranges = self._ranges(stage)

        def dataflow(role: str, tensors, config):
            ct: list[int] = []
            for t in tensors:
                ct += list(ttnn.TensorAccessorArgs(t).get_compile_time_args())
            addrs = [t.buffer_address() for t in tensors]
            return kd(
                kernel_source=str(KERNEL_DIR / f"{stage}_{role}.cpp"),
                source_type=kd.SourceType.FILE_PATH,
                core_ranges=self.core_set,
                compile_time_args=ct,
                defines=defines,
                runtime_args=[(core, r + addrs) for core, r in zip(self.cores, ranges)],
                config=config,
            )

        cc = ttnn.ComputeConfigDescriptor()
        cc.math_fidelity = ttnn.MathFidelity.HiFi4
        cc.fp32_dest_acc_en = True
        cc.dst_full_sync_en = True
        cc.math_approx_mode = False
        cc.unpack_to_dest_mode = [ttnn.UnpackToDestMode.UnpackToDestFp32] * 32
        compute = kd(
            kernel_source=str(KERNEL_DIR / f"{stage}_compute.cpp"),
            source_type=kd.SourceType.FILE_PATH,
            core_ranges=self.core_set,
            compile_time_args=[],
            defines=defines,
            runtime_args=list(zip(self.cores, ranges)),
            config=cc,
        )
        kernels = [
            dataflow("reader", reader, ttnn.ReaderConfigDescriptor()),
            dataflow("writer", writer, ttnn.WriterConfigDescriptor()),
            compute,
        ]
        return ttnn.ProgramDescriptor(kernels=kernels, semaphores=[], cbs=self._cbs(cbs))

    def _step_programs(self, src, dst):
        spec = self.spec
        T, C, K = spec.row_tiles, spec.channels, spec.kernels
        CT, HT = spec.sx // 16, spec.sx // TILE_VECTORS
        cap = self.capture
        p1 = self._program("p1", [src], [self.s_spec], {0: 2 * T, 16: 2 * T})
        p2_cbs = {0: 2 * CT, 1: 4 * HT, 2: CT, 3: CT, 4: CT, 5: CT, 16: 2 * CT}
        p2_in = [self.s_spec, self.h]
        if self.twiddles is not None:
            p2_cbs |= {10: CT, 11: CT // 2}
            p2_in.append(self.twiddles)
        p2 = self._program("p2", p2_in, [self.resp], p2_cbs)
        p3_cbs = {0: 2 * T, 6: K * T, 7: 2, 8: 2, 9: C * T, 16: 2 * C, 17: 2}
        if cap:
            p3_cbs[18] = 2 * T
        p3 = self._program(
            "p3",
            [self.resp, src, self.par],
            [self.u, self.matter] + ([self.pot] if cap else []),
            p3_cbs,
        )
        p4_cbs = {0: 14, 16: 2}
        if cap:
            p4_cbs[18] = 2
        p4 = self._program(
            "p4", [self.u, self.matter], [self.shift] + ([self.flow] if cap else []), p4_cbs
        )
        p5 = self._program("p5", [src, self.shift], [dst], {0: 6 * T, 8: 2 * T + 2, 16: 2})
        tensors = {
            "p1": [src, self.s_spec],
            "p2": p2_in + [self.resp],
            "p3": [self.resp, src, self.par, self.u, self.matter] + ([self.pot] if cap else []),
            "p4": [self.u, self.matter, self.shift] + ([self.flow] if cap else []),
            "p5": [src, self.shift, dst],
        }
        return [
            (name, tensors[name], prog)
            for name, prog in zip(("p1", "p2", "p3", "p4", "p5"), (p1, p2, p3, p4, p5))
        ]

    def step(self, steps: int = 1) -> None:
        if self.capture and steps != 1:
            raise ValueError("capture engines advance one step at a time")
        for _ in range(steps):
            for _, tensors, prog in self.programs[self.parity]:
                self.ttnn.generic_op(tensors, prog)
            self.parity ^= 1

    def run_stage(self, name: str) -> None:
        """One pass of the current step, for timing; the state is undefined afterwards."""
        for stage, tensors, prog in self.programs[self.parity]:
            if stage == name:
                self.ttnn.generic_op(tensors, prog)
                return
        raise ValueError(f"unknown stage {name!r}")

    def synchronize(self) -> None:
        self.ttnn.synchronize_device(self.mesh)

    def mass(self) -> np.ndarray:
        spec = self.spec
        pages = self._download(self.mass_a if self.parity == 0 else self.mass_b)
        v = decode(pages).reshape(-1, spec.channels, spec.sx, spec.row_tiles, TILE_VECTORS, LANES)
        return v.transpose(0, 5, 2, 3, 4, 1).reshape(self.bodies, spec.sx, spec.sy, spec.channels)

    def captured(self) -> dict[str, np.ndarray]:
        """Potential, affinity and unclipped flow of the last step, in Metal layouts."""
        if not self.capture:
            raise ValueError("engine was built without capture")
        spec = self.spec
        sx, sy, T, C, K = spec.sx, spec.sy, spec.row_tiles, spec.channels, spec.kernels
        pot = decode(self._download(self.pot)).reshape(-1, sx, K, T, TILE_VECTORS, LANES)
        u = decode(self._download(self.u)).reshape(-1, C, sx, T, TILE_VECTORS, LANES)
        flw = decode(self._download(self.flow)).reshape(-1, C, 2, sx, T, TILE_VECTORS, LANES)
        return {
            "potential": pot.transpose(0, 5, 1, 3, 4, 2).reshape(self.bodies, sx, sy, K),
            "affinity": u.transpose(0, 5, 2, 3, 4, 1).reshape(self.bodies, sx, sy, C),
            "flow": flw.transpose(0, 6, 3, 4, 5, 1, 2).reshape(self.bodies, sx, sy, C, 2),
        }
