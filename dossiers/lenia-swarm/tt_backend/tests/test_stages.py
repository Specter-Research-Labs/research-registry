"""Test individual TTNN-ready stages against the NumPy reference."""
import sys
from types import ModuleType, SimpleNamespace

import numpy as np

from tt_lenia.stages.fft import DFTMatmul
from tt_lenia.stages.gather_spectra import compile_kernel_source_groups, gather_kernel_spectra_numpy
from tt_lenia.stages.gather_spectra_ttlang import TTLangGatherKernelSpectra
from tt_lenia.stages.growth import growth_bell
from tt_lenia.stages.reintegration_generic import _tiles_to_mass
from tt_lenia.stages.reintegration import build_pos_grid, reintegrate
from tt_lenia.numpy_ref import stages as ref


class TestDFTMatmulStage:
    def test_forward_matches_numpy_fft(self):
        N = 128
        rng = np.random.default_rng(0)
        x = rng.standard_normal((N, N)).astype(np.float32)

        dft = DFTMatmul(N)
        out_re, out_im = dft.forward_2d(x, np.zeros_like(x))

        expected = np.fft.fft2(x)
        assert np.allclose(out_re, expected.real, atol=1e-2)
        assert np.allclose(out_im, expected.imag, atol=1e-2)

    def test_roundtrip(self):
        N = 128
        rng = np.random.default_rng(1)
        x = rng.standard_normal((N, N)).astype(np.float32)

        dft = DFTMatmul(N)
        f_re, f_im = dft.forward_2d(x, np.zeros_like(x))
        r_re, r_im = dft.inverse_2d(f_re, f_im)

        assert np.allclose(r_re, x, atol=1e-2)
        assert np.allclose(r_im, 0, atol=1e-2)


class TestGrowthStage:
    def test_matches_ref(self):
        rng = np.random.default_rng(5)
        UK = rng.standard_normal((2, 32, 32, 3)).astype(np.float32)
        m = np.array([0.1, 0.3, 0.5], dtype=np.float32)
        s = np.array([0.05, 0.1, 0.15], dtype=np.float32)
        h = np.array([0.5, 0.8, 1.0], dtype=np.float32)

        ref_result = ref.growth(UK, m, s, h)
        stage_result = growth_bell(UK, m, s, h)
        assert np.allclose(ref_result, stage_result, atol=1e-6)


class TestGatherSpectraStage:
    def test_kernel_source_groups_preserve_kernel_order(self):
        c0_idxs = np.array([0, 0, 0, 1, 1, 2, 2, 2], dtype=np.int32)
        groups = compile_kernel_source_groups(c0_idxs)
        assert [(group.source_channel, group.start, group.stop) for group in groups] == [
            (0, 0, 3),
            (1, 3, 5),
            (2, 5, 8),
        ]

    def test_numpy_gather_matches_reference_indexing(self):
        rng = np.random.default_rng(7)
        fA_re = rng.standard_normal((2, 32, 32, 3)).astype(np.float32)
        fA_im = rng.standard_normal((2, 32, 32, 3)).astype(np.float32)
        fK_re = rng.standard_normal((1, 32, 32, 6)).astype(np.float32)
        fK_im = rng.standard_normal((1, 32, 32, 6)).astype(np.float32)
        c0_idxs = np.array([0, 0, 1, 1, 2, 2], dtype=np.int32)

        out_re, out_im = gather_kernel_spectra_numpy(fA_re, fA_im, fK_re, fK_im, c0_idxs)
        expected_re = fA_re[:, :, :, c0_idxs] * fK_re - fA_im[:, :, :, c0_idxs] * fK_im
        expected_im = fA_re[:, :, :, c0_idxs] * fK_im + fA_im[:, :, :, c0_idxs] * fK_re
        assert np.allclose(out_re, expected_re, atol=1e-6)
        assert np.allclose(out_im, expected_im, atol=1e-6)

    def test_ttlang_gather_groups_share_full_batch_ordered_output(self, monkeypatch):
        fake_ttnn = ModuleType("ttnn")
        allocations = []

        def allocate_tensor_on_device(spec, device):
            tensor = SimpleNamespace(spec=spec, device=device)
            allocations.append(tensor)
            return tensor

        def concat(_tensors, *, dim):
            raise AssertionError(f"TT-Lang spectra gather should not concat groups on dim={dim}")

        fake_ttnn.allocate_tensor_on_device = allocate_tensor_on_device
        fake_ttnn.concat = concat
        monkeypatch.setitem(sys.modules, "ttnn", fake_ttnn)

        calls = []

        def make_kernel(label):
            def kernel(_fA_re, _fA_im, _fK_re, _fK_im, out_re, out_im):
                calls.append((label, out_re, out_im))

            return kernel

        stage = object.__new__(TTLangGatherKernelSpectra)
        stage.device = "device"
        stage._groups = [
            SimpleNamespace(start=0, stop=2, kernel=make_kernel("c0"), fK_re="fK0_re", fK_im="fK0_im"),
            SimpleNamespace(start=2, stop=5, kernel=make_kernel("c1"), fK_re="fK1_re", fK_im="fK1_im"),
        ]

        def context(**kwargs):
            assert kwargs == {"batch": 2, "nb_k": 5, "sx": 256, "sy": 256}
            return SimpleNamespace(spec="full_re"), SimpleNamespace(spec="full_im")

        stage._context = context
        out_re, out_im = stage("fA_re", "fA_im", batch=2, channels=2, nb_k=5, sx=256, sy=256)

        assert [call[0] for call in calls] == ["c0", "c1"]
        assert out_re is allocations[0]
        assert out_im is allocations[1]
        assert all(call[1] is out_re and call[2] is out_im for call in calls)


class TestReintegrationStage:
    def test_tiles_to_mass_crops_padding(self):
        pages = np.zeros((8, 32, 32), dtype=np.float32)
        pages[0].fill(1.0)
        pages[1].fill(2.0)
        pages[2].fill(3.0)
        pages[3].fill(4.0)
        reconstructed = _tiles_to_mass(pages, sx=40, sy=48, total_tiles=4)
        assert reconstructed.shape == (40, 48)
        assert np.allclose(reconstructed[:32, :32], 1.0)
        assert np.allclose(reconstructed[:32, 32:48], 2.0)

    def test_matches_ref(self):
        rng = np.random.default_rng(20)
        sx, sy = 32, 32
        mass = np.zeros((1, sx, sy, 1), dtype=np.float32)
        mass[0, 10:22, 10:22, 0] = rng.uniform(0, 1, (12, 12)).astype(np.float32)
        F = rng.uniform(-0.5, 0.5, (1, sx, sy, 2, 1)).astype(np.float32)

        pos_grid_ref = ref.build_pos_grid(sx, sy)
        pos_grid_stage = build_pos_grid(sx, sy)
        assert np.array_equal(pos_grid_ref, pos_grid_stage)

        ref_result = ref.reintegration(
            mass, F, pos_grid=pos_grid_ref, dt=0.2, dd=5, sigma=0.65,
            use_torus=True, sx=sx, sy=sy,
        )
        stage_result = reintegrate(
            mass, F, pos_grid=pos_grid_stage, dt=0.2, dd=5, sigma=0.65,
            use_torus=True, sx=sx, sy=sy,
        )
        assert np.allclose(ref_result, stage_result, atol=1e-6)
