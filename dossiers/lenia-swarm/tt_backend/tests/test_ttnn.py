"""TTNN device tests — skipped when ttnn is not importable."""
from __future__ import annotations

import numpy as np
import pytest

from tt_lenia.stages.fft import DFTMatmul, TTNNDFTMatmul, _np_to_ttnn, _ttnn_to_np

ttnn = pytest.importorskip("ttnn")

DEVICE_ID = 1


@pytest.fixture(scope="module")
def device():
    d = ttnn.open_device(device_id=DEVICE_ID)
    yield d
    ttnn.close_device(d)


class TestTTNNDFTMatmul:
    def test_forward_matches_numpy(self, device):
        N = 128
        rng = np.random.default_rng(42)
        x = rng.standard_normal((1, N, N)).astype(np.float32)
        x_im = np.zeros_like(x)

        ref = DFTMatmul(N)
        ref_re, ref_im = ref.forward_2d(x, x_im)

        tt_dft = TTNNDFTMatmul(N, device)
        t_re = _np_to_ttnn(x, device)
        t_im = _np_to_ttnn(x_im, device)
        out_re, out_im = tt_dft.forward_2d(t_re, t_im)
        out_re_np = _ttnn_to_np(out_re)
        out_im_np = _ttnn_to_np(out_im)

        assert out_re_np.shape == ref_re.shape
        re_diff = np.max(np.abs(out_re_np - ref_re))
        im_diff = np.max(np.abs(out_im_np - ref_im))
        print(f"DFT forward: re_max_diff={re_diff:.2e}, im_max_diff={im_diff:.2e}")
        assert re_diff < 2.0, f"re max_diff={re_diff:.2e}"
        assert im_diff < 2.0, f"im max_diff={im_diff:.2e}"

    def test_inverse_roundtrip(self, device):
        N = 128
        rng = np.random.default_rng(99)
        x = rng.standard_normal((1, N, N)).astype(np.float32)
        x_im = np.zeros_like(x)

        tt_dft = TTNNDFTMatmul(N, device)
        t_re = _np_to_ttnn(x, device)
        t_im = _np_to_ttnn(x_im, device)

        fwd_re, fwd_im = tt_dft.forward_2d(t_re, t_im)
        inv_re, inv_im = tt_dft.inverse_2d(fwd_re, fwd_im)

        roundtrip = _ttnn_to_np(inv_re)
        max_diff = np.max(np.abs(roundtrip - x))
        assert max_diff < 1.0, f"roundtrip max_diff={max_diff:.2e}"


class TestTTNNEngine:
    def test_step_matches_numpy(self, device, paper_config, paper_kernels, random_mass_1c_128):
        from tt_lenia.engine import TTFlowLeniaEngine
        from tt_lenia.numpy_ref.engine import NumpyFlowLeniaEngine

        config, _ = paper_config
        np_engine = NumpyFlowLeniaEngine(config, paper_kernels)
        tt_engine = TTFlowLeniaEngine(config, paper_kernels, device=device)

        np_result = np_engine.step(random_mass_1c_128)
        tt_result = tt_engine.step(random_mass_1c_128)

        max_diff = np.max(np.abs(tt_result.mass - np_result.mass))
        assert max_diff < 5e-1, f"mass_out max_diff={max_diff:.2e}"

    def test_capture_stages_matches_numpy(self, device, paper_config, paper_kernels, random_mass_1c_128):
        from tt_lenia.engine import TTFlowLeniaEngine
        from tt_lenia.numpy_ref.engine import NumpyFlowLeniaEngine

        config, _ = paper_config
        np_engine = NumpyFlowLeniaEngine(config, paper_kernels)
        tt_engine = TTFlowLeniaEngine(config, paper_kernels, device=device)

        np_result = np_engine.step(random_mass_1c_128, capture_stages=True)
        tt_result = tt_engine.step(random_mass_1c_128, capture_stages=True)

        assert tt_result.uk is not None
        assert tt_result.growth_out is not None
        assert tt_result.u is not None
        assert tt_result.flow is not None

        assert np.max(np.abs(tt_result.uk - np_result.uk)) < 1.0
        assert np.max(np.abs(tt_result.growth_out - np_result.growth_out)) < 1.0
        assert np.max(np.abs(tt_result.u - np_result.u)) < 1.0
        assert np.max(np.abs(tt_result.flow - np_result.flow)) < 1.0
