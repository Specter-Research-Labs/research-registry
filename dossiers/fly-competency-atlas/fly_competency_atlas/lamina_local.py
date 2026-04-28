from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

_BACKEND_NAME = "local_linear_v1"
_REPLICATE_COUNT = 4
_NULL_ENSEMBLE_COUNT = 4
_DOWNSAMPLE_POINTS = 256


@dataclass(frozen=True)
class LocalExecutionResult:
    result_path: Path
    raw_root: Path
    case_count: int


@dataclass(frozen=True)
class CircuitModel:
    neuron_order: tuple[str, ...]
    weight_matrix: np.ndarray
    receptor_mask: np.ndarray


def execute_local_manifest(
    manifest_path: Path,
    case_ids: tuple[str, ...] = (),
) -> LocalExecutionResult:
    manifest = load_manifest(manifest_path)
    cases = filter_cases(as_case_list(manifest["cases"]), case_ids)
    asset_root = Path(as_str(manifest["asset_root"]))
    circuit = load_circuit(asset_root / "connection.csv")
    result_path = manifest_path.parent.parent / "results" / f"{manifest_path.stem}.local.ndjson"
    raw_root = manifest_path.parent.parent / "results" / f"{manifest_path.stem}.local"
    raw_root.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, Any]] = []
    for case in cases:
        case_output = run_case(circuit, case)
        raw_path = raw_root / f"{as_str(case['case_id'])}.json"
        raw_path.write_text(
            json.dumps(case_output, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        case_output["raw_output_path"] = str(raw_path)
        outputs.append(case_output)
    metrics_by_case = derive_metrics(outputs)
    records = [
        build_record(case_output, metrics_by_case[as_str(case_output["case_id"])])
        for case_output in outputs
    ]
    write_ndjson(result_path, records)
    return LocalExecutionResult(result_path=result_path, raw_root=raw_root, case_count=len(records))


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def as_case_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeError("manifest cases must be a list of objects")
    return list(value)


def filter_cases(cases: list[dict[str, Any]], selected: tuple[str, ...]) -> list[dict[str, Any]]:
    if not selected:
        return cases
    selected_set = set(selected)
    filtered = [case for case in cases if case.get("case_id") in selected_set]
    missing = sorted(selected_set.difference(as_str(case["case_id"]) for case in filtered))
    if missing:
        raise RuntimeError(f"unknown case ids: {', '.join(missing)}")
    return filtered


def load_circuit(connection_csv: Path) -> CircuitModel:
    with connection_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        neuron_order = tuple(header[1:])
        counts = np.array([[float(value) for value in row[1:]] for row in reader], dtype=np.float64)
    if counts.shape[0] != counts.shape[1]:
        raise RuntimeError("lamina connection matrix must be square")
    signs = np.ones_like(counts)
    for pre_idx, neuron in enumerate(neuron_order):
        signs[:, pre_idx] = presynaptic_sign(neuron)
    weights = counts * signs
    spectral_radius = float(np.max(np.abs(np.linalg.eigvals(weights)))) if np.any(weights) else 0.0
    if spectral_radius > 0.0:
        weights *= 0.92 / spectral_radius
    receptor_mask = np.array([name.startswith("R") for name in neuron_order], dtype=bool)
    return CircuitModel(
        neuron_order=neuron_order,
        weight_matrix=weights,
        receptor_mask=receptor_mask,
    )


def presynaptic_sign(neuron: str) -> float:
    # The tutorial connectivity CSV does not encode synapse sign or backend model params,
    # so the local runner uses a small mixed-sign surrogate to keep perturbation responses stable.
    if neuron.startswith("R"):
        return -1.0
    if neuron.startswith("a") or neuron in {"C2", "C3"}:
        return -0.55
    return 0.45


def run_case(circuit: CircuitModel, case: dict[str, Any]) -> dict[str, Any]:
    case_id = as_str(case["case_id"])
    primary_output = primary_output_target(as_str_list(case["output_targets"]))
    replicate_summaries: list[dict[str, Any]] = []
    replicate_vectors: list[np.ndarray] = []
    family_counts: dict[str, int] = {}
    downsampled_reference: dict[str, list[float]] | None = None
    target_series_reference: dict[str, list[float]] | None = None
    for replicate_index in range(_REPLICATE_COUNT):
        seed = case_seed(case_id, replicate_index)
        simulation = simulate_case(circuit, case, seed=seed, weight_matrix=circuit.weight_matrix)
        summary = summarize_simulation(circuit, case, simulation, primary_output)
        replicate_summaries.append(summary)
        replicate_vectors.append(np.asarray(summary["response_vector"], dtype=np.float64))
        family = as_str(summary["family"])
        family_counts[family] = family_counts.get(family, 0) + 1
        if downsampled_reference is None:
            downsampled_reference = simulation["downsampled"]
            target_series_reference = simulation["target_series"]
    null_scores = [
        summarize_simulation(
            circuit,
            case,
            simulate_case(
                circuit,
                case,
                seed=case_seed(case_id, 100 + null_index),
                weight_matrix=null_weight_matrix(
                    circuit.weight_matrix,
                    case_seed(case_id, 1000 + null_index),
                ),
            ),
            primary_output,
        )["primary_score"]
        for null_index in range(_NULL_ENSEMBLE_COUNT)
    ]
    dominant_family, dominant_fraction = dominant_family_stats(family_counts)
    aggregate_targets = aggregate_target_summaries(replicate_summaries)
    response_vector = np.mean(np.stack(replicate_vectors), axis=0)
    return {
        "backend": _BACKEND_NAME,
        "case_id": case_id,
        "family": as_str(case["family"]),
        "input_pattern": as_str(case["input_pattern"]),
        "lesion_name": as_str(case["lesion_name"]),
        "disabled_neurons": as_str_list(case["disabled_neurons"]),
        "active_channels": as_str_list(case["active_channels"]),
        "output_targets": as_str_list(case["output_targets"]),
        "simulation_config": {
            "replicate_count": _REPLICATE_COUNT,
            "null_ensemble_count": _NULL_ENSEMBLE_COUNT,
            "downsample_points": _DOWNSAMPLE_POINTS,
            "duration_s": float(case["duration_s"]),
            "dt_s": float(case["dt_s"]),
        },
        "dominant_family": dominant_family,
        "dominant_fraction": dominant_fraction,
        "family_counts": family_counts,
        "neuron_order": list(circuit.neuron_order),
        "aggregate_targets": aggregate_targets,
        "primary_output": primary_output,
        "primary_score": float(aggregate_targets[primary_output]["window_abs_integral"]),
        "null_scores": [float(value) for value in null_scores],
        "null_median_score": float(np.median(np.asarray(null_scores, dtype=np.float64))),
        "response_vector": [float(value) for value in response_vector],
        "internal_response_digest": response_digest(circuit, response_vector),
        "replicate_summaries": replicate_summaries,
        "downsampled": downsampled_reference or {},
        "target_series": target_series_reference or {},
    }


def simulate_case(
    circuit: CircuitModel,
    case: dict[str, Any],
    *,
    seed: int,
    weight_matrix: np.ndarray,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    neuron_to_index = {name: index for index, name in enumerate(circuit.neuron_order)}
    active_mask = np.ones(len(circuit.neuron_order), dtype=np.float64)
    for neuron in as_str_list(case["disabled_neurons"]):
        active_mask[neuron_to_index[neuron]] = 0.0
    effective_weights = weight_matrix * active_mask[:, None] * active_mask[None, :]
    duration_s = float(case["duration_s"])
    dt_s = float(case["dt_s"])
    steps = int(round(duration_s / dt_s))
    start_step = int(round(float(case["start_s"]) / dt_s))
    stop_step = int(round(float(case["stop_s"]) / dt_s))
    taus = np.where(circuit.receptor_mask, 0.02, 0.05)
    external = np.zeros(len(circuit.neuron_order), dtype=np.float64)
    amplitude_scale = float(case["amplitude"]) / 1e4
    for neuron in as_str_list(case["active_channels"]):
        external[neuron_to_index[neuron]] = amplitude_scale
    state = rng.normal(0.0, 0.01, len(circuit.neuron_order)) * active_mask
    downsample_stride = max(1, steps // _DOWNSAMPLE_POINTS)
    tracked_neurons = [name for name in tracked_targets(case) if name in neuron_to_index]
    tracked_indices = [neuron_to_index[name] for name in tracked_neurons]
    target_names = as_str_list(case["output_targets"])
    target_indices = [neuron_to_index[name] for name in target_names]
    time_s: list[float] = []
    downsampled = {name: [] for name in tracked_neurons}
    target_series = {name: [] for name in target_names}
    window_integral = np.zeros(len(target_names), dtype=np.float64)
    window_peak_abs = np.zeros(len(target_names), dtype=np.float64)
    response_vector = np.zeros(len(circuit.neuron_order), dtype=np.float64)
    window_count = 0
    for step in range(steps):
        drive = external if start_step <= step < stop_step else 0.0
        noise = rng.normal(0.0, 0.015, len(circuit.neuron_order))
        target_state = np.tanh(effective_weights @ state + drive + noise)
        state = state + (dt_s / taus) * (-state + target_state)
        state *= active_mask
        if step % downsample_stride == 0:
            time_s.append(step * dt_s)
            for name, index in zip(tracked_neurons, tracked_indices):
                downsampled[name].append(float(state[index]))
        if start_step <= step < stop_step:
            response_vector += state
            window_count += 1
            for target_name, target_index in zip(target_names, target_indices):
                value = float(state[target_index])
                window_integral[target_names.index(target_name)] += value * dt_s
                window_peak_abs[target_names.index(target_name)] = max(
                    window_peak_abs[target_names.index(target_name)],
                    abs(value),
                )
                target_series[target_name].append(value)
    if window_count == 0:
        raise RuntimeError("simulation window cannot be empty")
    response_vector /= window_count
    return {
        "time_s": time_s,
        "downsampled": downsampled,
        "target_series": target_series,
        "window_integral": {
            name: float(window_integral[index]) for index, name in enumerate(target_names)
        },
        "window_peak_abs": {
            name: float(window_peak_abs[index]) for index, name in enumerate(target_names)
        },
        "response_vector": response_vector,
    }


def tracked_targets(case: dict[str, Any]) -> list[str]:
    tracked = ["R1", "L1", "L2", "T1"]
    for name in as_str_list(case["output_targets"]):
        if name not in tracked:
            tracked.append(name)
    return tracked


def summarize_simulation(
    circuit: CircuitModel,
    case: dict[str, Any],
    simulation: dict[str, Any],
    primary_output: str,
) -> dict[str, Any]:
    target_names = as_str_list(case["output_targets"])
    target_summaries = {
        name: {
            "window_integral": float(simulation["window_integral"][name]),
            "window_abs_integral": float(abs(simulation["window_integral"][name])),
            "peak_abs": float(simulation["window_peak_abs"][name]),
        }
        for name in target_names
    }
    primary_score = target_summaries[primary_output]["window_abs_integral"]
    return {
        "target_summaries": target_summaries,
        "primary_score": float(primary_score),
        "family": classify_family(
            primary_score,
            float(target_summaries[primary_output]["window_integral"]),
        ),
        "response_vector": [float(value) for value in np.asarray(simulation["response_vector"])],
        "internal_response_digest": response_digest(
            circuit, np.asarray(simulation["response_vector"], dtype=np.float64)
        ),
    }


def classify_family(primary_score: float, signed_integral: float) -> str:
    if primary_score < 0.01:
        band = "low"
    elif primary_score < 0.05:
        band = "mid"
    else:
        band = "high"
    sign = "pos" if signed_integral >= 0.0 else "neg"
    return f"{sign}:{band}"


def response_digest(circuit: CircuitModel, response_vector: np.ndarray) -> dict[str, float]:
    return {
        name: round(float(response_vector[index]), 6)
        for index, name in enumerate(circuit.neuron_order)
        if name in {"R1", "L1", "L2", "T1", "a1"}
    }


def dominant_family_stats(family_counts: dict[str, int]) -> tuple[str, float]:
    dominant_family = max(sorted(family_counts), key=lambda name: family_counts[name])
    total = sum(family_counts.values())
    return dominant_family, family_counts[dominant_family] / total


def aggregate_target_summaries(
    replicate_summaries: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    target_names = replicate_summaries[0]["target_summaries"].keys()
    aggregate: dict[str, dict[str, float]] = {}
    for name in target_names:
        integrals = np.array(
            [
                float(summary["target_summaries"][name]["window_integral"])
                for summary in replicate_summaries
            ],
            dtype=np.float64,
        )
        peak_abs = np.array(
            [
                float(summary["target_summaries"][name]["peak_abs"])
                for summary in replicate_summaries
            ],
            dtype=np.float64,
        )
        aggregate[name] = {
            "window_integral": float(np.median(integrals)),
            "window_abs_integral": float(np.median(np.abs(integrals))),
            "peak_abs": float(np.median(peak_abs)),
        }
    return aggregate


def null_weight_matrix(weight_matrix: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    nonzero_positions = np.argwhere(weight_matrix != 0.0)
    values = weight_matrix[weight_matrix != 0.0]
    permuted_positions = nonzero_positions[rng.permutation(len(nonzero_positions))]
    permuted_values = values[rng.permutation(len(values))]
    null_weights = np.zeros_like(weight_matrix)
    for position, value in zip(permuted_positions, permuted_values):
        null_weights[tuple(position)] = value
    return null_weights


def derive_metrics(outputs: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    baseline_lookup = {
        (as_str(output["input_pattern"]), "none"): output
        for output in outputs
        if as_str(output["lesion_name"]) == "none"
    }
    structured_lookup = {
        as_str(output["lesion_name"]): output
        for output in outputs
        if as_str(output["input_pattern"]) == "structured_gradient"
    }
    shuffled_lookup = {
        as_str(output["lesion_name"]): output
        for output in outputs
        if as_str(output["input_pattern"]) == "shuffled_gradient_seed_11"
    }
    metrics_by_case: dict[str, dict[str, float | None]] = {}
    for output in outputs:
        case_id = as_str(output["case_id"])
        primary_output = as_str(output["primary_output"])
        primary_score = float(output["primary_score"])
        null_median = float(output["null_median_score"])
        baseline = baseline_lookup.get((as_str(output["input_pattern"]), "none"))
        lesion_tolerance = None
        reroute_capacity = None
        basin_preservation = None
        if baseline is not None:
            baseline_score = float(baseline["primary_score"])
            lesion_tolerance = safe_ratio(primary_score, baseline_score)
            basin_preservation = family_distribution_similarity(output, baseline)
            if as_str(output["lesion_name"]) != "none":
                divergence = internal_divergence(
                    output,
                    baseline,
                    primary_output,
                    as_str_list(output["active_channels"]),
                )
                reroute_capacity = min(max(lesion_tolerance or 0.0, 0.0), 1.0) * divergence
            else:
                reroute_capacity = 0.0
        structured_vs_noise_gap = None
        lesion_name = as_str(output["lesion_name"])
        input_pattern = as_str(output["input_pattern"])
        if (
            input_pattern in {"structured_gradient", "shuffled_gradient_seed_11"}
            and lesion_name in structured_lookup
            and lesion_name in shuffled_lookup
        ):
            structured_score = float(structured_lookup[lesion_name]["primary_score"])
            shuffled_score = float(shuffled_lookup[lesion_name]["primary_score"])
            structured_vs_noise_gap = safe_ratio(structured_score - shuffled_score, shuffled_score)
        metrics_by_case[case_id] = {
            "efficiency_over_blind": safe_ratio(primary_score, null_median) - 1.0,
            "lesion_tolerance": lesion_tolerance,
            "reroute_capacity": reroute_capacity,
            "basin_preservation": basin_preservation,
            "structured_vs_noise_gap": structured_vs_noise_gap,
        }
    return metrics_by_case


def build_record(case_output: dict[str, Any], metrics: dict[str, float | None]) -> dict[str, Any]:
    return {
        "record_type": "lamina_run",
        "schema_version": "lamina_result_v1",
        "status": "completed",
        "execution_backend": _BACKEND_NAME,
        "case_id": as_str(case_output["case_id"]),
        "family": as_str(case_output["family"]),
        "processor_url": None,
        "dataset": None,
        "model_name": _BACKEND_NAME,
        "model_version": "1.0",
        "input_pattern": as_str(case_output["input_pattern"]),
        "lesion_name": as_str(case_output["lesion_name"]),
        "disabled_neurons": as_str_list(case_output["disabled_neurons"]),
        "active_channels": as_str_list(case_output["active_channels"]),
        "output_targets": as_str_list(case_output["output_targets"]),
        "raw_output_path": as_str(case_output["raw_output_path"]),
        "output_summary": {
            "backend": _BACKEND_NAME,
            "dominant_family": as_str(case_output["dominant_family"]),
            "dominant_fraction": float(case_output["dominant_fraction"]),
            "aggregate_targets": case_output["aggregate_targets"],
            "primary_output": as_str(case_output["primary_output"]),
            "primary_score": float(case_output["primary_score"]),
            "null_median_score": float(case_output["null_median_score"]),
        },
        "metrics": metrics,
    }


def family_distribution_similarity(
    case_output: dict[str, Any],
    baseline_output: dict[str, Any],
) -> float:
    keys = set(case_output["family_counts"]).union(baseline_output["family_counts"])
    case_total = sum(case_output["family_counts"].values())
    baseline_total = sum(baseline_output["family_counts"].values())
    total_variation = 0.0
    for key in keys:
        case_prob = case_output["family_counts"].get(key, 0) / case_total
        baseline_prob = baseline_output["family_counts"].get(key, 0) / baseline_total
        total_variation += abs(case_prob - baseline_prob)
    return max(0.0, 1.0 - 0.5 * total_variation)


def internal_divergence(
    case_output: dict[str, Any],
    baseline_output: dict[str, Any],
    primary_output: str,
    active_channels: list[str],
) -> float:
    case_vector = np.asarray(case_output["response_vector"], dtype=np.float64)
    baseline_vector = np.asarray(baseline_output["response_vector"], dtype=np.float64)
    ignore = set(active_channels)
    ignore.add(primary_output)
    neuron_order = [as_str(name) for name in case_output["neuron_order"]]
    keep = np.ones(len(case_vector), dtype=bool)
    for index, name in enumerate(neuron_order):
        if name in ignore:
            keep[index] = False
    if not np.any(keep):
        return 0.0
    numerator = float(np.mean(np.abs(case_vector[keep] - baseline_vector[keep])))
    denominator = float(np.mean(np.abs(baseline_vector[keep]))) + 1e-9
    return min(1.0, numerator / denominator)


def primary_output_target(output_targets: list[str]) -> str:
    if "L1" in output_targets:
        return "L1"
    return output_targets[0]


def safe_ratio(numerator: float, denominator: float) -> float:
    scale = abs(denominator) + 1e-9
    return numerator / scale


def case_seed(case_id: str, salt: int) -> int:
    payload = f"{case_id}:{salt}".encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:16], 16) % (2**32)


def write_ndjson(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")


def as_str(value: Any) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"expected string, received {type(value).__name__}")
    return value


def as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError("expected list of strings")
    return list(value)
