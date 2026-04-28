from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import typer

from fly_competency_atlas.paths import artifact_root

LAMINA_APP = typer.Typer(no_args_is_help=True, add_completion=False)

_TOP_LEVEL_ASSETS: tuple[tuple[str, str], ...] = (
    (
        "Cartridge.ipynb",
        "https://raw.githubusercontent.com/FlyBrainLab/Tutorials/master/tutorials/cartridge/Cartridge.ipynb",
    ),
    (
        "cartridge.svg",
        "https://raw.githubusercontent.com/FlyBrainLab/Tutorials/master/tutorials/cartridge/cartridge.svg",
    ),
    (
        "connection.csv",
        "https://raw.githubusercontent.com/FlyBrainLab/Tutorials/master/tutorials/cartridge/connection.csv",
    ),
    (
        "onCartridgeLoad.js",
        "https://raw.githubusercontent.com/FlyBrainLab/Tutorials/master/tutorials/cartridge/onCartridgeLoad.js",
    ),
    (
        "processor_setup.jpg",
        "https://raw.githubusercontent.com/FlyBrainLab/Tutorials/master/tutorials/cartridge/processor_setup.jpg",
    ),
    (
        "update_available_models.js",
        "https://raw.githubusercontent.com/FlyBrainLab/Tutorials/master/tutorials/cartridge/update_available_models.js",
    ),
)
_SWC_API_URL = "https://api.github.com/repos/FlyBrainLab/Tutorials/contents/tutorials/cartridge/swc"
_CAMPAIGN_NAME = "lamina_step_panel_v1"
_RESULT_SCHEMA_VERSION = "lamina_result_v1"


class LaminaError(RuntimeError):
    """Raised when the lamina runner cannot prepare its assets or manifest."""


@dataclass(frozen=True)
class AssetRecord:
    relative_path: str
    source_url: str
    sha256: str
    bytes: int
    materialized: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class InputPattern:
    slug: str
    mode: str
    channel_weights: dict[str, float]
    start_s: float
    stop_s: float
    amplitude: float

    def active_channels(self) -> tuple[str, ...]:
        return tuple(channel for channel, weight in self.channel_weights.items() if weight > 0.0)


@dataclass(frozen=True)
class LesionSpec:
    slug: str
    disabled_neurons: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class LaminaCase:
    case_id: str
    family: str
    input_pattern: str
    lesion_name: str
    disabled_neurons: tuple[str, ...]
    active_channels: tuple[str, ...]
    amplitude: float
    start_s: float
    stop_s: float
    duration_s: float
    dt_s: float
    output_targets: tuple[str, ...]
    metric_slots: tuple[str, ...]
    notes: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CircuitSummary:
    neuron_order: tuple[str, ...]
    neuron_count: int
    edge_count: int
    total_synapse_weight: int
    swc_files: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PlannedRunRecord:
    record_type: str
    schema_version: str
    case_id: str
    family: str
    status: str
    input_pattern: str
    lesion_name: str
    lesion_count: int
    active_channels: tuple[str, ...]
    output_targets: tuple[str, ...]
    metrics: dict[str, float | None]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PreparationResult:
    asset_root: Path
    manifest_path: Path
    planned_runs_path: Path
    asset_count: int
    case_count: int


@LAMINA_APP.command("prepare")
def prepare(
    force: bool = typer.Option(False, "--force", help="Redownload upstream assets."),
) -> None:
    result = prepare_lamina_runner(force=force)
    typer.echo(f"asset_root={result.asset_root}")
    typer.echo(f"manifest={result.manifest_path}")
    typer.echo(f"planned_runs={result.planned_runs_path}")
    typer.echo(f"assets={result.asset_count}")
    typer.echo(f"cases={result.case_count}")


@LAMINA_APP.command("execute")
def execute(
    processor_url: str | None = typer.Option(
        None,
        "--processor-url",
        envvar="FLYBRAINLAB_PROCESSOR_URL",
        help="WAMP processor websocket url for a full FlyBrainLab backend.",
    ),
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        envvar="FLYBRAINLAB_DATASET",
        help="Dataset name exposed by the FFBO processor.",
    ),
    manifest_path: Path | None = typer.Option(
        None,
        "--manifest",
        help="Prepared lamina manifest. If omitted, the default prepared manifest is used.",
    ),
    runtime_python: Path | None = typer.Option(
        None,
        "--runtime-python",
        envvar="FLYBRAINLAB_RUNTIME_PYTHON",
        help="Python interpreter inside the dedicated FlyBrainLab env.",
    ),
    connect_timeout_s: int = typer.Option(20, "--connect-timeout-s"),
    execute_timeout_s: int = typer.Option(180, "--execute-timeout-s"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate and emit dry-run records only.",
    ),
    force_prepare: bool = typer.Option(
        False,
        "--force-prepare",
        help="Refresh assets and manifest first.",
    ),
    case_id: list[str] | None = typer.Option(
        None,
        "--case-id",
        help="Execute only the selected case id.",
    ),
    keep_going: bool = typer.Option(False, "--keep-going", help="Continue after failed cases."),
) -> None:
    if manifest_path is None or force_prepare:
        prepared = prepare_lamina_runner(force=force_prepare)
        manifest_path = prepared.manifest_path
    if manifest_path is None:
        raise LaminaError("manifest path could not be resolved")
    if not manifest_path.exists():
        raise LaminaError(f"manifest does not exist: {manifest_path}")
    if not dry_run and processor_url is None:
        raise LaminaError(
            "processor url is required for execution. The packaged FlyBrainLab default is stale "
            "today, so pass --processor-url for your full backend installation."
        )
    runtime_python = runtime_python or (
        Path(__file__).resolve().parent.parent / ".venv-flybrainlab/bin/python"
    )
    if not runtime_python.exists():
        raise LaminaError(
            f"runtime python does not exist: {runtime_python}. Create it with "
            "./scripts/bootstrap_flybrainlab_user_side.sh /path/to/python3.9 .venv-flybrainlab"
        )
    result = execute_manifest(
        manifest_path=manifest_path,
        runtime_python=runtime_python,
        processor_url=processor_url,
        dataset=dataset,
        connect_timeout_s=connect_timeout_s,
        execute_timeout_s=execute_timeout_s,
        dry_run=dry_run,
        case_ids=tuple(case_id or ()),
        keep_going=keep_going,
    )
    if result.stdout.strip():
        typer.echo(result.stdout.rstrip())
    if result.stderr.strip():
        typer.echo(result.stderr.rstrip(), err=True)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


@LAMINA_APP.command("local-execute")
def local_execute(
    manifest_path: Path | None = typer.Option(
        None,
        "--manifest",
        help="Prepared lamina manifest. If omitted, the default prepared manifest is used.",
    ),
    force_prepare: bool = typer.Option(
        False,
        "--force-prepare",
        help="Refresh assets and manifest first.",
    ),
    case_id: list[str] | None = typer.Option(
        None,
        "--case-id",
        help="Execute only the selected case id.",
    ),
) -> None:
    from fly_competency_atlas.lamina_local import execute_local_manifest

    if manifest_path is None or force_prepare:
        prepared = prepare_lamina_runner(force=force_prepare)
        manifest_path = prepared.manifest_path
    if manifest_path is None:
        raise LaminaError("manifest path could not be resolved")
    if not manifest_path.exists():
        raise LaminaError(f"manifest does not exist: {manifest_path}")
    result = execute_local_manifest(manifest_path=manifest_path, case_ids=tuple(case_id or ()))
    typer.echo("backend=local_linear_v1")
    typer.echo(f"result_path={result.result_path}")
    typer.echo(f"raw_root={result.raw_root}")
    typer.echo(f"cases={result.case_count}")


def prepare_lamina_runner(force: bool = False) -> PreparationResult:
    lamina_root = artifact_root() / "lamina_cartridge"
    upstream_root = lamina_root / "upstream"
    assets = fetch_lamina_assets(upstream_root, force=force)
    circuit = load_circuit_summary(upstream_root / "connection.csv", upstream_root / "swc")
    manifest = build_manifest(upstream_root, assets, circuit)
    cases = cast(list[dict[str, object]], manifest["cases"])
    manifest_path = lamina_root / "manifests" / f"{_CAMPAIGN_NAME}.json"
    planned_runs_path = lamina_root / "results" / f"{_CAMPAIGN_NAME}.ndjson"
    _write_json(manifest_path, manifest)
    _write_ndjson(planned_runs_path, planned_run_records(cases))
    return PreparationResult(
        asset_root=upstream_root,
        manifest_path=manifest_path,
        planned_runs_path=planned_runs_path,
        asset_count=len(assets),
        case_count=len(cases),
    )


def execute_manifest(
    manifest_path: Path,
    runtime_python: Path,
    processor_url: str | None,
    dataset: str | None,
    connect_timeout_s: int,
    execute_timeout_s: int,
    dry_run: bool,
    case_ids: tuple[str, ...],
    keep_going: bool,
) -> subprocess.CompletedProcess[str]:
    command = [
        str(runtime_python),
        "-m",
        "fly_competency_atlas.lamina_runtime",
        "--manifest",
        str(manifest_path),
        "--connect-timeout-s",
        str(connect_timeout_s),
        "--execute-timeout-s",
        str(execute_timeout_s),
    ]
    if processor_url is not None:
        command.extend(["--processor-url", processor_url])
    if dataset is not None:
        command.extend(["--dataset", dataset])
    if dry_run:
        command.append("--dry-run")
    if keep_going:
        command.append("--keep-going")
    for selected_case in case_ids:
        command.extend(["--case-id", selected_case])
    env = os.environ.copy()
    env["PATH"] = f"{runtime_python.parent}{os.pathsep}{env.get('PATH', '')}"
    dossier_root = Path(__file__).resolve().parent.parent
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(dossier_root)
        if not existing_pythonpath
        else f"{dossier_root}{os.pathsep}{existing_pythonpath}"
    )
    return subprocess.run(command, capture_output=True, text=True, env=env)


def fetch_lamina_assets(destination: Path, force: bool = False) -> tuple[AssetRecord, ...]:
    assets: list[AssetRecord] = []
    for relative_path, source_url in _TOP_LEVEL_ASSETS:
        assets.append(_materialize_asset(destination / relative_path, source_url, force=force))
    for relative_path, source_url in _swc_asset_urls():
        assets.append(_materialize_asset(destination / relative_path, source_url, force=force))
    return tuple(assets)


def load_circuit_summary(connection_csv: Path, swc_dir: Path) -> CircuitSummary:
    if not connection_csv.exists():
        raise LaminaError(f"missing connection matrix: {connection_csv}")
    if not swc_dir.exists():
        raise LaminaError(f"missing swc directory: {swc_dir}")
    with connection_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        neuron_order = tuple(header[1:])
        edge_count = 0
        total_synapse_weight = 0
        for row in reader:
            for value in row[1:]:
                weight = int(value)
                if weight <= 0:
                    continue
                edge_count += 1
                total_synapse_weight += weight
    swc_files = tuple(sorted(path.name for path in swc_dir.glob("*.swc")))
    if len(swc_files) != len(neuron_order):
        raise LaminaError(
            f"expected {len(neuron_order)} swc files for cartridge neurons, found {len(swc_files)}"
        )
    return CircuitSummary(
        neuron_order=neuron_order,
        neuron_count=len(neuron_order),
        edge_count=edge_count,
        total_synapse_weight=total_synapse_weight,
        swc_files=swc_files,
    )


def build_manifest(
    upstream_root: Path,
    assets: tuple[AssetRecord, ...],
    circuit: CircuitSummary,
) -> dict[str, object]:
    cases = [case.to_dict() for case in default_cases()]
    return {
        "manifest_version": _CAMPAIGN_NAME,
        "created_at_utc": _utc_now(),
        "asset_root": str(upstream_root),
        "execution_requirements": [
            "activate the dedicated FlyBrainLab env before import",
            "make the FFBO processor/client backend available before execution",
        ],
        "source_urls": {
            "tutorial": "https://github.com/FlyBrainLab/Tutorials/blob/master/tutorials/cartridge/Cartridge.ipynb",
            "connection_matrix": "https://raw.githubusercontent.com/FlyBrainLab/Tutorials/master/tutorials/cartridge/connection.csv",
        },
        "assets": [asset.to_dict() for asset in assets],
        "circuit_summary": circuit.to_dict(),
        "result_schema_version": _RESULT_SCHEMA_VERSION,
        "cases": cases,
    }


def planned_run_records(cases: list[dict[str, object]]) -> tuple[dict[str, object], ...]:
    records = []
    for case in cases:
        metric_slots = _as_string_sequence(case["metric_slots"])
        active_channels = _as_string_sequence(case["active_channels"])
        output_targets = _as_string_sequence(case["output_targets"])
        record = PlannedRunRecord(
            record_type="planned_run",
            schema_version=_RESULT_SCHEMA_VERSION,
            case_id=_as_str(case["case_id"]),
            family=_as_str(case["family"]),
            status="planned",
            input_pattern=_as_str(case["input_pattern"]),
            lesion_name=_as_str(case["lesion_name"]),
            lesion_count=len(_as_string_sequence(case["disabled_neurons"])),
            active_channels=tuple(active_channels),
            output_targets=tuple(output_targets),
            metrics={slot: None for slot in metric_slots},
        )
        records.append(record.to_dict())
    return tuple(records)


def default_cases() -> tuple[LaminaCase, ...]:
    patterns = {pattern.slug: pattern for pattern in default_input_patterns()}
    lesions = {lesion.slug: lesion for lesion in default_lesions()}
    combinations = (
        ("uniform_full_field", "none"),
        ("uniform_full_field", "disable_L2"),
        ("uniform_full_field", "disable_T1"),
        ("uniform_full_field", "disable_a1"),
        ("structured_gradient", "none"),
        ("structured_gradient", "disable_L2"),
        ("structured_gradient", "disable_T1"),
        ("shuffled_gradient_seed_11", "none"),
        ("shuffled_gradient_seed_11", "disable_L2"),
        ("shuffled_gradient_seed_11", "disable_T1"),
        ("single_r1", "none"),
        ("single_r1", "tutorial_r1_path_ablation"),
    )
    return tuple(
        _case(patterns[input_slug], lesions[lesion_slug])
        for input_slug, lesion_slug in combinations
    )


def default_input_patterns() -> tuple[InputPattern, ...]:
    return (
        InputPattern(
            slug="uniform_full_field",
            mode="uniform",
            channel_weights={f"R{i}": 1.0 for i in range(1, 7)},
            start_s=0.5,
            stop_s=1.5,
            amplitude=1e4,
        ),
        InputPattern(
            slug="structured_gradient",
            mode="structured",
            channel_weights={
                "R1": 1.0,
                "R2": 0.8,
                "R3": 0.6,
                "R4": 0.4,
                "R5": 0.2,
                "R6": 0.1,
            },
            start_s=0.5,
            stop_s=1.5,
            amplitude=1e4,
        ),
        InputPattern(
            slug="shuffled_gradient_seed_11",
            mode="shuffled",
            channel_weights={
                "R1": 0.4,
                "R2": 0.1,
                "R3": 1.0,
                "R4": 0.2,
                "R5": 0.8,
                "R6": 0.6,
            },
            start_s=0.5,
            stop_s=1.5,
            amplitude=1e4,
        ),
        InputPattern(
            slug="single_r1",
            mode="single_channel",
            channel_weights={
                "R1": 1.0,
                "R2": 0.0,
                "R3": 0.0,
                "R4": 0.0,
                "R5": 0.0,
                "R6": 0.0,
            },
            start_s=0.5,
            stop_s=1.5,
            amplitude=1e4,
        ),
    )


def default_lesions() -> tuple[LesionSpec, ...]:
    return (
        LesionSpec(slug="none", disabled_neurons=(), rationale="wild_type"),
        LesionSpec(
            slug="disable_L2",
            disabled_neurons=("L2",),
            rationale="local_interneuron_ablation",
        ),
        LesionSpec(
            slug="disable_T1",
            disabled_neurons=("T1",),
            rationale="feedback_channel_ablation",
        ),
        LesionSpec(slug="disable_a1", disabled_neurons=("a1",), rationale="amacrine_path_ablation"),
        LesionSpec(
            slug="tutorial_r1_path_ablation",
            disabled_neurons=(
                "R2",
                "R3",
                "R4",
                "R5",
                "R6",
                "a1",
                "a2",
                "a3",
                "a4",
                "a5",
                "a6",
                "L3",
                "T1",
            ),
            rationale="mirror_the_single_channel_ablation_from_the_upstream_tutorial",
        ),
    )


def _case(pattern: InputPattern, lesion: LesionSpec) -> LaminaCase:
    note = (
        f"input={pattern.mode}; lesion={lesion.rationale}; amplitude={pattern.amplitude}; "
        "result metrics are derived by the selected execution backend"
    )
    return LaminaCase(
        case_id=f"{pattern.slug}__{lesion.slug}",
        family=_CAMPAIGN_NAME,
        input_pattern=pattern.slug,
        lesion_name=lesion.slug,
        disabled_neurons=lesion.disabled_neurons,
        active_channels=pattern.active_channels(),
        amplitude=pattern.amplitude,
        start_s=pattern.start_s,
        stop_s=pattern.stop_s,
        duration_s=2.0,
        dt_s=1e-4,
        output_targets=("R1", "L1"),
        metric_slots=(
            "efficiency_over_blind",
            "lesion_tolerance",
            "reroute_capacity",
            "basin_preservation",
            "structured_vs_noise_gap",
        ),
        notes=note,
    )


def _materialize_asset(destination: Path, source_url: str, force: bool) -> AssetRecord:
    destination.parent.mkdir(parents=True, exist_ok=True)
    materialized = force or not destination.exists()
    if materialized:
        payload = _fetch_bytes(source_url)
        destination.write_bytes(payload)
    else:
        payload = destination.read_bytes()
    return AssetRecord(
        relative_path=str(destination.relative_to(destination.parents[2])),
        source_url=source_url,
        sha256=hashlib.sha256(payload).hexdigest(),
        bytes=len(payload),
        materialized=materialized,
    )


def _swc_asset_urls() -> tuple[tuple[str, str], ...]:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(_SWC_API_URL, headers={"User-Agent": "specter-labs"}),
            timeout=20,
        ) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.URLError as exc:
        raise LaminaError(f"failed to list swc assets: {exc}") from exc
    entries = []
    for item in payload:
        if item.get("type") != "file":
            continue
        download_url = item.get("download_url")
        name = item.get("name")
        if not isinstance(download_url, str) or not isinstance(name, str):
            raise LaminaError("swc asset listing is missing a download url or name")
        entries.append((f"swc/{name}", download_url))
    if not entries:
        raise LaminaError("swc asset listing returned no files")
    return tuple(sorted(entries))


def _fetch_bytes(url: str) -> bytes:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "specter-labs"}),
            timeout=20,
        ) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise LaminaError(f"failed to fetch {url}: {exc}") from exc


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_ndjson(path: Path, records: tuple[dict[str, object], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_str(value: object) -> str:
    if not isinstance(value, str):
        raise LaminaError(f"expected string value, got {type(value).__name__}")
    return value


def _as_string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise LaminaError("expected sequence[str]")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise LaminaError("expected sequence[str]")
        items.append(item)
    return tuple(items)
