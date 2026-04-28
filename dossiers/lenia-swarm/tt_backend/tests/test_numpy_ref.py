"""Internal consistency tests for the NumPy reference engine."""
import numpy as np

from tt_lenia.numpy_ref import stages
from tt_lenia.numpy_ref.engine import NumpyFlowLeniaEngine


class TestGrowth:
    def test_peak_at_mu(self):
        """Growth function peaks at mu with value (2*1 - 1) * h = h."""
        m = np.array([0.3], dtype=np.float32)
        s = np.array([0.1], dtype=np.float32)
        h = np.array([0.5], dtype=np.float32)
        UK = np.array([[[[0.3]]]], dtype=np.float32)
        G = stages.growth(UK, m, s, h)
        assert np.isclose(G[0, 0, 0, 0], 0.5, atol=1e-6)

    def test_far_from_mu_is_negative(self):
        """Growth function far from mu approaches -h."""
        m = np.array([0.3], dtype=np.float32)
        s = np.array([0.01], dtype=np.float32)
        h = np.array([1.0], dtype=np.float32)
        UK = np.array([[[[10.0]]]], dtype=np.float32)
        G = stages.growth(UK, m, s, h)
        assert G[0, 0, 0, 0] < -0.99

    def test_symmetric_around_mu(self):
        """Growth function is symmetric around mu."""
        m = np.array([0.3], dtype=np.float32)
        s = np.array([0.1], dtype=np.float32)
        h = np.array([1.0], dtype=np.float32)
        UK_above = np.array([[[[0.4]]]], dtype=np.float32)
        UK_below = np.array([[[[0.2]]]], dtype=np.float32)
        assert np.isclose(
            stages.growth(UK_above, m, s, h),
            stages.growth(UK_below, m, s, h),
            atol=1e-6,
        )


class TestSobel:
    def test_constant_field_zero_gradient(self):
        """Constant field has zero gradient everywhere."""
        A = np.ones((1, 16, 16, 1), dtype=np.float32) * 5.0
        grad = stages.sobel_periodic(A)
        assert np.allclose(grad, 0.0, atol=1e-6)

    def test_linear_ramp_x(self):
        """Linear ramp in x (axis 1) produces nonzero gy (dim3=0), near-zero gx (dim3=1)."""
        N = 32
        A = np.zeros((1, N, N, 1), dtype=np.float32)
        for i in range(N):
            A[0, i, :, 0] = float(i) / N
        grad = stages.sobel_periodic(A)
        gy = grad[0, :, :, 0, 0]
        gx = grad[0, :, :, 1, 0]
        interior_gy = gy[2:-2, 2:-2]
        assert np.all(np.abs(interior_gy) > 0.01)
        assert np.max(np.abs(gx[2:-2, 2:-2])) < np.mean(np.abs(interior_gy)) * 0.5


class TestReintegration:
    def test_mass_conservation_zero_flow(self):
        """With zero flow, reintegration preserves total mass exactly."""
        rng = np.random.default_rng(10)
        sx, sy = 32, 32
        mass = np.zeros((1, sx, sy, 1), dtype=np.float32)
        mass[0, 10:22, 10:22, 0] = rng.uniform(0, 1, (12, 12)).astype(np.float32)
        F = np.zeros((1, sx, sy, 2, 1), dtype=np.float32)
        pos_grid = stages.build_pos_grid(sx, sy)

        result = stages.reintegration(
            mass, F, pos_grid=pos_grid, dt=0.2, dd=5, sigma=0.65,
            use_torus=True, sx=sx, sy=sy,
        )
        assert np.isclose(result.sum(), mass.sum(), rtol=1e-4), (
            f"Mass changed: {mass.sum()} -> {result.sum()}"
        )

    def test_mass_conservation_with_flow(self):
        """With nonzero flow, reintegration still conserves total mass."""
        rng = np.random.default_rng(11)
        sx, sy = 32, 32
        mass = np.zeros((1, sx, sy, 1), dtype=np.float32)
        mass[0, 10:22, 10:22, 0] = rng.uniform(0, 1, (12, 12)).astype(np.float32)
        F = rng.uniform(-1, 1, (1, sx, sy, 2, 1)).astype(np.float32) * 0.5
        pos_grid = stages.build_pos_grid(sx, sy)

        result = stages.reintegration(
            mass, F, pos_grid=pos_grid, dt=0.2, dd=5, sigma=0.65,
            use_torus=True, sx=sx, sy=sy,
        )
        assert np.isclose(result.sum(), mass.sum(), rtol=1e-3), (
            f"Mass changed: {mass.sum()} -> {result.sum()}"
        )

    def test_nonnegative_output(self):
        """Reintegration of nonnegative input with any flow stays nonnegative."""
        rng = np.random.default_rng(12)
        sx, sy = 32, 32
        mass = rng.uniform(0, 1, (1, sx, sy, 1)).astype(np.float32)
        F = rng.uniform(-2, 2, (1, sx, sy, 2, 1)).astype(np.float32)
        pos_grid = stages.build_pos_grid(sx, sy)

        result = stages.reintegration(
            mass, F, pos_grid=pos_grid, dt=0.2, dd=5, sigma=0.65,
            use_torus=True, sx=sx, sy=sy,
        )
        assert np.all(result >= -1e-6), f"Min value: {result.min()}"


class TestEngine:
    def test_step_shape(self, paper_config, paper_kernels, random_mass_1c_128):
        config, _ = paper_config
        engine = NumpyFlowLeniaEngine(config, paper_kernels)
        result = engine.step(random_mass_1c_128)
        assert result.mass.shape == random_mass_1c_128.shape
        assert result.mass.dtype == np.float32

    def test_step_captures_stages(self, paper_config, paper_kernels, random_mass_1c_128):
        config, _ = paper_config
        engine = NumpyFlowLeniaEngine(config, paper_kernels)
        result = engine.step(random_mass_1c_128, capture_stages=True)
        assert result.fft_out is not None
        assert result.uk is not None
        assert result.flow is not None

    def test_deterministic(self, paper_config, paper_kernels, random_mass_1c_128):
        """Same input produces identical output."""
        config, _ = paper_config
        engine = NumpyFlowLeniaEngine(config, paper_kernels)
        r1 = engine.step(random_mass_1c_128)
        r2 = engine.step(random_mass_1c_128)
        assert np.array_equal(r1.mass, r2.mass)

    def test_mass_conservation(self, paper_config, paper_kernels, random_mass_1c_128):
        config, _ = paper_config
        engine = NumpyFlowLeniaEngine(config, paper_kernels)
        result = engine.step(random_mass_1c_128)
        assert np.isclose(result.mass.sum(), random_mass_1c_128.sum(), rtol=1e-3), (
            f"Mass: {random_mass_1c_128.sum():.4f} -> {result.mass.sum():.4f}"
        )

    def test_multi_step_runs(self, paper_config, paper_kernels, random_mass_1c_128):
        config, _ = paper_config
        engine = NumpyFlowLeniaEngine(config, paper_kernels)
        result = engine.run(random_mass_1c_128, steps=5)
        assert result.shape == random_mass_1c_128.shape
        assert np.isfinite(result).all()
