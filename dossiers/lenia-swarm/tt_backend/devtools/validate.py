"""Validation: Swift reference bundle vs reference engine vs TT runtime.

Usage:
    # On Mac: export reference from Swift, then validate the oracle/reference path
    python devtools/validate.py --reference reference/ --backend reference

    # On quietbox: validate TT runtime against the same reference bundle
    python devtools/validate.py --reference reference/ --backend tt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tt_lenia.backends import make_reference_engine, make_runtime_engine
from tt_lenia.config import load_config
from tt_lenia.device import (
    apply_tt_runtime_env,
    close_ttnn_device,
    open_ttnn_device,
    parse_mesh_shape,
    restore_tt_runtime_env,
)
from tt_lenia.reference import load_initial_mass_from_reference, load_kernels_from_reference, load_reference_arrays


TOLERANCES = {
    "reference_vs_swift": 1e-5,
    "runtime_vs_reference": 5e-1,
    "runtime_vs_swift": 5e-1,
    "reference_multi_step": 1e-2,
}


def multi_step_drift_tolerance(backend: str, steps: int) -> float:
    if steps <= 0:
        raise ValueError(f"Expected steps > 0, got {steps}.")
    if backend == "reference":
        return TOLERANCES["reference_multi_step"]
    return TOLERANCES["runtime_vs_reference"] * float(np.sqrt(steps))


def validate_stage(name: str, actual: np.ndarray, expected: np.ndarray, tol: float) -> bool:
    if actual.shape != expected.shape:
        print(f"  FAIL {name}: shape mismatch {actual.shape} vs {expected.shape}")
        return False
    max_diff = np.max(np.abs(actual - expected))
    passed = max_diff < tol
    status = "PASS" if passed else "FAIL"
    print(f"  {status} {name}: max_abs_diff={max_diff:.2e} (tol={tol:.0e})")
    return passed

def validate_reference_vs_swift(ref_dir: Path, config_path: Path) -> bool:
    ref = load_reference_arrays(ref_dir)
    if "mass_in" not in ref:
        print("No Swift reference data found. Export with: lenia-swarm export-reference")
        return False

    config, raw = load_config(config_path)
    kernels = load_kernels_from_reference(ref)

    engine = make_reference_engine(config, kernels)
    result = engine.step(load_initial_mass_from_reference(ref), capture_stages=True)

    tol = TOLERANCES["reference_vs_swift"]
    all_pass = True
    if "mass_out" in ref:
        all_pass &= validate_stage("mass_out", result.mass, ref["mass_out"], tol)
    return all_pass


def make_test_state(config_path: Path):
    from tt_lenia.config import compile_kernels, resolve_connectivity, resolve_params

    config, raw = load_config(config_path)
    c0, c1 = resolve_connectivity(raw)
    params = resolve_params(raw, config.nb_k)
    kernels = compile_kernels(params, config, c0, c1)

    rng = np.random.default_rng(42)
    mass = np.zeros((1, config.sx, config.sy, config.channels), dtype=np.float32)
    mass[0, 44:84, 44:84, :] = rng.uniform(0, 1, (40, 40, config.channels)).astype(np.float32)
    return config, kernels, mass


def make_reference_state(reference_dir: Path, config_path: Path):
    config, _ = load_config(config_path)
    ref = load_reference_arrays(reference_dir)
    kernels = load_kernels_from_reference(ref)
    mass = load_initial_mass_from_reference(ref)
    return config, kernels, mass, ref


def _make_runtime_validation_engine(
    backend: str,
    *,
    config,
    kernels,
    device_id: int,
    visible_devices: str | None,
    mesh_shape: tuple[int, int] | None,
):
    previous_env = apply_tt_runtime_env(visible_device=visible_devices)
    device = None
    try:
        device = open_ttnn_device(
            device_id=device_id,
            mesh_shape=mesh_shape,
        )
        engine = make_runtime_engine(backend, config, kernels, device=device)
        return engine, device, previous_env
    except Exception:
        if device is not None:
            close_ttnn_device(device)
        restore_tt_runtime_env(previous_env)
        raise


def validate_runtime_vs_reference(
    backend: str,
    config_path: Path,
    reference_dir: Path | None = None,
    *,
    device_id: int = 1,
    visible_devices: str | None = None,
    mesh_shape: tuple[int, int] | None = None,
) -> bool:
    if reference_dir is not None:
        config, kernels, mass, ref = make_reference_state(reference_dir, config_path)
    else:
        config, kernels, mass = make_test_state(config_path)
        ref = None

    reference_engine = make_reference_engine(config, kernels)
    runtime_engine, device, previous_env = _make_runtime_validation_engine(
        backend,
        config=config,
        kernels=kernels,
        device_id=device_id,
        visible_devices=visible_devices,
        mesh_shape=mesh_shape,
    )

    try:
        reference_result = reference_engine.step(mass, capture_stages=True)
        runtime_result = runtime_engine.step(mass, capture_stages=True)
    finally:
        close = getattr(runtime_engine, "close", None)
        if callable(close):
            close()
        if device is not None:
            close_ttnn_device(device)
        restore_tt_runtime_env(previous_env)

    tol = TOLERANCES["runtime_vs_reference"]
    all_pass = True
    all_pass &= validate_stage("mass_out", runtime_result.mass, reference_result.mass, tol)
    if ref is not None and "mass_out" in ref:
        all_pass &= validate_stage(
            "reference_mass_out_vs_swift",
            reference_result.mass,
            ref["mass_out"],
            TOLERANCES["reference_vs_swift"],
        )
        all_pass &= validate_stage(
            f"{backend}_mass_out_vs_swift",
            runtime_result.mass,
            ref["mass_out"],
            TOLERANCES["runtime_vs_swift"],
        )
    return all_pass


def main():
    parser = argparse.ArgumentParser(description="Validate TT backend against references")
    parser.add_argument("--reference", type=Path, help="Directory with Swift .npy reference data")
    parser.add_argument("--backend", choices=["reference", "tt"], required=True)
    parser.add_argument("--config", type=Path, default=None, help="Config JSON (defaults to paper_base_3k_1c_128)")
    parser.add_argument("--multi-step", type=int, default=0, help="Run N steps and check drift")
    parser.add_argument(
        "--multi-step-tol",
        type=float,
        default=None,
        help="Override multi-step max-abs drift tolerance. Defaults to backend-aware numerical drift.",
    )
    parser.add_argument("--device-id", type=int, default=1)
    parser.add_argument("--tt-visible-devices", default=None)
    parser.add_argument("--mesh-shape", default=None, help="Explicit TT mesh shape as rows,cols.")
    args = parser.parse_args()

    config_path = args.config
    if config_path is None:
        config_path = Path(__file__).parents[2] / "configs" / "base" / "paper_base_3k_1c_128.json"

    print(f"Validating {args.backend} backend")
    print(f"Config: {config_path}")
    mesh_shape = parse_mesh_shape(args.mesh_shape)

    if args.backend == "reference" and args.reference:
        passed = validate_reference_vs_swift(args.reference, config_path)
    elif args.backend == "tt":
        passed = validate_runtime_vs_reference(
            args.backend,
            config_path,
            reference_dir=args.reference,
            device_id=args.device_id,
            visible_devices=args.tt_visible_devices,
            mesh_shape=mesh_shape,
        )
    else:
        print("For reference validation, provide --reference directory with Swift exports")
        sys.exit(1)

    if args.multi_step > 0:
        print(f"\nMulti-step drift test ({args.multi_step} steps)...")
        if args.reference is not None:
            config, kernels, mass, _ = make_reference_state(args.reference, config_path)
        else:
            config, kernels, mass = make_test_state(config_path)

        reference_engine = make_reference_engine(config, kernels)
        if args.backend == "reference":
            runtime_engine = reference_engine
            runtime_device = None
        else:
            runtime_engine, runtime_device, previous_env = _make_runtime_validation_engine(
                args.backend,
                config=config,
                kernels=kernels,
                device_id=args.device_id,
                visible_devices=args.tt_visible_devices,
                mesh_shape=mesh_shape,
            )

        try:
            reference_result = reference_engine.run(mass, args.multi_step)
            runtime_result = runtime_engine.run(mass, args.multi_step)
            diff = np.abs(reference_result - runtime_result)
            max_diff = np.max(diff)
            mean_diff = np.mean(diff)
            drift_tol = (
                args.multi_step_tol
                if args.multi_step_tol is not None
                else multi_step_drift_tolerance(args.backend, args.multi_step)
            )
            drift_pass = max_diff < drift_tol
            status = "PASS" if drift_pass else "FAIL"
            print(
                f"  {status} {args.multi_step}-step drift: "
                f"max_abs_diff={max_diff:.2e}, mean_abs_diff={mean_diff:.2e} (tol={drift_tol:.0e})"
            )
            passed &= drift_pass
        finally:
            if args.backend != "reference":
                close = getattr(runtime_engine, "close", None)
                if callable(close):
                    close()
                if runtime_device is not None:
                    close_ttnn_device(runtime_device)
                restore_tt_runtime_env(previous_env)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
