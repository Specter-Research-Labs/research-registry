"""Benchmark TTNN reintegration vs NumPy at 128x128."""
import sys
import time
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tt_lenia.config import compile_kernels, load_config, resolve_connectivity, resolve_params
from tt_lenia.numpy_ref.engine import NumpyFlowLeniaEngine
from tt_lenia.numpy_ref.stages import build_pos_grid, reintegration

config_path = Path(__file__).parents[2] / "configs" / "base" / "paper_base_3k_1c_128.json"
config, raw = load_config(config_path)
c0, c1 = resolve_connectivity(raw)
params = resolve_params(raw, config.nb_k)
kernels = compile_kernels(params, config, c0, c1)

sx, sy = config.sx, config.sy
rng = np.random.default_rng(42)
mass = np.zeros((1, sx, sy, 1), dtype=np.float32)
mass[0, 44:84, 44:84, 0] = rng.uniform(0, 1, (40, 40)).astype(np.float32)
np_engine = NumpyFlowLeniaEngine(config, kernels)
step_out = np_engine.step(mass, capture_stages=True)
U = step_out.u
F = step_out.flow
pos_grid = build_pos_grid(sx, sy)

# NumPy reintegration benchmark
for _ in range(2):
    _ = reintegration(mass, F, pos_grid=pos_grid, dt=config.dt, dd=config.dd,
                      sigma=config.sigma, use_torus=True, sx=sx, sy=sy)

t0 = time.perf_counter()
n_runs = 5
for _ in range(n_runs):
    np_result = reintegration(mass, F, pos_grid=pos_grid, dt=config.dt, dd=config.dd,
                              sigma=config.sigma, use_torus=True, sx=sx, sy=sy)
numpy_ms = (time.perf_counter() - t0) / n_runs * 1000
print("NumPy reintegration: {:.0f}ms".format(numpy_ms))

# TTNN reintegration benchmark
try:
    import ttnn
    from tt_lenia.stages.reintegration_ttnn import reintegrate_ttnn, prepare_reintegration_inputs
    from tt_lenia.stages.fft import _ttnn_to_np

    device = ttnn.open_device(device_id=1)
    inputs = prepare_reintegration_inputs(mass, F, pos_grid, device)

    # Warmup (compiles kernels for each shift)
    print("Warming up TTNN reintegration (121 shift combinations)...")
    _ = reintegrate_ttnn(
        inputs["X"], inputs["F_y"], inputs["F_x"],
        pos_y=inputs["pos_y"], pos_x=inputs["pos_x"],
        dt=config.dt, dd=config.dd, sigma=config.sigma,
        use_torus=True, sx=sx, sy=sy, device=device,
    )
    print("Warmup done")

    t0 = time.perf_counter()
    for _ in range(n_runs):
        tt_result_dev = reintegrate_ttnn(
            inputs["X"], inputs["F_y"], inputs["F_x"],
            pos_y=inputs["pos_y"], pos_x=inputs["pos_x"],
            dt=config.dt, dd=config.dd, sigma=config.sigma,
            use_torus=True, sx=sx, sy=sy, device=device,
        )
    ttnn_ms = (time.perf_counter() - t0) / n_runs * 1000
    tt_result = _ttnn_to_np(tt_result_dev)

    max_diff = np.max(np.abs(tt_result - np_result))
    print("TTNN reintegration: {:.0f}ms".format(ttnn_ms))
    print("Speedup: {:.1f}x".format(numpy_ms / ttnn_ms))
    print("max_diff vs NumPy: {:.2e}".format(max_diff))

    ttnn.close_device(device)
except ImportError:
    print("ttnn not available, skipping TTNN benchmark")

print("DONE")
