from __future__ import annotations

import argparse
import csv
import json
import math
import signal
import sys
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


@dataclass(frozen=True)
class RuntimeArgs:
    manifest: Path
    processor_url: str | None
    dataset: str | None
    connect_timeout_s: int
    execute_timeout_s: int
    dry_run: bool
    case_ids: tuple[str, ...]
    keep_going: bool


class RuntimeErrorWithContext(RuntimeError):
    """Raised when the lamina runtime cannot execute a case or reach the backend."""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = load_manifest(args.manifest)
    cases = filter_cases(as_case_list(manifest["cases"]), args.case_ids)
    result_path = default_result_path(args.manifest)
    raw_root = default_raw_root(args.manifest)
    raw_root.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        records = [dry_run_record(case, args) for case in cases]
        write_ndjson(result_path, records)
        print(
            json.dumps(
                {"status": "dry_run", "result_path": str(result_path), "case_count": len(records)}
            )
        )
        return 0
    if args.processor_url is None:
        raise RuntimeErrorWithContext(
            "processor url is required. The packaged FlyBrainLab default is stale today, "
            "so pass --processor-url for your full backend installation."
        )
    heuristic_probe(args.processor_url)
    client = None
    try:
        client, server_info = connect_client(
            processor_url=args.processor_url,
            dataset=args.dataset,
            connect_timeout_s=args.connect_timeout_s,
        )
        if len(server_info.get("nk", {})) == 0:
            raise RuntimeErrorWithContext(
                "no Neurokernel server is registered on this processor. The upstream README "
                "notes that public user-side backends do not support circuit execution."
            )
        context = build_execution_context(client, manifest)
        records = execute_cases(
            client=client,
            context=context,
            cases=cases,
            raw_root=raw_root,
            args=args,
        )
        write_ndjson(result_path, records)
        failed = [record for record in records if record["status"] != "completed"]
        print(
            json.dumps(
                {
                    "status": "completed" if not failed else "partial_failure",
                    "result_path": str(result_path),
                    "raw_root": str(raw_root),
                    "case_count": len(records),
                    "failed_case_count": len(failed),
                }
            )
        )
        return 0 if not failed else 1
    finally:
        if client is not None:
            try:
                client.client.stop()
            except Exception:
                pass


def parse_args(argv: list[str] | None) -> RuntimeArgs:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--processor-url")
    parser.add_argument("--dataset")
    parser.add_argument("--connect-timeout-s", type=int, default=20)
    parser.add_argument("--execute-timeout-s", type=int, default=180)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--keep-going", action="store_true")
    ns = parser.parse_args(argv)
    return RuntimeArgs(
        manifest=ns.manifest,
        processor_url=ns.processor_url,
        dataset=ns.dataset,
        connect_timeout_s=ns.connect_timeout_s,
        execute_timeout_s=ns.execute_timeout_s,
        dry_run=ns.dry_run,
        case_ids=tuple(ns.case_id),
        keep_going=ns.keep_going,
    )


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def as_case_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeErrorWithContext("manifest cases must be a list of objects")
    return list(value)


def filter_cases(cases: list[dict[str, Any]], selected: tuple[str, ...]) -> list[dict[str, Any]]:
    if not selected:
        return cases
    selected_set = set(selected)
    filtered = [case for case in cases if case.get("case_id") in selected_set]
    missing = selected_set.difference(case["case_id"] for case in filtered)
    if missing:
        raise RuntimeErrorWithContext(f"unknown case ids: {', '.join(sorted(missing))}")
    return filtered


def default_result_path(manifest_path: Path) -> Path:
    return manifest_path.parent.parent / "results" / f"{manifest_path.stem}.ndjson"


def default_raw_root(manifest_path: Path) -> Path:
    return manifest_path.parent.parent / "results" / manifest_path.stem


def dry_run_record(case: dict[str, Any], args: RuntimeArgs) -> dict[str, Any]:
    return {
        "record_type": "lamina_run",
        "schema_version": "lamina_result_v1",
        "status": "dry_run",
        "case_id": as_str(case["case_id"]),
        "family": as_str(case["family"]),
        "processor_url": args.processor_url,
        "dataset": args.dataset,
        "metrics": {slot: None for slot in as_str_list(case["metric_slots"])},
        "raw_output_path": None,
        "output_summary": {},
    }


def heuristic_probe(processor_url: str) -> None:
    import requests

    probe_url = processor_url.replace("wss://", "https://").replace("ws://", "http://")
    try:
        response = requests.get(probe_url, timeout=10)
    except Exception:
        return
    if response.status_code == 404:
        raise RuntimeErrorWithContext(
            f"processor url probe returned 404 for {processor_url}. "
            "The packaged default endpoint is stale today."
        )


def connect_client(
    processor_url: str,
    dataset: str | None,
    connect_timeout_s: int,
) -> tuple[Any, dict[str, Any]]:
    warnings.filterwarnings(
        "ignore",
        message="pkg_resources is deprecated as an API.*",
        category=UserWarning,
    )
    from flybrainlab.Client import Client

    with time_limit(connect_timeout_s, "backend connection timed out"):
        client = Client(
            url=processor_url,
            ssl=processor_url.startswith("wss://"),
            debug=False,
            log_level="warning",
            dataset=dataset,
        )
    server_info = client.rpc("ffbo.processor.server_information")
    return client, server_info


def build_execution_context(client: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    import flybrainlab.circuit as circuit
    import flybrainlab.query as fbl_query
    import pandas as pd

    asset_root = Path(as_str(manifest["asset_root"]))
    runtime_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower()
    data_source_name = f"fly_competency_atlas_lamina_{runtime_id}"
    model_name = f"lamina_step_panel_{runtime_id}"
    model_version = "1.0"
    db = fbl_query.NeuroArch_Mirror(client)
    data_source = db.add_DataSource(
        data_source_name,
        version="1.0",
        url="https://github.com/FlyBrainLab/Tutorials/blob/master/tutorials/cartridge/Cartridge.ipynb",
        description="Fly Competency Atlas lamina cartridge staging model",
    )
    db.select_DataSource(first_rid(data_source))
    db.add_Neuropil("LAM(L)", synonyms=["left lamina"])
    connections = pd.read_csv(asset_root / "connection.csv", index_col=0)
    neuron_order = connections.columns.to_list()
    neuron_rids: list[str] = []
    for neuron in neuron_order:
        swc = load_swc(asset_root / "swc" / f"{neuron}.swc")
        morphology = {
            "x": [value * 0.04 for value in swc["x"]],
            "y": [value * 0.04 for value in swc["y"]],
            "z": [value * 0.04 for value in swc["z"]],
            "r": [value * 0.04 for value in swc["r"]],
            "parent": swc["parent"],
            "identifier": [0] * len(swc["x"]),
            "sample": swc["sample"],
            "type": "swc",
        }
        arborization = [
            {
                "type": "neuropil",
                "dendrites": {"LAM(L)": int(connections.loc[neuron].sum())},
                "axons": {"LAM(L)": int(connections[neuron].sum())},
            }
        ]
        neuron_res = db.add_Neuron(
            neuron,
            neuron,
            referenceId=neuron,
            morphology=morphology,
            arborization=arborization,
        )
        neuron_rids.append(first_rid(neuron_res))
    db.flush_edges()
    adjacency = connections.to_numpy()
    for post_idx, pre_idx in zip(*adjacency.nonzero()):
        pre_neuron = neuron_order[pre_idx]
        post_neuron = neuron_order[post_idx]
        db.add_Synapse(pre_neuron, post_neuron, int(adjacency[post_idx][pre_idx]))
    circuit_query = client.executeNAquery(
        {
            "query": [{"action": {"method": {"query": {}}}, "object": {"rid": neuron_rids}}],
            "format": "nx",
        },
        temp=True,
    )
    executable = circuit.ExecutableCircuit(
        client,
        circuit_query,
        model_name=model_name,
        model_version=model_version,
    )
    executable.initialize_diagram_config(no_send=True)
    configure_models(executable)
    executable.flush_model()
    return {
        "model_name": model_name,
        "model_version": model_version,
        "data_source_name": data_source_name,
    }


def execute_cases(
    client: Any,
    context: dict[str, Any],
    cases: list[dict[str, Any]],
    raw_root: Path,
    args: RuntimeArgs,
) -> list[dict[str, Any]]:
    import flybrainlab.circuit as circuit

    records: list[dict[str, Any]] = []
    for case in cases:
        case_id = as_str(case["case_id"])
        try:
            with time_limit(args.execute_timeout_s, f"case execution timed out: {case_id}"):
                executable = circuit.ExecutableCircuit(
                    client,
                    model_name=as_str(context["model_name"]),
                    model_version=as_str(context["model_version"]),
                )
                disabled = as_str_list(case["disabled_neurons"])
                if disabled:
                    executable.disable_neurons(disabled, no_send=True)
                input_processors = build_input_processors(executable, case)
                output_processors = build_output_processors()
                experiment_name = f"{context['model_name']}/{case_id}"
                executable.execute(
                    input_processors=input_processors,
                    output_processors=output_processors,
                    steps=int(float(case["duration_s"]) / float(case["dt_s"])),
                    dt=float(case["dt_s"]),
                    name=experiment_name,
                )
                result = executable.get_result(experiment_name)
            raw_path = raw_root / f"{case_id}.json"
            raw_payload = jsonable(result)
            raw_path.write_text(
                json.dumps(raw_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            records.append(
                {
                    "record_type": "lamina_run",
                    "schema_version": "lamina_result_v1",
                    "status": "completed",
                    "case_id": case_id,
                    "family": as_str(case["family"]),
                    "processor_url": args.processor_url,
                    "dataset": args.dataset,
                    "model_name": as_str(context["model_name"]),
                    "model_version": as_str(context["model_version"]),
                    "input_pattern": as_str(case["input_pattern"]),
                    "lesion_name": as_str(case["lesion_name"]),
                    "disabled_neurons": disabled,
                    "active_channels": as_str_list(case["active_channels"]),
                    "output_targets": as_str_list(case["output_targets"]),
                    "raw_output_path": str(raw_path),
                    "output_summary": summarize_outputs(
                        raw_payload,
                        as_str_list(case["output_targets"]),
                        float(case["start_s"]),
                        float(case["stop_s"]),
                    ),
                    "metrics": {slot: None for slot in as_str_list(case["metric_slots"])},
                    "completed_at_utc": utc_now(),
                }
            )
        except Exception as exc:
            records.append(
                {
                    "record_type": "lamina_run",
                    "schema_version": "lamina_result_v1",
                    "status": "failed",
                    "case_id": case_id,
                    "family": as_str(case["family"]),
                    "processor_url": args.processor_url,
                    "dataset": args.dataset,
                    "model_name": as_str(context["model_name"]),
                    "model_version": as_str(context["model_version"]),
                    "input_pattern": as_str(case["input_pattern"]),
                    "lesion_name": as_str(case["lesion_name"]),
                    "disabled_neurons": as_str_list(case["disabled_neurons"]),
                    "active_channels": as_str_list(case["active_channels"]),
                    "output_targets": as_str_list(case["output_targets"]),
                    "raw_output_path": None,
                    "output_summary": {},
                    "metrics": {slot: None for slot in as_str_list(case["metric_slots"])},
                    "error": str(exc),
                    "completed_at_utc": utc_now(),
                }
            )
            if not args.keep_going:
                break
    return derive_metrics(records)


def configure_models(executable: Any) -> None:
    photoreceptor_params = {"name": "PhotoreceptorModel", "num_microvilli": 30000}
    executable.update_model("R1", photoreceptor_params, states={"V": -82.0})
    executable.update_model_like([f"R{i}" for i in range(2, 7)], "R1")
    l2_params = {
        "V1": -20.0,
        "V2": 50.0,
        "V3": -40.0,
        "V4": 20.0,
        "phi": 0.1,
        "offset": 0.0,
        "V_L": -40.0,
        "V_Ca": 80.0,
        "V_K": -80.0,
        "g_L": 15.0,
        "g_Ca": 2.0,
        "g_K": 10.0,
        "name": "MorrisLecar",
    }
    executable.update_model("L2", l2_params, states={"V": -46.08, "n": 0.3525})
    executable.update_model_like(
        ["L1", "L3", "L4", "L5", "T1", "C2", "C3", "a1", "a2", "a3", "a4", "a5", "a6"],
        "L2",
    )
    update_models: dict[str, dict[str, Any]] = {}
    for rid, node in executable.get("Synapse").items():
        update_models[node["uname"]] = {
            "params": {
                "name": "SigmoidSynapse",
                "reverse": -80.0 if node["uname"].split("--")[0].startswith("R") else 0.0,
                "threshold": -50.5,
                "slope": 0.05,
                "gmax": 0.04,
                "scale": executable.graph.nodes[rid]["N"],
            },
            "states": {"g": 0.0},
        }
    executable.update_models(update_models)


def build_input_processors(
    executable: Any,
    case: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    processors = []
    weights = pattern_weights(as_str(case["input_pattern"]))
    for channel in as_str_list(case["active_channels"]):
        uid = next(iter(executable.find_model(executable.uname_to_rid[channel]).keys()))
        processors.append(
            {
                "class": "StepInputProcessor",
                "name": f"LAM(L)_{channel}",
                "module": "neurokernel.LPU.InputProcessors.StepInputProcessor",
                "variable": "photon",
                "uids": [uid],
                "val": float(case["amplitude"]) * weights.get(channel, 1.0),
                "start": float(case["start_s"]),
                "stop": float(case["stop_s"]),
                "input_file": f"LAM_input_{case['case_id']}_{channel}.h5",
                "input_interval": 10,
            }
        )
    return {"LAM(L)": processors}


def pattern_weights(pattern: str) -> dict[str, float]:
    weights = {
        "uniform_full_field": {f"R{i}": 1.0 for i in range(1, 7)},
        "structured_gradient": {
            "R1": 1.0,
            "R2": 0.8,
            "R3": 0.6,
            "R4": 0.4,
            "R5": 0.2,
            "R6": 0.1,
        },
        "shuffled_gradient_seed_11": {
            "R1": 0.4,
            "R2": 0.1,
            "R3": 1.0,
            "R4": 0.2,
            "R5": 0.8,
            "R6": 0.6,
        },
        "single_r1": {"R1": 1.0},
    }
    return weights.get(pattern, {})


def build_output_processors() -> dict[str, list[dict[str, Any]]]:
    return {
        "LAM(L)": [
            {
                "class": "Record",
                "uid_dict": {"V": {"uids": None}},
                "sample_interval": 10,
            }
        ]
    }


def summarize_outputs(
    result: dict[str, Any],
    targets: list[str],
    start_s: float,
    stop_s: float,
) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for target in targets:
        target_data = result.get("output", {}).get(target, {}).get("V")
        if not isinstance(target_data, dict):
            continue
        series = [float(value) for value in target_data.get("data", [])]
        dt = float(target_data.get("dt", 0.0))
        summaries[target] = summarize_series(series, dt, start_s, stop_s)
    return summaries


def summarize_series(
    series: list[float],
    dt: float,
    start_s: float,
    stop_s: float,
) -> dict[str, Any]:
    if not series:
        return {"sample_count": 0}
    start_index = min(len(series), max(0, math.floor(start_s / dt))) if dt > 0 else 0
    stop_index = (
        min(len(series), max(start_index, math.ceil(stop_s / dt)))
        if dt > 0
        else len(series)
    )
    stim = series[start_index:stop_index] or series
    return {
        "sample_count": len(series),
        "dt": dt,
        "min": min(series),
        "max": max(series),
        "final": series[-1],
        "stim_mean": sum(stim) / len(stim),
        "stim_peak_abs": max(abs(value) for value in stim),
    }


def derive_metrics(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline_by_pattern: dict[str, float] = {}
    structured_pairs: dict[str, dict[str, float]] = {}
    for record in records:
        if record["status"] != "completed":
            continue
        primary = primary_response(record)
        if primary is None:
            continue
        if record["lesion_name"] == "none":
            baseline_by_pattern[as_str(record["input_pattern"])] = primary
        if as_str(record["input_pattern"]) in {"structured_gradient", "shuffled_gradient_seed_11"}:
            lesion_name = as_str(record["lesion_name"])
            structured_pairs.setdefault(lesion_name, {})[as_str(record["input_pattern"])] = primary
    for record in records:
        metrics = record.get("metrics")
        if not isinstance(metrics, dict) or record["status"] != "completed":
            continue
        primary = primary_response(record)
        if primary is None:
            continue
        baseline = baseline_by_pattern.get(as_str(record["input_pattern"]))
        if baseline not in {None, 0.0}:
            metrics["lesion_tolerance"] = primary / baseline
        lesion_name = as_str(record["lesion_name"])
        pair = structured_pairs.get(lesion_name, {})
        structured = pair.get("structured_gradient")
        shuffled = pair.get("shuffled_gradient_seed_11")
        if structured is not None and shuffled is not None and shuffled != 0.0:
            metrics["structured_vs_noise_gap"] = (structured - shuffled) / abs(shuffled)
    return records


def primary_response(record: dict[str, Any]) -> float | None:
    output_summary = record.get("output_summary")
    if not isinstance(output_summary, dict):
        return None
    l1 = output_summary.get("L1")
    if not isinstance(l1, dict):
        return None
    value = l1.get("stim_peak_abs")
    return float(value) if isinstance(value, (float, int)) else None


def load_swc(path: Path) -> dict[str, list[float | int]]:
    rows: dict[str, list[float | int]] = {
        "sample": [],
        "identifier": [],
        "x": [],
        "y": [],
        "z": [],
        "r": [],
        "parent": [],
    }
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter=" ", skipinitialspace=True)
        for row in reader:
            if not row or row[0].startswith("#"):
                continue
            rows["sample"].append(int(row[0]))
            rows["identifier"].append(int(row[1]))
            rows["x"].append(float(row[2]))
            rows["y"].append(float(row[3]))
            rows["z"].append(float(row[4]))
            rows["r"].append(float(row[5]))
            rows["parent"].append(int(row[6]))
    return rows


def first_rid(payload: Any) -> str:
    if not isinstance(payload, dict) or not payload:
        raise RuntimeErrorWithContext("expected non-empty dict payload from NeuroArch write")
    return next(iter(payload.keys()))


def as_str(value: Any) -> str:
    if not isinstance(value, str):
        raise RuntimeErrorWithContext(f"expected string, got {type(value).__name__}")
    return value


def as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeErrorWithContext("expected list[str]")
    return list(value)


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(inner) for inner in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def write_ndjson(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def time_limit(seconds: int, message: str) -> Iterator[None]:
    if seconds <= 0:
        yield
        return

    def handle_timeout(signum: int, frame: Any) -> None:
        raise RuntimeErrorWithContext(message)

    previous = signal.signal(signal.SIGALRM, handle_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeErrorWithContext as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
