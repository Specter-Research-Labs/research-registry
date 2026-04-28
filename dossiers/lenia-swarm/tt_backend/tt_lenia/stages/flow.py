"""Stage 5: Sobel gradient + alpha blending to compute flow field."""
from __future__ import annotations

import numpy as np


def sobel_periodic(A: np.ndarray) -> np.ndarray:
    """Sobel gradient with periodic boundary.

    A: [batch, sx, sy, C]
    Returns: [batch, sx, sy, 2, C] where dim 3 is (gy, gx).
    """
    a00 = np.roll(np.roll(A, 1, axis=1), 1, axis=2)
    a01 = np.roll(A, 1, axis=1)
    a02 = np.roll(np.roll(A, 1, axis=1), -1, axis=2)
    a10 = np.roll(A, 1, axis=2)
    a12 = np.roll(A, -1, axis=2)
    a20 = np.roll(np.roll(A, -1, axis=1), 1, axis=2)
    a21 = np.roll(A, -1, axis=1)
    a22 = np.roll(np.roll(A, -1, axis=1), -1, axis=2)

    gx = (a00 + 2.0 * a10 + a20) - (a02 + 2.0 * a12 + a22)
    gy = (a00 + 2.0 * a01 + a02) - (a20 + 2.0 * a21 + a22)

    return np.stack([gy, gx], axis=3)


def mass_field(
    A: np.ndarray, chem_channel: int | None, include_in_mass: bool
) -> np.ndarray:
    total = A.sum(axis=-1, keepdims=True)
    if chem_channel is not None and not include_in_mass:
        chem = A[:, :, :, chem_channel : chem_channel + 1]
        total = total - chem
    return total


def _ttnn_shape4d(tensor) -> tuple[int, int, int, int]:
    return tuple(int(dim) for dim in tensor.shape)


def _ttnn_roll_axis(tensor, axis: int, shift: int):
    import ttnn

    batch, sx, sy, channels = _ttnn_shape4d(tensor)
    size = sx if axis == 1 else sy
    normalized = shift % size
    if normalized == 0:
        return tensor

    if axis == 1:
        front = ttnn.slice(tensor, (0, size - normalized, 0, 0), (batch, size, sy, channels))
        back = ttnn.slice(tensor, (0, 0, 0, 0), (batch, size - normalized, sy, channels))
    elif axis == 2:
        front = ttnn.slice(tensor, (0, 0, size - normalized, 0), (batch, sx, size, channels))
        back = ttnn.slice(tensor, (0, 0, 0, 0), (batch, sx, size - normalized, channels))
    else:
        raise ValueError(f"Unsupported roll axis: {axis}")

    return ttnn.concat([front, back], dim=axis)


def ttnn_roll_periodic(tensor, shift_y: int, shift_x: int):
    rolled = _ttnn_roll_axis(tensor, 1, shift_y)
    return _ttnn_roll_axis(rolled, 2, shift_x)


def ttnn_sobel_periodic_split(tensor):
    import ttnn

    a00 = ttnn_roll_periodic(tensor, 1, 1)
    a01 = ttnn_roll_periodic(tensor, 1, 0)
    a02 = ttnn_roll_periodic(tensor, 1, -1)
    a10 = ttnn_roll_periodic(tensor, 0, 1)
    a12 = ttnn_roll_periodic(tensor, 0, -1)
    a20 = ttnn_roll_periodic(tensor, -1, 1)
    a21 = ttnn_roll_periodic(tensor, -1, 0)
    a22 = ttnn_roll_periodic(tensor, -1, -1)

    gx_left = ttnn.add(ttnn.add(a00, ttnn.multiply(a10, 2.0)), a20)
    gx_right = ttnn.add(ttnn.add(a02, ttnn.multiply(a12, 2.0)), a22)
    gy_top = ttnn.add(ttnn.add(a00, ttnn.multiply(a01, 2.0)), a02)
    gy_bottom = ttnn.add(ttnn.add(a20, ttnn.multiply(a21, 2.0)), a22)
    return ttnn.subtract(gy_top, gy_bottom), ttnn.subtract(gx_left, gx_right)


def ttnn_mass_field(A, chem_channel: int | None, include_in_mass: bool):
    import ttnn

    total = ttnn.sum(A, dim=3, keepdim=True)
    if chem_channel is not None and not include_in_mass:
        batch, sx, sy, _ = _ttnn_shape4d(A)
        chem = ttnn.slice(A, (0, 0, 0, chem_channel), (batch, sx, sy, chem_channel + 1))
        total = ttnn.subtract(total, chem)
    return total


def _ttnn_clamp(tensor, lo: float, hi: float):
    import ttnn

    return ttnn.minimum(ttnn.maximum(tensor, lo), hi)


def _ttnn_alpha(tensor, *, theta_a: float, n: int):
    import ttnn

    scaled = ttnn.multiply(tensor, 1.0 / float(theta_a))
    if int(n) == 2:
        alpha = _ttnn_clamp(ttnn.multiply(scaled, scaled), 0.0, 1.0)
        return alpha, (scaled,)
    alpha = _ttnn_clamp(ttnn.pow(scaled, float(n)), 0.0, 1.0)
    return alpha, (scaled,)


def _sobel_weight_tensor(channels: int) -> np.ndarray:
    gy = np.array([[1.0, 2.0, 1.0], [0.0, 0.0, 0.0], [-1.0, -2.0, -1.0]], dtype=np.float32)
    gx = np.array([[1.0, 0.0, -1.0], [2.0, 0.0, -2.0], [1.0, 0.0, -1.0]], dtype=np.float32)
    weights = np.zeros((2 * channels, channels, 3, 3), dtype=np.float32)
    for channel in range(channels):
        weights[channel, channel, :, :] = gy
        weights[channels + channel, channel, :, :] = gx
    return weights


class TTNNPeriodicSobelFlow:
    """Flow stage using TTNN conv2d for the periodic Sobel stencils.

    This replaces the eight roll/slice/concat Sobel construction with one
    torus halo pad and a cached 3x3 convolution per field.
    """

    def __init__(self, device):
        self.device = device
        self._weight_cache: dict[tuple[int, int, int, int], object] = {}

    def close(self) -> None:
        import ttnn

        for weight in self._weight_cache.values():
            try:
                ttnn.deallocate(weight)
            except Exception:
                pass
        self._weight_cache.clear()

    def __call__(
        self,
        U,
        A,
        *,
        theta_a: float,
        n: int,
        alpha_mode: str,
        flow_clip: str,
        chem_channel: int | None,
        chem_include_in_mass: bool,
        dd: int,
        sigma: float,
        wall_potential=None,
    ):
        import ttnn

        if wall_potential is not None:
            raise ValueError("TTNN conv flow does not yet support wall potential")

        batch, sx, sy, channels = _ttnn_shape4d(U)
        if _ttnn_shape4d(A) != (batch, sx, sy, channels):
            raise ValueError(f"Expected U/A shape match, got {tuple(U.shape)} and {tuple(A.shape)}.")

        gy_u, gx_u = self._sobel_split(U, channels=channels, batch=batch, sx=sx, sy=sy)
        mass = ttnn_mass_field(A, chem_channel, chem_include_in_mass)
        gy_a, gx_a = self._sobel_split(mass, channels=1, batch=batch, sx=sx, sy=sy)

        if alpha_mode == "mass":
            alpha_src = mass
        elif alpha_mode == "per_channel":
            alpha_src = A
        else:
            raise ValueError(f"Unknown alpha_mode: {alpha_mode}")

        alpha, alpha_cleanup = _ttnn_alpha(alpha_src, theta_a=theta_a, n=n)
        # Equivalent to (1 - alpha) * grad_u - alpha * grad_a, with fewer TTNN ops.
        flow_y_grad_sum = ttnn.add(gy_u, gy_a)
        flow_x_grad_sum = ttnn.add(gx_u, gx_a)
        flow_y_scaled = ttnn.multiply(alpha, flow_y_grad_sum)
        flow_x_scaled = ttnn.multiply(alpha, flow_x_grad_sum)
        flow_y = ttnn.subtract(gy_u, flow_y_scaled)
        flow_x = ttnn.subtract(gx_u, flow_x_scaled)

        if flow_clip == "always":
            max_flow = float(dd) - sigma
            clipped_y = _ttnn_clamp(flow_y, -max_flow, max_flow)
            clipped_x = _ttnn_clamp(flow_x, -max_flow, max_flow)
            self._release((flow_y, flow_x))
            flow_y, flow_x = clipped_y, clipped_x

        self._release(
            (
                gy_u,
                gx_u,
                mass,
                gy_a,
                gx_a,
                alpha,
                *alpha_cleanup,
                flow_y_grad_sum,
                flow_x_grad_sum,
                flow_y_scaled,
                flow_x_scaled,
            )
        )
        return flow_y, flow_x

    def _sobel_split(self, tensor, *, channels: int, batch: int, sx: int, sy: int):
        import ttnn

        padded, pad_cleanup = self._periodic_pad(tensor, batch=batch, sx=sx, sy=sy, channels=channels)
        conv_out = self._conv2d(padded, channels=channels, batch=batch, sx=sx, sy=sy)
        conv_out = ttnn.reshape(conv_out, (batch, sx, sy, 2 * channels))
        gy = ttnn.slice(conv_out, (0, 0, 0, 0), (batch, sx, sy, channels))
        gx = ttnn.slice(conv_out, (0, 0, 0, channels), (batch, sx, sy, 2 * channels))
        self._release((*pad_cleanup, padded, conv_out))
        return gy, gx

    def _periodic_pad(self, tensor, *, batch: int, sx: int, sy: int, channels: int):
        import ttnn

        top = ttnn.slice(tensor, (0, sx - 1, 0, 0), (batch, sx, sy, channels))
        bottom = ttnn.slice(tensor, (0, 0, 0, 0), (batch, 1, sy, channels))
        rows = ttnn.concat([top, tensor, bottom], dim=1)
        left = ttnn.slice(rows, (0, 0, sy - 1, 0), (batch, sx + 2, sy, channels))
        right = ttnn.slice(rows, (0, 0, 0, 0), (batch, sx + 2, 1, channels))
        padded = ttnn.concat([left, rows, right], dim=2)
        return padded, (top, bottom, rows, left, right)

    def _conv2d(self, tensor, *, channels: int, batch: int, sx: int, sy: int):
        import torch
        import ttnn

        conv_config = ttnn.Conv2dConfig()
        conv_config.config_tensors_in_dram = True
        conv_config.output_layout = ttnn.TILE_LAYOUT
        key = (channels, batch, sx, sy)
        weight = self._weight_cache.get(key)
        if weight is None:
            weight_host = torch.from_numpy(_sobel_weight_tensor(channels))
            weight = ttnn.from_torch(weight_host, layout=ttnn.ROW_MAJOR_LAYOUT, dtype=ttnn.float32)
            result = ttnn.conv2d(
                input_tensor=tensor,
                weight_tensor=weight,
                device=self.device,
                in_channels=channels,
                out_channels=2 * channels,
                batch_size=batch,
                input_height=sx + 2,
                input_width=sy + 2,
                kernel_size=(3, 3),
                stride=(1, 1),
                padding=(0, 0),
                groups=1,
                dtype=ttnn.float32,
                conv_config=conv_config,
                return_weights_and_bias=True,
            )
            conv_out, (prepared_weight, prepared_bias) = result
            self._weight_cache[key] = prepared_weight
            self._release((weight, prepared_bias))
            return conv_out

        return ttnn.conv2d(
            input_tensor=tensor,
            weight_tensor=weight,
            device=self.device,
            in_channels=channels,
            out_channels=2 * channels,
            batch_size=batch,
            input_height=sx + 2,
            input_width=sy + 2,
            kernel_size=(3, 3),
            stride=(1, 1),
            padding=(0, 0),
            groups=1,
            dtype=ttnn.float32,
            conv_config=conv_config,
        )

    @staticmethod
    def _release(tensors) -> None:
        import ttnn

        for tensor in tensors:
            if tensor is None:
                continue
            try:
                ttnn.deallocate(tensor)
            except Exception:
                pass


def ttnn_compute_flow(
    U,
    A,
    *,
    theta_a: float,
    n: int,
    alpha_mode: str,
    flow_clip: str,
    chem_channel: int | None,
    chem_include_in_mass: bool,
    dd: int,
    sigma: float,
    wall_potential=None,
):
    import ttnn

    if wall_potential is not None:
        raise ValueError("TTNN flow does not yet support wall potential")

    gy_u, gx_u = ttnn_sobel_periodic_split(U)
    mass = ttnn_mass_field(A, chem_channel, chem_include_in_mass)
    gy_a, gx_a = ttnn_sobel_periodic_split(mass)

    if alpha_mode == "mass":
        alpha, _ = _ttnn_alpha(mass, theta_a=theta_a, n=n)
    elif alpha_mode == "per_channel":
        alpha, _ = _ttnn_alpha(A, theta_a=theta_a, n=n)
    else:
        raise ValueError(f"Unknown alpha_mode: {alpha_mode}")

    flow_y = ttnn.subtract(gy_u, ttnn.multiply(alpha, ttnn.add(gy_u, gy_a)))
    flow_x = ttnn.subtract(gx_u, ttnn.multiply(alpha, ttnn.add(gx_u, gx_a)))

    if flow_clip == "always":
        max_flow = float(dd) - sigma
        flow_y = _ttnn_clamp(flow_y, -max_flow, max_flow)
        flow_x = _ttnn_clamp(flow_x, -max_flow, max_flow)

    return flow_y, flow_x


def compute_flow(
    U: np.ndarray,
    A: np.ndarray,
    *,
    theta_a: float,
    n: int,
    alpha_mode: str,
    flow_clip: str,
    chem_channel: int | None,
    chem_include_in_mass: bool,
    dd: int,
    sigma: float,
    wall_potential: np.ndarray | None = None,
) -> np.ndarray:
    """Compute flow field F from affinity U and mass A.

    Returns F: [batch, sx, sy, 2, channels].
    """
    if wall_potential is not None:
        U = U + wall_potential

    nabla_U = sobel_periodic(U)
    mass = mass_field(A, chem_channel, chem_include_in_mass)
    nabla_A = sobel_periodic(mass)

    if alpha_mode == "mass":
        alpha = np.clip(np.power(mass / theta_a, float(n)), 0.0, 1.0)
    elif alpha_mode == "per_channel":
        alpha = np.clip(np.power(A / theta_a, float(n)), 0.0, 1.0)
    else:
        raise ValueError(f"Unknown alpha_mode: {alpha_mode}")

    alpha_exp = np.expand_dims(alpha, axis=3)
    F = (1.0 - alpha_exp) * nabla_U - alpha_exp * nabla_A

    if flow_clip == "always":
        max_flow = float(dd) - sigma
        F = np.clip(F, -max_flow, max_flow)

    return F.astype(np.float32)
