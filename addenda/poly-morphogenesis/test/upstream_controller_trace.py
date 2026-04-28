#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import sys
import types
from pathlib import Path

import numpy as np


class StopTrace(Exception):
    pass


def _poly_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _stub_modules() -> None:
    noop = lambda *args, **kwargs: None

    eplot = types.ModuleType("eplot")
    eplot.plot_worm = noop
    eplot.plot_ion = noop
    eplot.plot_worm_times = noop
    eplot.plot_Vmem = noop
    eplot.plot_onecell = noop
    sys.modules["eplot"] = eplot

    edebug = types.ModuleType("edebug")
    edebug.dump = noop
    edebug.Units = types.SimpleNamespace(
        mol_per_m3s="mol_per_m3s",
        mol_per_m2s="mol_per_m2s",
        mV_per_s="mV_per_s",
    )
    sys.modules["edebug"] = edebug


def _strip_top_level_run(tree: ast.Module) -> ast.Module:
    body = list(tree.body)
    if body and isinstance(body[-1], ast.Expr) and isinstance(body[-1].value, ast.Call):
        call = body[-1].value
        if isinstance(call.func, ast.Name) and call.func.id == "run_counting_GRN":
            body = body[:-1]
    return ast.Module(body=body, type_ignores=[])


def _load_grn_count1():
    root = _poly_root() / "upstream" / "bitsey"
    rd_root = root / "RD"
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(rd_root))
    _stub_modules()

    source_path = rd_root / "grn_count1.py"
    tree = ast.parse(source_path.read_text(), filename=str(source_path))
    tree = _strip_top_level_run(tree)

    module = types.ModuleType("grn_count1_oracle")
    module.__file__ = str(source_path)
    exec(compile(tree, module.__file__, "exec"), module.__dict__)
    return module


def _active_pre_indices(head_pre: np.ndarray) -> list[int]:
    return np.flatnonzero(head_pre > 0.6).astype(int).tolist()


def _source_diffusion(sim_module, ion_idx: int) -> float:
    if sim_module.GJ_diffusion.shape[1] == 0:
        return 0.0
    return float(sim_module.GJ_diffusion[ion_idx, 0])


def run_controller_trace(n_cells: int, goal_peaks: int, n_peaks_max: int, max_loops: int | None):
    module = _load_grn_count1()

    import sim
    import werner_common as wc

    original_sim = sim.sim
    original_linear_spread = wc.linear_spread
    original_set_pre_decay_fast = module.set_pre_decay_fast
    original_set_pre_decay_normal = module.set_pre_decay_normal
    original_GRN_N_peaks = module.GRN_N_peaks

    history: list[dict[str, object]] = []
    current_loop: dict[str, object] | None = None
    loop_index = 0
    previous_peak_count = 0.0
    phase = "rd"

    def ensure_loop() -> dict[str, object]:
        nonlocal current_loop
        if current_loop is None:
            current_loop = {
                "loop_index": loop_index,
                "previous_peak_count": previous_peak_count,
                "controller_action": "increase",
                "linear_spread_applied": False,
            }
        return current_loop

    def wrapped_linear_spread():
        record = ensure_loop()
        record["controller_action"] = "decrease"
        record["linear_spread_applied"] = True
        return original_linear_spread()

    def wrapped_set_pre_decay_fast():
        record = ensure_loop()
        record["rd_pre_decay"] = 10.0
        return original_set_pre_decay_fast()

    def wrapped_set_pre_decay_normal():
        record = ensure_loop()
        record["grn_pre_decay"] = 1.0
        return original_set_pre_decay_normal()

    def wrapped_sim(end_time):
        nonlocal phase

        record = ensure_loop()
        A = sim.ion_i["A"]
        I = sim.ion_i["I"]
        pre_start = sim.ion_i["pre0L"]

        if phase == "rd":
            record["rd_duration"] = float(end_time)
            record["D_a"] = _source_diffusion(sim, A)
            record["D_i"] = _source_diffusion(sim, I)
            result = original_sim(end_time)
            record["rd_A_profile"] = sim.cc_cells[A].astype(float).tolist()
            record["rd_I_profile"] = sim.cc_cells[I].astype(float).tolist()
            record["shape_after_rd"] = module.wc.shape()
            phase = "grn"
            return result

        record["seed_pre0l"] = float(sim.cc_cells[pre_start, 0])
        record["grn_duration"] = float(end_time)
        result = original_sim(end_time)
        head_pre = sim.cc_cells[pre_start : pre_start + 2 * n_peaks_max, -1].astype(float)
        record["head_pre"] = head_pre.tolist()
        record["active_pre_indices"] = _active_pre_indices(head_pre)
        record["highest_pre_on"] = (
            record["active_pre_indices"][-1] if record["active_pre_indices"] else None
        )
        phase = "rd"
        return result

    def wrapped_GRN_N_peaks(pre_start: int, n_max: int):
        nonlocal current_loop, loop_index, previous_peak_count

        n_peaks = float(original_GRN_N_peaks(pre_start, n_max))
        record = ensure_loop()
        record["n_peaks"] = n_peaks
        record["source_should_continue"] = (n_peaks != goal_peaks) or ((loop_index + 1) <= 8)
        history.append(dict(record))
        loop_index += 1
        previous_peak_count = n_peaks
        current_loop = None
        if max_loops is not None and loop_index >= max_loops:
            raise StopTrace()
        return n_peaks

    wc.linear_spread = wrapped_linear_spread
    module.set_pre_decay_fast = wrapped_set_pre_decay_fast
    module.set_pre_decay_normal = wrapped_set_pre_decay_normal
    sim.sim = wrapped_sim
    module.GRN_N_peaks = wrapped_GRN_N_peaks

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                module.run_counting_GRN(
                    n_cells=n_cells,
                    n_peaks_max=n_peaks_max,
                    goal_n_peaks=goal_peaks,
                )
            except StopTrace:
                pass
    finally:
        wc.linear_spread = original_linear_spread
        module.set_pre_decay_fast = original_set_pre_decay_fast
        module.set_pre_decay_normal = original_set_pre_decay_normal
        sim.sim = original_sim
        module.GRN_N_peaks = original_GRN_N_peaks

    return {
        "n_cells": n_cells,
        "goal_peaks": goal_peaks,
        "n_peaks_max": n_peaks_max,
        "history": history,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-cells", type=int, required=True)
    parser.add_argument("--goal-peaks", type=int, required=True)
    parser.add_argument("--n-peaks-max", type=int, required=True)
    parser.add_argument("--max-loops", type=int)
    args = parser.parse_args()

    trace = run_controller_trace(args.n_cells, args.goal_peaks, args.n_peaks_max, args.max_loops)
    json.dump(trace, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
