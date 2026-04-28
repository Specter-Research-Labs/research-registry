from __future__ import annotations

import base64
import copy
import json
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class CandidateSpecimen:
    run_id: str
    campaign_id: str
    specimen_id: str
    seed: int
    dominant_order: int | None
    dominant_amplitude: float | None
    source_export_dir: Path
    source_meta: dict[str, Any]
    payload: dict[str, Any]
    baseline_fingerprint: np.ndarray


@dataclass(frozen=True)
class CandidatePair:
    rank: int
    row: dict[str, Any]
    specimen_a: CandidateSpecimen
    specimen_b: CandidateSpecimen


@dataclass(frozen=True)
class ReplayOutcome:
    name: str
    run_id: str
    run_dir: Path
    returncode: int
    stdout_tail: str
    stderr_tail: str
    results_path: Path | None
    fingerprint: np.ndarray | None
    dominant_order: int | None
    dominant_amplitude: float | None


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise SystemExit(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")


def sanitize(value: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "fiber"


def fingerprint_from_result(result: dict[str, Any]) -> np.ndarray:
    bundle = result.get("descriptor_bundle")
    terminal = bundle.get("terminal") if isinstance(bundle, dict) else None
    fingerprint = terminal.get("fingerprintU8") if isinstance(terminal, dict) else None
    if isinstance(fingerprint, list):
        return np.asarray([float(value) / 255.0 for value in fingerprint], dtype=np.float64)
    if isinstance(fingerprint, str):
        decoded = np.frombuffer(base64.b64decode(fingerprint), dtype=np.uint8)
        return decoded.astype(np.float64) / 255.0
    raise SystemExit("Result is missing descriptor_bundle.terminal.fingerprintU8")


def l2_distance(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(left - right))


def extract_result_metrics(result: dict[str, Any]) -> tuple[np.ndarray, int | None, float | None]:
    fingerprint = fingerprint_from_result(result)
    bundle = result.get("descriptor_bundle")
    terminal = bundle.get("terminal") if isinstance(bundle, dict) else None
    angular = terminal.get("angularSymmetry") if isinstance(terminal, dict) else None
    if not isinstance(angular, dict):
        return fingerprint, None, None
    dominant_order = angular.get("dominantOrder")
    dominant_amplitude = angular.get("dominantAmplitude")
    return (
        fingerprint,
        int(dominant_order) if isinstance(dominant_order, (int, float)) else None,
        float(dominant_amplitude) if isinstance(dominant_amplitude, (int, float)) else None,
    )


def qd_kernel_count(payload: dict[str, Any]) -> int:
    pattern = payload.get("pattern")
    kernels = pattern.get("kernels") if isinstance(pattern, dict) else None
    if not isinstance(kernels, list) or not kernels:
        raise SystemExit("qd payload pattern.kernels must be a non-empty list")
    return len(kernels)


def qd_param_count(payload: dict[str, Any]) -> int:
    base = payload.get("base")
    n_params_size = base.get("n_params_size") if isinstance(base, dict) else None
    if not isinstance(n_params_size, int) or n_params_size <= 0:
        raise SystemExit("qd payload base.n_params_size must be a positive integer")
    return n_params_size * qd_kernel_count(payload)


def qd_genotype(payload: dict[str, Any]) -> np.ndarray:
    elite = payload.get("elite")
    genotype = elite.get("genotype") if isinstance(elite, dict) else None
    if not isinstance(genotype, list) or not genotype:
        raise SystemExit("qd payload elite.genotype must be a non-empty list")
    return np.asarray(genotype, dtype=np.float64)


def set_qd_genotype(payload: dict[str, Any], genotype: np.ndarray, *, cell_seed: int) -> dict[str, Any]:
    mutated = copy.deepcopy(payload)
    elite = mutated.get("elite")
    if not isinstance(elite, dict):
        raise SystemExit("qd payload is missing elite")
    elite["genotype"] = genotype.astype(float).tolist()
    elite["cell"] = int(cell_seed)
    elite["descriptor"] = []
    elite["centroid"] = []
    elite["generation"] = -1
    return mutated


def resolve_library_source_export_dir(
    library_row: dict[str, Any],
    *,
    campaign_dir: Path,
) -> Path:
    manifest = library_row.get("specimen_manifest")
    manifest_dict = manifest if isinstance(manifest, dict) else {}
    research_metadata = manifest_dict.get("researchMetadata")
    metadata = (
        research_metadata
        if isinstance(research_metadata, dict)
        else library_row.get("research_metadata")
    )
    if not isinstance(metadata, dict):
        metadata = {}

    source_export_dir = metadata.get("source_export_dir")
    if not isinstance(source_export_dir, str):
        replay = manifest_dict.get("replay")
        if isinstance(replay, dict):
            source_export_dir = replay.get("exportDir")
    if not isinstance(source_export_dir, str):
        raise SystemExit(
            f"{campaign_dir}: missing canonical source export dir in specimen_manifest or research_metadata"
        )
    return Path(source_export_dir)


def interpolate_payload(specimen_a: CandidateSpecimen, specimen_b: CandidateSpecimen, alpha: float) -> dict[str, Any]:
    genotype_a = qd_genotype(specimen_a.payload)
    genotype_b = qd_genotype(specimen_b.payload)
    if genotype_a.shape != genotype_b.shape:
        raise SystemExit("candidate pair genotypes have mismatched shapes")
    genotype = (1.0 - alpha) * genotype_a + alpha * genotype_b
    return set_qd_genotype(specimen_a.payload, genotype, cell_seed=specimen_a.seed)


def perturb_midpoint_payload(
    midpoint_payload: dict[str, Any],
    *,
    variant_name: str,
    param_delta: float,
    random_scale: float,
) -> dict[str, Any]:
    genotype = qd_genotype(midpoint_payload)
    param_count = qd_param_count(midpoint_payload)
    kernel_count = qd_kernel_count(midpoint_payload)
    param_segment = genotype[:param_count].copy()

    if variant_name == "midpoint":
        pass
    elif variant_name == "delta-p010":
        param_segment[:kernel_count] = np.clip(
            param_segment[:kernel_count] + param_delta,
            0.0,
            1.0,
        )
    elif variant_name == "delta-m010":
        param_segment[:kernel_count] = np.clip(
            param_segment[:kernel_count] - param_delta,
            0.0,
            1.0,
        )
    elif variant_name in {"rand1-p005", "rand1-m005", "rand2-p005", "rand2-m005"}:
        basis_seed = 1 if "rand1" in variant_name else 2
        direction = 1.0 if variant_name.endswith("p005") else -1.0
        rng = np.random.default_rng(basis_seed)
        noise = rng.normal(size=param_count)
        norm = float(np.linalg.norm(noise))
        if norm == 0:
            raise SystemExit("random perturbation basis produced zero norm")
        param_segment = np.clip(param_segment + direction * random_scale * (noise / norm), 0.0, 1.0)
    else:
        raise SystemExit(f"Unsupported midpoint variant: {variant_name}")

    genotype[:param_count] = param_segment
    elite = midpoint_payload.get("elite")
    cell_seed = elite.get("cell") if isinstance(elite, dict) else None
    if not isinstance(cell_seed, int):
        raise SystemExit("midpoint payload is missing elite.cell")
    return set_qd_genotype(midpoint_payload, genotype, cell_seed=cell_seed)


def load_specimen(side: dict[str, Any], replay_root: Path) -> CandidateSpecimen:
    specimen_id = side.get("specimenId")
    run_id = side.get("runId")
    campaign_id = side.get("campaignId")
    seed = side.get("seed")
    if (
        not isinstance(specimen_id, str)
        or not isinstance(run_id, str)
        or not isinstance(campaign_id, str)
        or not isinstance(seed, int)
    ):
        raise SystemExit("candidate specimen is missing specimenId/runId/campaignId/seed")

    replay_campaign_dir = replay_root / run_id / "campaigns" / campaign_id
    library_rows = read_jsonl(replay_campaign_dir / "library/index.jsonl")
    if len(library_rows) != 1:
        raise SystemExit(f"{replay_campaign_dir}: expected exactly one library row")
    export_dir = resolve_library_source_export_dir(
        library_rows[0],
        campaign_dir=replay_campaign_dir,
    )

    result_rows = read_jsonl(replay_campaign_dir / "results.jsonl")
    if len(result_rows) != 1:
        raise SystemExit(f"{replay_campaign_dir}: expected exactly one result row")
    baseline_fingerprint, dominant_order, dominant_amplitude = extract_result_metrics(result_rows[0])
    return CandidateSpecimen(
        run_id=run_id,
        campaign_id=campaign_id,
        specimen_id=specimen_id,
        seed=seed,
        dominant_order=dominant_order,
        dominant_amplitude=dominant_amplitude,
        source_export_dir=export_dir,
        source_meta=read_json(export_dir / "meta.json"),
        payload=read_json(export_dir / "payload.json"),
        baseline_fingerprint=baseline_fingerprint,
    )


def load_specimen_identity(
    *,
    specimen_id: str,
    run_id: str,
    campaign_id: str,
    seed: int,
    replay_root: Path,
) -> CandidateSpecimen:
    return load_specimen(
        {
            "specimenId": specimen_id,
            "runId": run_id,
            "campaignId": campaign_id,
            "seed": seed,
        },
        replay_root,
    )


def load_specimen_from_topology_row(row: dict[str, Any], replay_root: Path) -> CandidateSpecimen:
    specimen_id = row.get("specimenId")
    run_id = row.get("runId")
    campaign_id = row.get("campaignId")
    seed = row.get("seed")
    if (
        not isinstance(specimen_id, str)
        or not isinstance(run_id, str)
        or not isinstance(campaign_id, str)
        or not isinstance(seed, int)
    ):
        raise SystemExit("topology row is missing specimenId/runId/campaignId/seed")
    return load_specimen_identity(
        specimen_id=specimen_id,
        run_id=run_id,
        campaign_id=campaign_id,
        seed=seed,
        replay_root=replay_root,
    )


def topology_rows_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        specimen_id = row.get("specimenId")
        if not isinstance(specimen_id, str) or not specimen_id:
            raise SystemExit("topology rows must all carry specimenId")
        index[specimen_id] = row
    return index


def load_specimens_from_topology_rows(
    rows: list[dict[str, Any]],
    *,
    replay_root: Path,
    specimen_ids: list[str],
) -> list[CandidateSpecimen]:
    row_index = topology_rows_index(rows)
    specimens: list[CandidateSpecimen] = []
    for specimen_id in specimen_ids:
        row = row_index.get(specimen_id)
        if row is None:
            raise SystemExit(f"topology rows are missing specimenId={specimen_id}")
        specimens.append(load_specimen_from_topology_row(row, replay_root))
    return specimens


def load_candidate_pairs(candidates_path: Path, replay_root: Path, top_pairs: int) -> list[CandidatePair]:
    rows = json.loads(candidates_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"{candidates_path}: expected a non-empty candidates list")
    specimen_cache: dict[str, CandidateSpecimen] = {}
    pairs: list[CandidatePair] = []
    for rank, row in enumerate(rows[:top_pairs], start=1):
        if not isinstance(row, dict):
            raise SystemExit("candidate rows must be objects")
        specimen_a_raw = row.get("specimenA")
        specimen_b_raw = row.get("specimenB")
        if not isinstance(specimen_a_raw, dict) or not isinstance(specimen_b_raw, dict):
            raise SystemExit("candidate row is missing specimenA/specimenB")
        specimen_a = specimen_cache.setdefault(
            specimen_a_raw["specimenId"],
            load_specimen(specimen_a_raw, replay_root),
        )
        specimen_b = specimen_cache.setdefault(
            specimen_b_raw["specimenId"],
            load_specimen(specimen_b_raw, replay_root),
        )
        pairs.append(CandidatePair(rank=rank, row=row, specimen_a=specimen_a, specimen_b=specimen_b))
    return pairs


def pair_slug(pair: CandidatePair) -> str:
    return sanitize(
        f"order{pair.specimen_a.dominant_order or 'x'}-rank{pair.rank}-"
        f"{pair.specimen_a.campaign_id}-{pair.specimen_b.campaign_id}"
    )


def synthetic_export_record(
    *,
    export_dir: Path,
    payload_path: Path,
    source_meta: dict[str, Any],
    name: str,
    reason: str,
    run_id: str,
) -> dict[str, Any]:
    creature = source_meta.get("creature")
    if not isinstance(creature, dict):
        raise SystemExit(f"{export_dir}: source meta is missing creature")
    creature_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}|{name}")).upper()
    owner_id = creature.get("ownerId")
    if not isinstance(owner_id, str):
        owner_id = "codex-fiber-local"
    return {
        "bundleKind": "qd24_paper_replay_bundle_v1",
        "creatureId": creature_uuid,
        "exportDir": str(export_dir),
        "exportedAt": time.time(),
        "name": name,
        "ownerId": owner_id,
        "payloadPath": str(payload_path),
        "reason": reason,
        "runId": run_id,
        "score": float(creature.get("score", 0.0)) if isinstance(creature.get("score"), (int, float)) else 0.0,
    }


def write_synthetic_qd_input(
    *,
    output_root: Path,
    pair_slug_value: str,
    variant_slug: str,
    source_specimen: CandidateSpecimen,
    payload: dict[str, Any],
    reason: str,
    source_run_id: str,
) -> Path:
    bundle_root = output_root / "synthetic-inputs" / pair_slug_value / variant_slug
    export_dir = bundle_root / "bundle"
    export_dir.mkdir(parents=True, exist_ok=True)
    payload_path = export_dir / "payload.json"
    meta_path = export_dir / "meta.json"
    index_path = bundle_root / "index.jsonl"

    meta = copy.deepcopy(source_specimen.source_meta)
    creature = meta.get("creature")
    if not isinstance(creature, dict):
        meta["creature"] = {}
        creature = meta["creature"]
    creature["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_run_id}|{variant_slug}")).upper()
    creature["name"] = variant_slug
    creature["ownerId"] = creature.get("ownerId", "codex-fiber-local")
    meta["reason"] = reason
    meta["bundleKind"] = "qd24_paper_replay_bundle_v1"
    meta["runId"] = source_run_id
    meta["exportedAt"] = time.time()

    write_json(payload_path, payload)
    write_json(meta_path, meta)
    write_jsonl(
        index_path,
        [
            synthetic_export_record(
                export_dir=export_dir,
                payload_path=payload_path,
                source_meta=meta,
                name=variant_slug,
                reason=reason,
                run_id=source_run_id,
            )
        ],
    )
    return index_path


def find_single_results_path(run_dir: Path) -> Path:
    paths = list((run_dir / "campaigns").glob("*/results.jsonl"))
    if len(paths) != 1:
        raise SystemExit(f"{run_dir}: expected exactly one replay results.jsonl, found {len(paths)}")
    return paths[0]


def run_variant(
    *,
    cli_binary: Path,
    output_root: Path,
    pair_slug_value: str,
    variant_slug: str,
    source_specimen: CandidateSpecimen,
    payload: dict[str, Any],
    reason: str,
    run_id: str,
    db_path: Path | None,
) -> ReplayOutcome:
    variant_dir = output_root / "variants" / pair_slug_value / variant_slug
    variant_dir.mkdir(parents=True, exist_ok=True)
    status_path = variant_dir / "status.json"
    if status_path.exists():
        status = read_json(status_path)
        results_path = Path(status["resultsPath"]) if isinstance(status.get("resultsPath"), str) else None
        fingerprint = None
        if results_path and results_path.exists():
            result_rows = read_jsonl(results_path)
            if len(result_rows) == 1:
                fingerprint, dominant_order, dominant_amplitude = extract_result_metrics(result_rows[0])
                return ReplayOutcome(
                    name=status["name"],
                    run_id=status["runId"],
                    run_dir=Path(status["runDir"]),
                    returncode=int(status["returncode"]),
                    stdout_tail=str(status.get("stdoutTail", "")),
                    stderr_tail=str(status.get("stderrTail", "")),
                    results_path=results_path,
                    fingerprint=fingerprint,
                    dominant_order=dominant_order,
                    dominant_amplitude=dominant_amplitude,
                )

        return ReplayOutcome(
            name=status["name"],
            run_id=status["runId"],
            run_dir=Path(status["runDir"]),
            returncode=int(status["returncode"]),
            stdout_tail=str(status.get("stdoutTail", "")),
            stderr_tail=str(status.get("stderrTail", "")),
            results_path=results_path,
            fingerprint=None,
            dominant_order=None,
            dominant_amplitude=None,
        )

    source_run_id = f"fiber-local-{pair_slug_value}-source"
    index_path = write_synthetic_qd_input(
        output_root=output_root,
        pair_slug_value=pair_slug_value,
        variant_slug=variant_slug,
        source_specimen=source_specimen,
        payload=payload,
        reason=reason,
        source_run_id=source_run_id,
    )
    replay_root = variant_dir / "replay"
    command = [
        str(cli_binary),
        "publish",
        "replay",
        "--input",
        str(index_path),
        "--output",
        str(replay_root),
        "--run-id",
        run_id,
        "--no-log-console",
    ]
    if db_path is not None:
        command.extend(["--db", str(db_path)])
    completed = subprocess.run(command, capture_output=True, text=True)
    results_path: Path | None = None
    fingerprint: np.ndarray | None = None
    dominant_order = None
    dominant_amplitude = None
    if completed.returncode == 0:
        results_path = find_single_results_path(replay_root)
        result_rows = read_jsonl(results_path)
        if len(result_rows) != 1:
            raise SystemExit(f"{results_path}: expected exactly one result row")
        fingerprint, dominant_order, dominant_amplitude = extract_result_metrics(result_rows[0])

    status = {
        "name": variant_slug,
        "reason": reason,
        "runId": run_id,
        "runDir": str(replay_root),
        "returncode": completed.returncode,
        "stdoutTail": completed.stdout[-1000:],
        "stderrTail": completed.stderr[-1000:],
    }
    if results_path is not None:
        status["resultsPath"] = str(results_path)
    write_json(status_path, status)
    return ReplayOutcome(
        name=variant_slug,
        run_id=run_id,
        run_dir=replay_root,
        returncode=completed.returncode,
        stdout_tail=completed.stdout[-1000:],
        stderr_tail=completed.stderr[-1000:],
        results_path=results_path,
        fingerprint=fingerprint,
        dominant_order=dominant_order,
        dominant_amplitude=dominant_amplitude,
    )


def coarse_alpha_grid(values: str) -> list[float]:
    grid = sorted({round(float(value.strip()), 6) for value in values.split(",") if value.strip()})
    if not grid:
        raise SystemExit("Need at least one alpha value")
    if grid[0] != 0.0 or grid[-1] != 1.0:
        raise SystemExit("Alpha grid must include 0.0 and 1.0")
    return grid


def bridge_variant_slug(alpha: float) -> str:
    return f"bridge-a{int(round(alpha * 1000)):03d}"


def adjacent_pairs(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    ordered = sorted(
        (row for row in rows if isinstance(row.get("alpha"), (int, float))),
        key=lambda row: float(row["alpha"]),
    )
    return list(zip(ordered, ordered[1:], strict=False))


def adjacent_status_brackets(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (left, right)
        for left, right in adjacent_pairs(rows)
        if (left.get("returncode") == 0) != (right.get("returncode") == 0)
    ]


def success_components(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    ordered = sorted(
        (row for row in rows if isinstance(row.get("alpha"), (int, float))),
        key=lambda row: float(row["alpha"]),
    )
    components: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for row in ordered:
        if row.get("returncode") == 0:
            current.append(row)
        elif current:
            components.append(current)
            current = []
    if current:
        components.append(current)
    return components


def has_interior_failure_band(rows: list[dict[str, Any]]) -> bool:
    components = success_components(rows)
    return len(components) >= 2 and any(
        float(component[0]["alpha"]) > 0.0 and float(component[-1]["alpha"]) < 1.0
        for component in components[1:-1]
    ) or (
        len(components) >= 2
        and float(components[0][-1]["alpha"]) > 0.0
        and float(components[-1][0]["alpha"]) < 1.0
    )


def max_contiguous_success_from_a(rows: list[dict[str, Any]]) -> float:
    ordered = sorted(
        (row for row in rows if isinstance(row.get("alpha"), (int, float))),
        key=lambda row: float(row["alpha"]),
    )
    maximum = 0.0
    for row in ordered:
        if row.get("returncode") == 0:
            maximum = float(row["alpha"])
        else:
            break
    return maximum
