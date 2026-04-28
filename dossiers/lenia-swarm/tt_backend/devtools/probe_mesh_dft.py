"""Probe TTNN mesh matmul patterns needed for a distributed DFT front half.

This is a hardware-facing bringup tool, not the user-facing Lenia CLI path. It
keeps mesh experiments small and explicit before we wire them into the runtime.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tt_lenia.device import (
    apply_tt_runtime_env,
    close_ttnn_device,
    open_ttnn_device,
    parse_mesh_shape,
    restore_tt_runtime_env,
)
from tt_lenia.stages.fft import DFTMatmul, TTNNMeshDFTMatmul, _safe_deallocate


@dataclass(frozen=True)
class ProbeResult:
    name: str
    size: int
    mesh_shape: tuple[int, int]
    warmup: int
    runs: int
    mean_elapsed_ms: float
    pcc: float
    max_abs_diff: float
    passed: bool


def _pcc(actual: np.ndarray, expected: np.ndarray) -> float:
    actual_flat = actual.astype(np.float32, copy=False).reshape(-1)
    expected_flat = expected.astype(np.float32, copy=False).reshape(-1)
    actual_centered = actual_flat - actual_flat.mean()
    expected_centered = expected_flat - expected_flat.mean()
    denom = float(np.linalg.norm(actual_centered) * np.linalg.norm(expected_centered))
    if denom == 0.0:
        return 1.0 if np.array_equal(actual_flat, expected_flat) else 0.0
    return float(np.dot(actual_centered, expected_centered) / denom)


def _metrics(actual: np.ndarray, expected: np.ndarray) -> tuple[float, float]:
    if actual.shape != expected.shape:
        raise ValueError(f"Shape mismatch: actual={actual.shape} expected={expected.shape}")
    return _pcc(actual, expected), float(np.max(np.abs(actual.astype(np.float32) - expected.astype(np.float32))))


def _torch_inputs(size: int, seed: int):
    import torch

    generator = torch.Generator().manual_seed(seed)
    a = torch.randn((size, size), dtype=torch.float32, generator=generator).bfloat16()
    b = torch.randn((size, size), dtype=torch.float32, generator=generator).bfloat16()
    expected = a.float() @ b.float()
    return a, b, expected


def _real_dft_inputs(size: int, seed: int):
    import torch

    generator = torch.Generator().manual_seed(seed)
    x = torch.randn((size, size), dtype=torch.float32, generator=generator).bfloat16()
    coords = torch.arange(size, dtype=torch.float32)
    phase = 2.0 * torch.pi * torch.outer(coords, coords) / float(size)
    w = torch.cos(phase).bfloat16()
    expected = w.float() @ x.float() @ w.float().T
    return x, w, expected


def _complex_dft_inputs(size: int, seed: int, planes: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    shape = (size, size) if planes == 1 else (planes, size, size)
    x_re = rng.standard_normal(shape).astype(np.float32)
    x_im = rng.standard_normal(shape).astype(np.float32)
    expected_re, expected_im = DFTMatmul(size).forward_2d(x_re, x_im)
    return x_re, x_im, expected_re, expected_im


def _to_mesh(tensor, *, mesh, mapper):
    import ttnn

    return ttnn.from_torch(
        tensor,
        dtype=ttnn.bfloat16,
        layout=ttnn.TILE_LAYOUT,
        device=mesh,
        memory_config=ttnn.DRAM_MEMORY_CONFIG,
        mesh_mapper=mapper,
    )


def _mesh_shape_tuple(mesh_shape) -> tuple[int, int]:
    return int(mesh_shape[0]), int(mesh_shape[1])


def _sync(device) -> None:
    import ttnn

    ttnn.synchronize_device(device)


def probe_row_sharded_matmul(
    *,
    mesh,
    size: int,
    seed: int,
    warmup: int,
    runs: int,
    min_pcc: float,
) -> ProbeResult:
    """Probe A[M,K] row-sharded, B[K,N] replicated, C[M,N] row-sharded."""
    import ttnn

    mesh_shape = _mesh_shape_tuple(mesh.shape)
    a, b, expected_torch = _torch_inputs(size, seed)
    a_tt = b_tt = out_tt = None
    try:
        a_tt = _to_mesh(a, mesh=mesh, mapper=ttnn.ShardTensorToMesh(mesh, dim=0))
        b_tt = _to_mesh(b, mesh=mesh, mapper=ttnn.ReplicateTensorToMesh(mesh))
        for _ in range(warmup):
            warmup_out = ttnn.matmul(a_tt, b_tt)
            _sync(mesh)
            _safe_deallocate(warmup_out)

        started_at = time.perf_counter()
        for _ in range(runs):
            previous_out = out_tt
            out_tt = ttnn.matmul(a_tt, b_tt)
            _sync(mesh)
            _safe_deallocate(previous_out)
        mean_elapsed_ms = (time.perf_counter() - started_at) * 1000.0 / float(runs)
        actual = ttnn.to_torch(out_tt, mesh_composer=ttnn.ConcatMeshToTensor(mesh, dim=0)).float().numpy()
    finally:
        _safe_deallocate(a_tt, b_tt, out_tt)

    expected = expected_torch.numpy()
    pcc, max_abs_diff = _metrics(actual, expected)
    return ProbeResult(
        name="row-sharded-matmul",
        size=size,
        mesh_shape=mesh_shape,
        warmup=warmup,
        runs=runs,
        mean_elapsed_ms=mean_elapsed_ms,
        pcc=pcc,
        max_abs_diff=max_abs_diff,
        passed=pcc >= min_pcc,
    )


def probe_k_sharded_matmul_all_reduce(
    *,
    mesh,
    size: int,
    seed: int,
    warmup: int,
    runs: int,
    min_pcc: float,
) -> ProbeResult:
    """Probe A[M,K] K-sharded, B[K,N] K-sharded, C[M,N] all-reduced."""
    import ttnn

    mesh_shape = _mesh_shape_tuple(mesh.shape)
    a, b, expected_torch = _torch_inputs(size, seed)
    a_tt = b_tt = partial_tt = reduced_tt = None
    try:
        a_tt = _to_mesh(a, mesh=mesh, mapper=ttnn.ShardTensorToMesh(mesh, dim=1))
        b_tt = _to_mesh(b, mesh=mesh, mapper=ttnn.ShardTensorToMesh(mesh, dim=0))
        for _ in range(warmup):
            warmup_partial = ttnn.matmul(a_tt, b_tt)
            warmup_reduced = ttnn.all_reduce(warmup_partial)
            _sync(mesh)
            _safe_deallocate(warmup_partial, warmup_reduced)

        started_at = time.perf_counter()
        for _ in range(runs):
            previous_partial = partial_tt
            previous_reduced = reduced_tt
            partial_tt = ttnn.matmul(a_tt, b_tt)
            reduced_tt = ttnn.all_reduce(partial_tt)
            _sync(mesh)
            _safe_deallocate(previous_partial, previous_reduced)
        mean_elapsed_ms = (time.perf_counter() - started_at) * 1000.0 / float(runs)
        gathered = ttnn.to_torch(
            reduced_tt,
            mesh_composer=ttnn.ConcatMeshToTensor(mesh, dim=0),
        ).float().numpy()
    finally:
        _safe_deallocate(a_tt, b_tt, partial_tt, reduced_tt)

    expected = expected_torch.numpy()
    mesh_size = mesh_shape[0] * mesh_shape[1]
    if gathered.shape == expected.shape:
        actual = gathered
    elif gathered.shape[0] == expected.shape[0] * mesh_size and gathered.shape[1:] == expected.shape[1:]:
        # all_reduce produces a replicated logical result in the upstream
        # examples; concatenating along dim 0 exposes one copy per mesh device.
        actual = gathered[: expected.shape[0], :]
    else:
        raise ValueError(f"Unexpected all_reduce gathered shape {gathered.shape} for expected {expected.shape}.")

    pcc, max_abs_diff = _metrics(actual, expected)
    return ProbeResult(
        name="k-sharded-matmul-all-reduce",
        size=size,
        mesh_shape=mesh_shape,
        warmup=warmup,
        runs=runs,
        mean_elapsed_ms=mean_elapsed_ms,
        pcc=pcc,
        max_abs_diff=max_abs_diff,
        passed=pcc >= min_pcc,
    )


def _replicated_result_to_numpy(tensor, *, mesh, expected_shape: tuple[int, ...]) -> np.ndarray:
    import ttnn

    mesh_shape = _mesh_shape_tuple(mesh.shape)
    mesh_size = mesh_shape[0] * mesh_shape[1]
    gathered = ttnn.to_torch(
        tensor,
        mesh_composer=ttnn.ConcatMeshToTensor(mesh, dim=0),
    ).float().numpy()
    if gathered.shape == expected_shape:
        return gathered
    if gathered.shape[0] == expected_shape[0] * mesh_size and gathered.shape[1:] == expected_shape[1:]:
        return gathered[: expected_shape[0], :]
    raise ValueError(f"Unexpected replicated gathered shape {gathered.shape} for expected {expected_shape}.")


def probe_real_dft_2d(
    *,
    mesh,
    size: int,
    seed: int,
    warmup: int,
    runs: int,
    min_pcc: float,
) -> ProbeResult:
    """Probe the mesh pattern for one real separable 2D DFT component."""
    import ttnn

    mesh_shape = _mesh_shape_tuple(mesh.shape)
    x, w, expected_torch = _real_dft_inputs(size, seed)
    x_tt = wt_tt = w_cols_tt = t1_tt = partial_tt = reduced_tt = None
    try:
        x_tt = _to_mesh(x, mesh=mesh, mapper=ttnn.ShardTensorToMesh(mesh, dim=0))
        wt_tt = _to_mesh(w.T, mesh=mesh, mapper=ttnn.ReplicateTensorToMesh(mesh))
        w_cols_tt = _to_mesh(w, mesh=mesh, mapper=ttnn.ShardTensorToMesh(mesh, dim=1))

        for _ in range(warmup):
            warmup_t1 = ttnn.matmul(x_tt, wt_tt)
            warmup_partial = ttnn.matmul(w_cols_tt, warmup_t1)
            warmup_reduced = ttnn.all_reduce(warmup_partial)
            _sync(mesh)
            _safe_deallocate(warmup_t1, warmup_partial, warmup_reduced)

        started_at = time.perf_counter()
        for _ in range(runs):
            previous_t1 = t1_tt
            previous_partial = partial_tt
            previous_reduced = reduced_tt
            t1_tt = ttnn.matmul(x_tt, wt_tt)
            partial_tt = ttnn.matmul(w_cols_tt, t1_tt)
            reduced_tt = ttnn.all_reduce(partial_tt)
            _sync(mesh)
            _safe_deallocate(previous_t1, previous_partial, previous_reduced)
        mean_elapsed_ms = (time.perf_counter() - started_at) * 1000.0 / float(runs)
        actual = _replicated_result_to_numpy(reduced_tt, mesh=mesh, expected_shape=tuple(expected_torch.shape))
    finally:
        _safe_deallocate(x_tt, wt_tt, w_cols_tt, t1_tt, partial_tt, reduced_tt)

    expected = expected_torch.numpy()
    pcc, max_abs_diff = _metrics(actual, expected)
    return ProbeResult(
        name="real-dft-2d-row-k-all-reduce",
        size=size,
        mesh_shape=mesh_shape,
        warmup=warmup,
        runs=runs,
        mean_elapsed_ms=mean_elapsed_ms,
        pcc=pcc,
        max_abs_diff=max_abs_diff,
        passed=pcc >= min_pcc,
    )


def probe_complex_dft_2d(
    *,
    mesh,
    size: int,
    seed: int,
    planes: int,
    warmup: int,
    runs: int,
    min_pcc: float,
) -> ProbeResult:
    """Probe the reusable complex mesh DFT primitive."""
    mesh_shape = _mesh_shape_tuple(mesh.shape)
    x_re, x_im, expected_re, expected_im = _complex_dft_inputs(size, seed, planes)
    mesh_dft = TTNNMeshDFTMatmul(size, mesh)
    x_re_tt = x_im_tt = out_re_tt = out_im_tt = None
    try:
        x_re_tt = mesh_dft.row_sharded_from_numpy(x_re)
        x_im_tt = mesh_dft.row_sharded_from_numpy(x_im)
        for _ in range(warmup):
            warmup_re, warmup_im = mesh_dft.forward_2d(x_re_tt, x_im_tt)
            _sync(mesh)
            _safe_deallocate(warmup_re, warmup_im)

        started_at = time.perf_counter()
        for _ in range(runs):
            previous_re = out_re_tt
            previous_im = out_im_tt
            out_re_tt, out_im_tt = mesh_dft.forward_2d(x_re_tt, x_im_tt)
            _sync(mesh)
            _safe_deallocate(previous_re, previous_im)
        mean_elapsed_ms = (time.perf_counter() - started_at) * 1000.0 / float(runs)
        actual_re = mesh_dft.replicated_to_numpy(out_re_tt)
        actual_im = mesh_dft.replicated_to_numpy(out_im_tt)
    finally:
        _safe_deallocate(x_re_tt, x_im_tt, out_re_tt, out_im_tt)
        mesh_dft.close()

    actual = np.stack([actual_re, actual_im], axis=0)
    expected = np.stack([expected_re, expected_im], axis=0)
    pcc, max_abs_diff = _metrics(actual, expected)
    return ProbeResult(
        name=f"complex-dft-2d-row-k-all-reduce-p{planes}",
        size=size,
        mesh_shape=mesh_shape,
        warmup=warmup,
        runs=runs,
        mean_elapsed_ms=mean_elapsed_ms,
        pcc=pcc,
        max_abs_diff=max_abs_diff,
        passed=pcc >= min_pcc,
    )


def probe_partitioned_complex_dft_2d(
    *,
    mesh,
    size: int,
    seed: int,
    planes: int,
    warmup: int,
    runs: int,
    min_pcc: float,
) -> ProbeResult:
    """Probe runtime-relevant replicated input -> mesh_partition -> DFT."""
    mesh_shape = _mesh_shape_tuple(mesh.shape)
    x_re, x_im, expected_re, expected_im = _complex_dft_inputs(size, seed, planes)
    mesh_dft = TTNNMeshDFTMatmul(size, mesh)
    x_re_full = x_im_full = x_re_tt = x_im_tt = out_re_tt = out_im_tt = None
    try:
        x_re_full = mesh_dft.replicated_from_numpy(x_re)
        x_im_full = mesh_dft.replicated_from_numpy(x_im)
        for _ in range(warmup):
            warm_re = mesh_dft.row_shard_replicated(x_re_full)
            warm_im = mesh_dft.row_shard_replicated(x_im_full)
            warmup_re, warmup_im = mesh_dft.forward_2d(warm_re, warm_im)
            _sync(mesh)
            _safe_deallocate(warm_re, warm_im, warmup_re, warmup_im)

        started_at = time.perf_counter()
        for _ in range(runs):
            previous_re = out_re_tt
            previous_im = out_im_tt
            previous_x_re = x_re_tt
            previous_x_im = x_im_tt
            x_re_tt = mesh_dft.row_shard_replicated(x_re_full)
            x_im_tt = mesh_dft.row_shard_replicated(x_im_full)
            out_re_tt, out_im_tt = mesh_dft.forward_2d(x_re_tt, x_im_tt)
            _sync(mesh)
            _safe_deallocate(previous_re, previous_im, previous_x_re, previous_x_im)
        mean_elapsed_ms = (time.perf_counter() - started_at) * 1000.0 / float(runs)
        actual_re = mesh_dft.replicated_to_numpy(out_re_tt)
        actual_im = mesh_dft.replicated_to_numpy(out_im_tt)
    finally:
        _safe_deallocate(x_re_full, x_im_full, x_re_tt, x_im_tt, out_re_tt, out_im_tt)
        mesh_dft.close()

    actual = np.stack([actual_re, actual_im], axis=0)
    expected = np.stack([expected_re, expected_im], axis=0)
    pcc, max_abs_diff = _metrics(actual, expected)
    return ProbeResult(
        name=f"partitioned-complex-dft-2d-p{planes}",
        size=size,
        mesh_shape=mesh_shape,
        warmup=warmup,
        runs=runs,
        mean_elapsed_ms=mean_elapsed_ms,
        pcc=pcc,
        max_abs_diff=max_abs_diff,
        passed=pcc >= min_pcc,
    )


def _print_result(result: ProbeResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(
        f"{status} {result.name}: size={result.size}, mesh={result.mesh_shape[0]}x{result.mesh_shape[1]}, "
        f"mean={result.mean_elapsed_ms:.2f}ms/run, warmup={result.warmup}, runs={result.runs}, "
        f"pcc={result.pcc:.6f}, max_abs_diff={result.max_abs_diff:.4f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe TTNN mesh matmul patterns for Lenia DFT")
    parser.add_argument("--size", type=int, default=256, help="Square matrix size; must be tile- and mesh-aligned.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device-id", type=int, default=0)
    parser.add_argument("--tt-visible-devices", default=None)
    parser.add_argument("--mesh-shape", required=True, help="TTNN mesh shape as rows,cols.")
    parser.add_argument(
        "--mode",
        choices=["row", "k", "dft", "complex-dft", "partition-complex-dft", "both", "all"],
        default="all",
        help=(
            "row=row-sharded matmul, k=K-sharded matmul plus all_reduce, "
            "dft=one real separable 2D DFT, complex-dft=reusable complex DFT primitive, "
            "partition-complex-dft=replicated input plus mesh_partition before complex DFT."
        ),
    )
    parser.add_argument("--min-pcc", type=float, default=0.99)
    parser.add_argument("--warmup", type=int, default=1, help="Resident warmup runs before timing.")
    parser.add_argument("--runs", type=int, default=3, help="Resident timed runs.")
    parser.add_argument("--planes", type=int, default=1, help="Number of batched planes for complex DFT probe modes.")
    parser.add_argument("--summary-json", type=Path, default=None)
    args = parser.parse_args()

    mesh_shape = parse_mesh_shape(args.mesh_shape)
    if mesh_shape is None:
        parser.error("--mesh-shape is required.")
    mesh_size = mesh_shape[0] * mesh_shape[1]
    if args.size % 32 != 0:
        parser.error("--size must be divisible by 32.")
    if args.size % mesh_size != 0:
        parser.error(f"--size must be divisible by mesh size {mesh_size}.")
    if args.warmup < 0:
        parser.error("--warmup must be >= 0.")
    if args.runs <= 0:
        parser.error("--runs must be > 0.")
    if args.planes <= 0:
        parser.error("--planes must be > 0.")

    device = None
    previous_env = apply_tt_runtime_env(visible_device=args.tt_visible_devices)
    try:
        device = open_ttnn_device(device_id=args.device_id, mesh_shape=mesh_shape)
        results: list[ProbeResult] = []
        if args.mode in {"row", "both", "all"}:
            results.append(
                probe_row_sharded_matmul(
                    mesh=device,
                    size=args.size,
                    seed=args.seed,
                    warmup=args.warmup,
                    runs=args.runs,
                    min_pcc=args.min_pcc,
                )
            )
        if args.mode in {"k", "both", "all"}:
            results.append(
                probe_k_sharded_matmul_all_reduce(
                    mesh=device,
                    size=args.size,
                    seed=args.seed,
                    warmup=args.warmup,
                    runs=args.runs,
                    min_pcc=args.min_pcc,
                )
            )
        if args.mode in {"dft", "all"}:
            results.append(
                probe_real_dft_2d(
                    mesh=device,
                    size=args.size,
                    seed=args.seed,
                    warmup=args.warmup,
                    runs=args.runs,
                    min_pcc=args.min_pcc,
                )
            )
        if args.mode in {"complex-dft", "all"}:
            results.append(
                probe_complex_dft_2d(
                    mesh=device,
                    size=args.size,
                    seed=args.seed,
                    planes=args.planes,
                    warmup=args.warmup,
                    runs=args.runs,
                    min_pcc=args.min_pcc,
                )
            )
        if args.mode in {"partition-complex-dft", "all"}:
            results.append(
                probe_partitioned_complex_dft_2d(
                    mesh=device,
                    size=args.size,
                    seed=args.seed,
                    planes=args.planes,
                    warmup=args.warmup,
                    runs=args.runs,
                    min_pcc=args.min_pcc,
                )
            )
        for result in results:
            _print_result(result)
        if args.summary_json is not None:
            args.summary_json.parent.mkdir(parents=True, exist_ok=True)
            args.summary_json.write_text(
                json.dumps([result.__dict__ for result in results], indent=2, sort_keys=True) + "\n"
            )
        if not all(result.passed for result in results):
            raise SystemExit(1)
    finally:
        if device is not None:
            close_ttnn_device(device)
        restore_tt_runtime_env(previous_env)


if __name__ == "__main__":
    main()
