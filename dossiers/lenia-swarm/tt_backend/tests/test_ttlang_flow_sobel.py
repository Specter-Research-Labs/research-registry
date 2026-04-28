from __future__ import annotations

import numpy as np
import pytest

from tt_lenia.stages.flow_ttlang import TTLangPackedSobelFlow
from tt_lenia.stages.flow import compute_flow
from ttlang.flow_gradient import (
    flow_gradient_param_matrix,
    flow_gradient_selector_matrices,
    packed_flow_gradient_reference,
)
from ttlang.flow_combine import flow_combine_param_matrix, packed_flow_combine_reference
from ttlang.flow_sobel import flow_sobel_param_matrix, flow_sobel_selector_matrices, packed_flow_sobel_reference
from ttlang.shape_bridge import lenia_state_to_plane_matrix


def test_packed_flow_sobel_reference_matches_numpy_flow():
    rng = np.random.default_rng(41)
    batch = 2
    sx = 64
    sy = 64
    channels = 2
    mass = rng.uniform(0.0, 0.7, size=(batch, sx, sy, channels)).astype(np.float32)
    u = rng.uniform(-0.2, 0.3, size=(batch, sx, sy, channels)).astype(np.float32)

    mass_matrix, _ = lenia_state_to_plane_matrix(mass)
    u_matrix, _ = lenia_state_to_plane_matrix(u)
    flow_y, flow_x = packed_flow_sobel_reference(
        mass_matrix,
        u_matrix,
        batch=batch,
        channels=channels,
        sx=sx,
        sy=sy,
        theta_a=1.0,
        dd=5,
        sigma=0.65,
        flow_clip="none",
    )

    expected = compute_flow(
        u,
        mass,
        theta_a=1.0,
        n=2,
        alpha_mode="mass",
        flow_clip="none",
        chem_channel=None,
        chem_include_in_mass=True,
        dd=5,
        sigma=0.65,
    )
    actual = np.stack(
        [
            flow_y.reshape(batch, channels, sx, sy).transpose(0, 2, 3, 1),
            flow_x.reshape(batch, channels, sx, sy).transpose(0, 2, 3, 1),
        ],
        axis=3,
    )

    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-6)


def test_flow_sobel_device_matrices_are_tile_shaped():
    rows, cols = flow_sobel_selector_matrices()
    params = flow_sobel_param_matrix(theta_a=1.0, dd=5, sigma=0.65)

    assert rows.shape == (16 * 32, 32)
    assert cols.shape == (16 * 32, 32)
    assert params.shape == (19 * 32, 32)


def test_packed_flow_gradient_reference_matches_numpy_sobel():
    from tt_lenia.stages.flow import sobel_periodic

    rng = np.random.default_rng(47)
    batch = 2
    sx = 64
    sy = 64
    channels = 2
    field = rng.uniform(-0.4, 0.7, size=(batch, sx, sy, channels)).astype(np.float32)

    matrix, _ = lenia_state_to_plane_matrix(field)
    gy, gx = packed_flow_gradient_reference(matrix, batch=batch, channels=channels, sx=sx, sy=sy)

    actual = np.stack(
        [
            gy.reshape(batch, channels, sx, sy).transpose(0, 2, 3, 1),
            gx.reshape(batch, channels, sx, sy).transpose(0, 2, 3, 1),
        ],
        axis=3,
    )
    expected = sobel_periodic(field)

    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-6)


def test_flow_gradient_device_matrices_are_tile_shaped():
    rows, cols = flow_gradient_selector_matrices()
    params = flow_gradient_param_matrix()

    assert rows.shape == (16 * 32, 32)
    assert cols.shape == (16 * 32, 32)
    assert params.shape == (16 * 32, 32)


def test_packed_flow_combine_reference_matches_numpy_flow_from_gradients():
    rng = np.random.default_rng(53)
    batch = 2
    sx = 64
    sy = 64
    channels = 2
    mass = rng.uniform(0.0, 0.7, size=(batch, sx, sy, channels)).astype(np.float32)
    u = rng.uniform(-0.2, 0.3, size=(batch, sx, sy, channels)).astype(np.float32)
    mass_total = mass.sum(axis=-1, keepdims=True)

    mass_matrix, _ = lenia_state_to_plane_matrix(mass_total)
    u_matrix, _ = lenia_state_to_plane_matrix(u)
    gy_u, gx_u = packed_flow_gradient_reference(u_matrix, batch=batch, channels=channels, sx=sx, sy=sy)
    gy_mass, gx_mass = packed_flow_gradient_reference(mass_matrix, batch=batch, channels=1, sx=sx, sy=sy)
    flow_y, flow_x = packed_flow_combine_reference(
        mass_matrix,
        gy_u,
        gx_u,
        gy_mass,
        gx_mass,
        batch=batch,
        channels=channels,
        sx=sx,
        sy=sy,
        theta_a=1.0,
    )

    actual = np.stack(
        [
            flow_y.reshape(batch, channels, sx, sy).transpose(0, 2, 3, 1),
            flow_x.reshape(batch, channels, sx, sy).transpose(0, 2, 3, 1),
        ],
        axis=3,
    )
    expected = compute_flow(
        u,
        mass,
        theta_a=1.0,
        n=2,
        alpha_mode="mass",
        flow_clip="none",
        chem_channel=None,
        chem_include_in_mass=True,
        dd=5,
        sigma=0.65,
    )

    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-6)


def test_flow_combine_param_matrix_is_tile_shaped():
    params = flow_combine_param_matrix(theta_a=1.0)

    assert params.shape == (3 * 32, 32)


@pytest.mark.parametrize(
    ("batch", "channels", "sx", "sy", "expected"),
    [
        (1, 1, 64, 64, (2, 2)),
        (1, 1, 128, 128, (4, 4)),
        (1, 2, 128, 128, (4, 7)),
        (1, 1, 256, 256, (8, 7)),
        (1, 2, 256, 256, (8, 7)),
    ],
)
def test_ttlang_flow_uses_tile_level_grid(batch, channels, sx, sy, expected):
    assert TTLangPackedSobelFlow._kernel_grid(batch=batch, channels=channels, sx=sx, sy=sy) == expected
