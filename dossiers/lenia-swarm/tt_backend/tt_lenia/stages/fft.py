"""DFT-as-matmul FFT: NumPy reference and TTNN device implementation.

At 128x128, each DFT matrix is 64KB float32 -- fits in Wormhole L1 SRAM.
2D DFT decomposes into two 1D transforms: W @ x @ W^T.
Complex matmul uses four real matmuls: (ac-bd, ad+bc).
"""
from __future__ import annotations

import numpy as np


def dft_matrix(N: int) -> np.ndarray:
    n = np.arange(N)
    return np.exp(-2j * np.pi * np.outer(n, n) / N).astype(np.complex64)


def dft_matrix_inv(N: int) -> np.ndarray:
    return np.conj(dft_matrix(N)) / N


def _complex_matmul_2d(
    x_re, x_im, W_re, W_im, WT_re, WT_im, *, matmul, sub, add,
):
    """2D complex matmul: W @ x @ W^T via 8 real matmuls."""
    t1_re = sub(matmul(x_re, WT_re), matmul(x_im, WT_im))
    t1_im = add(matmul(x_re, WT_im), matmul(x_im, WT_re))
    out_re = sub(matmul(W_re, t1_re), matmul(W_im, t1_im))
    out_im = add(matmul(W_re, t1_im), matmul(W_im, t1_re))
    return out_re, out_im


class DFTMatmul:
    """Precomputed DFT matrices for a given grid size (NumPy)."""

    def __init__(self, N: int):
        self.N = N
        W = dft_matrix(N)
        W_inv = dft_matrix_inv(N)
        self.W_re = W.real.astype(np.float32)
        self.W_im = W.imag.astype(np.float32)
        self.W_inv_re = W_inv.real.astype(np.float32)
        self.W_inv_im = W_inv.imag.astype(np.float32)

    def forward_2d(self, x_re: np.ndarray, x_im: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """2D forward DFT: F(x) = W @ x @ W^T using real arithmetic."""
        return _complex_matmul_2d(
            x_re, x_im,
            self.W_re, self.W_im, self.W_re.T, self.W_im.T,
            matmul=np.matmul, sub=np.subtract, add=np.add,
        )

    def inverse_2d(self, X_re: np.ndarray, X_im: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """2D inverse DFT: F^-1(X) = W_inv @ X @ W_inv^T."""
        return _complex_matmul_2d(
            X_re, X_im,
            self.W_inv_re, self.W_inv_im, self.W_inv_re.T, self.W_inv_im.T,
            matmul=np.matmul, sub=np.subtract, add=np.add,
        )


def _is_mesh_device(device) -> bool:
    import ttnn

    multi_device = getattr(getattr(ttnn, "_ttnn", None), "multi_device", None)
    mesh_type = getattr(multi_device, "MeshDevice", None)
    return mesh_type is not None and isinstance(device, mesh_type)


def _mesh_size(device) -> int:
    if hasattr(device, "get_num_devices"):
        return int(device.get_num_devices())
    if hasattr(device, "get_device_ids"):
        return len(device.get_device_ids())
    return 1


def _np_to_ttnn(arr: np.ndarray, device, *, dtype=None, shard_dim: int | None = None):
    """Transfer numpy array to TTNN device via torch bridge."""
    import torch
    import ttnn

    t = torch.from_numpy(arr.astype(np.float32))
    mesh_mapper = None
    if _is_mesh_device(device):
        if shard_dim is not None and arr.shape[shard_dim] >= _mesh_size(device):
            mesh_mapper = ttnn.shard_tensor_to_mesh_mapper(device, shard_dim)
        else:
            mesh_mapper = ttnn.replicate_tensor_to_mesh_mapper(device)
    return ttnn.from_torch(
        t,
        device=device,
        layout=ttnn.TILE_LAYOUT,
        dtype=dtype or ttnn.float32,
        mesh_mapper=mesh_mapper,
    )


def _ttnn_to_np(tensor, *, compose_dim: int | None = None) -> np.ndarray:
    """Transfer TTNN tensor back to numpy."""
    import ttnn

    if _is_mesh_device(tensor.device()):
        if compose_dim is not None:
            composer = ttnn.concat_mesh_to_tensor_composer(tensor.device(), compose_dim)
            return ttnn.to_torch(tensor, mesh_composer=composer).float().numpy()
        device_tensors = ttnn.get_device_tensors(tensor)
        if device_tensors:
            # Replicated mesh tensors have one valid logical copy per device. If the
            # caller did not request composition, read one device-local shard directly.
            return ttnn.to_torch(device_tensors[0]).float().numpy()
        raise RuntimeError(
            "Mesh tensor readback requires an explicit compose_dim or mesh composer; "
            "implicit shard merging is unsupported."
        )

    return ttnn.to_torch(tensor).float().numpy()


def _safe_deallocate(*tensors) -> None:
    import ttnn

    for tensor in tensors:
        if tensor is None:
            continue
        try:
            ttnn.deallocate(tensor)
        except Exception:
            pass


class TTNNDFTMatmul:
    """DFT matrices on Tenstorrent device. Weights stay in device DRAM."""

    def __init__(self, N: int, device, *, dtype=None):
        import ttnn

        self.N = N
        self.device = device
        self.dtype = dtype or ttnn.bfloat16
        W = dft_matrix(N)
        W_inv = dft_matrix_inv(N)
        self._forward_host = (
            W.real.astype(np.float32).reshape(1, 1, N, N),
            W.imag.astype(np.float32).reshape(1, 1, N, N),
            W.real.T.astype(np.float32).reshape(1, 1, N, N),
            W.imag.T.astype(np.float32).reshape(1, 1, N, N),
        )
        self._inverse_host = (
            W_inv.real.astype(np.float32).reshape(1, 1, N, N),
            W_inv.imag.astype(np.float32).reshape(1, 1, N, N),
            W_inv.real.T.astype(np.float32).reshape(1, 1, N, N),
            W_inv.imag.T.astype(np.float32).reshape(1, 1, N, N),
        )
        self._forward_cache: dict[int, tuple[object, object, object, object]] = {}
        self._inverse_cache: dict[int, tuple[object, object, object, object]] = {}

    def close(self) -> None:
        import ttnn

        for cache in (self._forward_cache, self._inverse_cache):
            for tensors in cache.values():
                for tensor in tensors:
                    try:
                        ttnn.deallocate(tensor)
                    except Exception:
                        pass
            cache.clear()

    def _batched_weights(self, batch_size: int, *, inverse: bool):
        cache = self._inverse_cache if inverse else self._forward_cache
        if batch_size in cache:
            return cache[batch_size]
        host = self._inverse_host if inverse else self._forward_host
        tensors = tuple(
            _np_to_ttnn(np.repeat(weight, batch_size, axis=0), self.device, dtype=self.dtype)
            for weight in host
        )
        cache[batch_size] = tensors
        return tensors

    def _prepare_input(self, tensor):
        import ttnn

        rank = len(tensor.shape)
        if rank == 3:
            batch = int(tensor.shape[0])
            return ttnn.reshape(tensor, (batch, 1, self.N, self.N)), rank, batch
        if rank == 4:
            if int(tensor.shape[1]) != 1:
                raise ValueError(f"Expected TTNN DFT inputs with singleton dim1, got shape {tuple(tensor.shape)}")
            return tensor, rank, int(tensor.shape[0])
        raise ValueError(f"Unsupported TTNN DFT rank: {rank}")

    def _restore_output(self, tensor, *, original_rank: int):
        import ttnn

        if original_rank == 3:
            return ttnn.reshape(tensor, (int(tensor.shape[0]), self.N, self.N))
        return tensor

    def forward_2d(self, x_re, x_im):
        """2D forward DFT on device tensors."""
        import ttnn

        x_re, original_rank, batch_size = self._prepare_input(x_re)
        x_im, _, _ = self._prepare_input(x_im)
        W_re, W_im, WT_re, WT_im = self._batched_weights(batch_size, inverse=False)
        out_re, out_im = _complex_matmul_2d(
            x_re, x_im,
            W_re, W_im, WT_re, WT_im,
            matmul=ttnn.matmul, sub=ttnn.subtract, add=ttnn.add,
        )
        return self._restore_output(out_re, original_rank=original_rank), self._restore_output(
            out_im,
            original_rank=original_rank,
        )

    def inverse_2d(self, X_re, X_im):
        """2D inverse DFT on device tensors."""
        import ttnn

        X_re, original_rank, batch_size = self._prepare_input(X_re)
        X_im, _, _ = self._prepare_input(X_im)
        W_re, W_im, WT_re, WT_im = self._batched_weights(batch_size, inverse=True)
        out_re, out_im = _complex_matmul_2d(
            X_re, X_im,
            W_re, W_im, WT_re, WT_im,
            matmul=ttnn.matmul, sub=ttnn.subtract, add=ttnn.add,
        )
        return self._restore_output(out_re, original_rank=original_rank), self._restore_output(
            out_im,
            original_rank=original_rank,
        )


class TTNNMeshDFTMatmul:
    """Spatially sharded DFT for a single plane on a TTNN mesh.

    This follows the upstream TT-Lang matmul tutorial pattern:
    first pass shards the input rows and replicates the right DFT weights;
    second pass reuses those row shards as K shards and fabric-all-reduces the
    partial output. The returned tensors are full-plane copies on each device.
    """

    def __init__(self, N: int, device, *, dtype=None):
        import ttnn

        if not _is_mesh_device(device):
            raise ValueError("TTNNMeshDFTMatmul requires a TTNN MeshDevice.")
        mesh_size = _mesh_size(device)
        if mesh_size <= 1:
            raise ValueError("TTNNMeshDFTMatmul requires a mesh with more than one device.")
        if N % mesh_size != 0:
            raise ValueError(f"DFT size {N} must be divisible by mesh size {mesh_size}.")

        self.N = N
        self.device = device
        self.dtype = dtype or ttnn.bfloat16
        W = dft_matrix(N)
        W_inv = dft_matrix_inv(N)
        self._forward_host = (
            W.real.astype(np.float32),
            W.imag.astype(np.float32),
            W.real.T.astype(np.float32),
            W.imag.T.astype(np.float32),
        )
        self._inverse_host = (
            W_inv.real.astype(np.float32),
            W_inv.imag.astype(np.float32),
            W_inv.real.T.astype(np.float32),
            W_inv.imag.T.astype(np.float32),
        )
        self._forward_cache: dict[tuple[int, int], tuple[object, object, object, object]] = {}
        self._inverse_cache: dict[tuple[int, int], tuple[object, object, object, object]] = {}

    def close(self) -> None:
        for cache in (self._forward_cache, self._inverse_cache):
            for tensors in cache.values():
                _safe_deallocate(*tensors)
            cache.clear()

    def _validate_host_planes(self, arr: np.ndarray) -> None:
        if arr.shape[-2:] != (self.N, self.N) or arr.ndim not in {2, 3}:
            raise ValueError(f"Expected host plane shape {(self.N, self.N)} or (planes, {self.N}, {self.N}), got {arr.shape}.")

    def row_sharded_from_numpy(self, arr: np.ndarray):
        """Upload host plane(s) sharded across mesh rows."""
        self._validate_host_planes(arr)
        return _np_to_ttnn(arr, self.device, dtype=self.dtype, shard_dim=arr.ndim - 2)

    def replicated_from_numpy(self, arr: np.ndarray):
        """Upload host plane(s) replicated to every mesh device."""
        self._validate_host_planes(arr)
        return _np_to_ttnn(arr, self.device, dtype=self.dtype)

    def row_shard_replicated(self, tensor):
        """Partition each device's full local copy into its mesh-owned rows."""
        import ttnn

        rank = len(tensor.shape)
        if rank not in {2, 3}:
            raise ValueError(f"Expected rank-2 or rank-3 replicated tensor, got shape {tuple(tensor.shape)}.")
        row_dim = rank - 2
        sharded = ttnn.mesh_partition(tensor, dim=row_dim)
        expected_shape = tuple(tensor.shape)
        expected_shape = (*expected_shape[:row_dim], self.N // _mesh_size(self.device), self.N)
        if tuple(sharded.shape) != expected_shape:
            _safe_deallocate(sharded)
            raise ValueError(f"mesh_partition produced shape {tuple(sharded.shape)}, expected {expected_shape}.")
        return sharded

    def replicated_to_numpy(self, tensor) -> np.ndarray:
        """Read one full-plane copy from a mesh-replicated result."""
        return _ttnn_to_np(tensor).astype(np.float32, copy=False)

    def row_sharded_to_numpy(self, tensor) -> np.ndarray:
        """Gather a row-sharded tensor to host for validation."""
        return _ttnn_to_np(tensor, compose_dim=len(tensor.shape) - 2).astype(np.float32, copy=False)

    def _weights(self, *, planes: int, rank: int, inverse: bool):
        cache = self._inverse_cache if inverse else self._forward_cache
        key = (planes, rank)
        if key in cache:
            return cache[key]
        W_re, W_im, WT_re, WT_im = self._inverse_host if inverse else self._forward_host
        if rank == 3:
            W_re = np.repeat(W_re.reshape(1, self.N, self.N), planes, axis=0)
            W_im = np.repeat(W_im.reshape(1, self.N, self.N), planes, axis=0)
            WT_re = np.repeat(WT_re.reshape(1, self.N, self.N), planes, axis=0)
            WT_im = np.repeat(WT_im.reshape(1, self.N, self.N), planes, axis=0)
        shard_dim = rank - 1
        tensors = (
            _np_to_ttnn(W_re, self.device, dtype=self.dtype, shard_dim=shard_dim),
            _np_to_ttnn(W_im, self.device, dtype=self.dtype, shard_dim=shard_dim),
            _np_to_ttnn(WT_re, self.device, dtype=self.dtype),
            _np_to_ttnn(WT_im, self.device, dtype=self.dtype),
        )
        cache[key] = tensors
        return tensors

    def _transform_2d(self, x_re, x_im, *, inverse: bool):
        import ttnn

        rank = len(x_re.shape)
        if rank not in {2, 3}:
            raise ValueError(f"Expected rank-2 or rank-3 row-sharded input, got shape {tuple(x_re.shape)}.")
        mesh_size = _mesh_size(self.device)
        planes = 1 if rank == 2 else int(x_re.shape[0])
        expected_shape = (self.N // mesh_size, self.N) if rank == 2 else (planes, self.N // mesh_size, self.N)
        if tuple(x_re.shape) != expected_shape:
            raise ValueError(
                "TTNNMeshDFTMatmul expects local row-sharded input shape "
                f"{expected_shape}, got {tuple(x_re.shape)}."
            )
        if tuple(x_im.shape) != tuple(x_re.shape):
            raise ValueError(f"Real/imag input shapes differ: {tuple(x_re.shape)} vs {tuple(x_im.shape)}.")

        W_re, W_im, WT_re, WT_im = self._weights(planes=planes, rank=rank, inverse=inverse)

        xre_wtre = xim_wtim = xre_wtim = xim_wtre = None
        t1_re = t1_im = None
        wre_t1re = wim_t1im = wre_t1im = wim_t1re = None
        partial_re = partial_im = None
        out_re = out_im = None
        try:
            xre_wtre = ttnn.matmul(x_re, WT_re)
            xim_wtim = ttnn.matmul(x_im, WT_im)
            t1_re = ttnn.subtract(xre_wtre, xim_wtim)
            xre_wtim = ttnn.matmul(x_re, WT_im)
            xim_wtre = ttnn.matmul(x_im, WT_re)
            t1_im = ttnn.add(xre_wtim, xim_wtre)
            _safe_deallocate(xre_wtre, xim_wtim, xre_wtim, xim_wtre)
            xre_wtre = xim_wtim = xre_wtim = xim_wtre = None

            wre_t1re = ttnn.matmul(W_re, t1_re)
            wim_t1im = ttnn.matmul(W_im, t1_im)
            partial_re = ttnn.subtract(wre_t1re, wim_t1im)
            wre_t1im = ttnn.matmul(W_re, t1_im)
            wim_t1re = ttnn.matmul(W_im, t1_re)
            partial_im = ttnn.add(wre_t1im, wim_t1re)
            out_re = ttnn.all_reduce(partial_re)
            out_im = ttnn.all_reduce(partial_im)
            return out_re, out_im
        except Exception:
            _safe_deallocate(out_re, out_im)
            raise
        finally:
            _safe_deallocate(
                xre_wtre,
                xim_wtim,
                xre_wtim,
                xim_wtre,
                t1_re,
                t1_im,
                wre_t1re,
                wim_t1im,
                wre_t1im,
                wim_t1re,
                partial_re,
                partial_im,
            )

    def forward_2d(self, x_re, x_im):
        return self._transform_2d(x_re, x_im, inverse=False)

    def inverse_2d(self, X_re, X_im):
        return self._transform_2d(X_re, X_im, inverse=True)
