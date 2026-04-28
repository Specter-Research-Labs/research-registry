from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from embryomaker_v2.legacy_snapshot import (
    LegacyEpithelialSnapshotSummary,
    LegacySnapshotSeries,
    LegacySnapshotSummary,
)


@dataclass(frozen=True)
class V2CellSortingSummary:
    steps: int
    node_count: int
    cell_count: int
    contact_count: int
    max_distance_from_origin: float
    mean_distance_from_origin: float
    mean_neighbor_count: float
    type1_cell_count: int
    type2_cell_count: int
    total_noise_attempts: int
    total_noise_accepted: int
    total_noise_rejected: int
    total_noise_zero_displacement: int


@dataclass(frozen=True)
class CellSortingComparison:
    matches: bool
    mismatches: tuple[str, ...]


@dataclass(frozen=True)
class CellSortingTrajectoryFrameComparison:
    legacy: LegacySnapshotSummary
    v2: V2CellSortingSummary
    comparison: CellSortingComparison


@dataclass(frozen=True)
class CellSortingTrajectoryComparison:
    matches: bool
    frames: tuple[CellSortingTrajectoryFrameComparison, ...]


@dataclass(frozen=True)
class V2InvaginationSummary:
    getot: int
    rtime: float
    node_count: int
    cell_count: int
    epithelial_node_count: int
    apical_node_count: int
    basal_node_count: int
    paired_epithelial_node_count: int
    epithelial_cell_count: int
    gene1_positive_node_count: int
    gene2_positive_node_count: int
    gene1_positive_cell_count: int
    gene2_positive_cell_count: int
    polarized_expression_cell_count: int
    zero_pla_node_count: int
    zero_kvol_node_count: int
    mean_grd: float
    mean_cod: float
    mean_pld: float
    mean_vod: float


@dataclass(frozen=True)
class InvaginationComparison:
    matches: bool
    mismatches: tuple[str, ...]


@dataclass(frozen=True)
class InvaginationGeometryComparison:
    matches: bool
    mismatches: tuple[str, ...]
    max_position_error: float
    mean_position_error: float
    rms_position_error: float


def parse_v2_cell_sorting_summary(text: str) -> V2CellSortingSummary:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key, separator, value = line.partition(":")
        if separator == "":
            raise ValueError("malformed v2 summary line")
        values[key.strip()] = value.strip()

    return V2CellSortingSummary(
        steps=int(values["steps"]),
        node_count=int(values["node_count"]),
        cell_count=int(values["cell_count"]),
        contact_count=int(values["contact_count"]),
        max_distance_from_origin=float(values["max_distance_from_origin"]),
        mean_distance_from_origin=float(values["mean_distance_from_origin"]),
        mean_neighbor_count=float(values["mean_neighbor_count"]),
        type1_cell_count=int(values["type1_cell_count"]),
        type2_cell_count=int(values["type2_cell_count"]),
        total_noise_attempts=int(values["total_noise_attempts"]),
        total_noise_accepted=int(values["total_noise_accepted"]),
        total_noise_rejected=int(values["total_noise_rejected"]),
        total_noise_zero_displacement=int(values["total_noise_zero_displacement"]),
    )


def run_v2_cell_sorting_summary(
    executable: Path,
    *,
    steps: int,
    initial_seed: int = -11111,
    noise_seed: int | None = None,
    cell_types_file: Path | None = None,
    node_positions_file: Path | None = None,
    noise_seed_words_file: Path | None = None,
) -> V2CellSortingSummary:
    command = [str(executable), str(steps), str(initial_seed)]
    if noise_seed is not None:
        command.append(str(noise_seed))
    if cell_types_file is not None:
        command.extend(["--cell-types-file", str(cell_types_file)])
    if node_positions_file is not None:
        command.extend(["--node-positions-file", str(node_positions_file)])
    if noise_seed_words_file is not None:
        command.extend(["--noise-seed-words-file", str(noise_seed_words_file)])
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return parse_v2_cell_sorting_summary(completed.stdout)


def parse_v2_invagination_summary(text: str) -> V2InvaginationSummary:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key, separator, value = line.partition(":")
        if separator == "":
            raise ValueError("malformed v2 invagination summary line")
        values[key.strip()] = value.strip()

    return V2InvaginationSummary(
        getot=int(values.get("getot", "0")),
        rtime=float(values.get("rtime", "0")),
        node_count=int(values["node_count"]),
        cell_count=int(values["cell_count"]),
        epithelial_node_count=int(values["epithelial_node_count"]),
        apical_node_count=int(values["apical_node_count"]),
        basal_node_count=int(values["basal_node_count"]),
        paired_epithelial_node_count=int(values["paired_epithelial_node_count"]),
        epithelial_cell_count=int(values["epithelial_cell_count"]),
        gene1_positive_node_count=int(values["gene1_positive_node_count"]),
        gene2_positive_node_count=int(values["gene2_positive_node_count"]),
        gene1_positive_cell_count=int(values["gene1_positive_cell_count"]),
        gene2_positive_cell_count=int(values["gene2_positive_cell_count"]),
        polarized_expression_cell_count=int(values["polarized_expression_cell_count"]),
        zero_pla_node_count=int(values["zero_pla_node_count"]),
        zero_kvol_node_count=int(values["zero_kvol_node_count"]),
        mean_grd=float(values["mean_grd"]),
        mean_cod=float(values["mean_cod"]),
        mean_pld=float(values["mean_pld"]),
        mean_vod=float(values["mean_vod"]),
    )


def run_v2_invagination_summary(
    executable: Path,
    *,
    bootstrap_file: Path,
    target_rtime: float | None = None,
    steps: int | None = None,
    positions_out: Path | None = None,
) -> V2InvaginationSummary:
    if target_rtime is not None and steps is not None:
        raise ValueError("target_rtime and steps are mutually exclusive")
    command = [str(executable), "--bootstrap-file", str(bootstrap_file)]
    if target_rtime is not None:
        command.extend(["--target-rtime", str(target_rtime)])
    if steps is not None:
        command.extend(["--steps", str(steps)])
    if positions_out is not None:
        command.extend(["--positions-out", str(positions_out)])
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return parse_v2_invagination_summary(completed.stdout)


def load_v2_node_positions(path: Path) -> tuple[tuple[float, float, float], ...]:
    positions: list[tuple[float, float, float]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        x, y, z = (float(value) for value in stripped.split())
        positions.append((x, y, z))
    return tuple(positions)


def compare_cell_sorting_summaries(
    legacy: LegacySnapshotSummary,
    v2: V2CellSortingSummary,
    *,
    relative_tolerance: float = 0.05,
) -> CellSortingComparison:
    mismatches: list[str] = []

    def compare_exact(name: str, legacy_value: int, v2_value: int) -> None:
        if legacy_value != v2_value:
            mismatches.append(f"{name}: legacy={legacy_value} v2={v2_value}")

    def compare_close(name: str, legacy_value: float, v2_value: float) -> None:
        scale = max(abs(legacy_value), 1.0)
        allowed = scale * relative_tolerance
        if abs(legacy_value - v2_value) > allowed:
            mismatches.append(f"{name}: legacy={legacy_value} v2={v2_value}")

    compare_exact("node_count", legacy.node_count, v2.node_count)
    compare_exact("cell_count", legacy.cell_count, v2.cell_count)
    compare_exact("type1_cell_count", legacy.type1_cell_count, v2.type1_cell_count)
    compare_exact("type2_cell_count", legacy.type2_cell_count, v2.type2_cell_count)
    compare_close("contact_count", float(legacy.contact_count), float(v2.contact_count))
    compare_close(
        "max_distance_from_origin",
        legacy.max_distance_from_origin,
        v2.max_distance_from_origin,
    )
    compare_close(
        "mean_distance_from_origin",
        legacy.mean_distance_from_origin,
        v2.mean_distance_from_origin,
    )
    compare_close("mean_neighbor_count", legacy.mean_neighbor_count, v2.mean_neighbor_count)

    return CellSortingComparison(matches=not mismatches, mismatches=tuple(mismatches))


def compare_invagination_summaries(
    legacy: LegacyEpithelialSnapshotSummary,
    v2: V2InvaginationSummary,
    *,
    relative_tolerance: float = 1e-12,
) -> InvaginationComparison:
    mismatches: list[str] = []

    def compare_exact(name: str, legacy_value: int, v2_value: int) -> None:
        if legacy_value != v2_value:
            mismatches.append(f"{name}: legacy={legacy_value} v2={v2_value}")

    def compare_close(name: str, legacy_value: float, v2_value: float) -> None:
        scale = max(abs(legacy_value), 1.0)
        allowed = scale * relative_tolerance
        if abs(legacy_value - v2_value) > allowed:
            mismatches.append(f"{name}: legacy={legacy_value} v2={v2_value}")

    compare_exact("node_count", legacy.node_count, v2.node_count)
    compare_exact("cell_count", legacy.cell_count, v2.cell_count)
    compare_exact("epithelial_node_count", legacy.epithelial_node_count, v2.epithelial_node_count)
    compare_exact("apical_node_count", legacy.apical_node_count, v2.apical_node_count)
    compare_exact("basal_node_count", legacy.basal_node_count, v2.basal_node_count)
    compare_exact(
        "paired_epithelial_node_count",
        legacy.paired_epithelial_node_count,
        v2.paired_epithelial_node_count,
    )
    compare_exact("epithelial_cell_count", legacy.epithelial_cell_count, v2.epithelial_cell_count)
    compare_exact(
        "gene1_positive_node_count",
        legacy.gene1_positive_node_count,
        v2.gene1_positive_node_count,
    )
    compare_exact(
        "gene2_positive_node_count",
        legacy.gene2_positive_node_count,
        v2.gene2_positive_node_count,
    )
    compare_exact(
        "gene1_positive_cell_count",
        legacy.gene1_positive_cell_count,
        v2.gene1_positive_cell_count,
    )
    compare_exact(
        "gene2_positive_cell_count",
        legacy.gene2_positive_cell_count,
        v2.gene2_positive_cell_count,
    )
    compare_exact(
        "polarized_expression_cell_count",
        legacy.polarized_expression_cell_count,
        v2.polarized_expression_cell_count,
    )
    compare_exact("zero_pla_node_count", legacy.zero_pla_node_count, v2.zero_pla_node_count)
    compare_exact("zero_kvol_node_count", legacy.zero_kvol_node_count, v2.zero_kvol_node_count)
    compare_close("mean_grd", legacy.mean_grd, v2.mean_grd)
    compare_close("mean_cod", legacy.mean_cod, v2.mean_cod)
    compare_close("mean_pld", legacy.mean_pld, v2.mean_pld)
    compare_close("mean_vod", legacy.mean_vod, v2.mean_vod)

    return InvaginationComparison(matches=not mismatches, mismatches=tuple(mismatches))


def compare_invagination_geometry(
    legacy_positions: tuple[tuple[float, float, float], ...],
    v2_positions: tuple[tuple[float, float, float], ...],
    *,
    absolute_tolerance: float,
) -> InvaginationGeometryComparison:
    mismatches: list[str] = []
    if len(legacy_positions) != len(v2_positions):
        mismatches.append(
            f"node_count: legacy={len(legacy_positions)} v2={len(v2_positions)}"
        )
        return InvaginationGeometryComparison(
            matches=False,
            mismatches=tuple(mismatches),
            max_position_error=0.0,
            mean_position_error=0.0,
            rms_position_error=0.0,
        )

    max_error = 0.0
    error_sum = 0.0
    error_sq_sum = 0.0
    for legacy, v2 in zip(legacy_positions, v2_positions, strict=True):
        dx = v2[0] - legacy[0]
        dy = v2[1] - legacy[1]
        dz = v2[2] - legacy[2]
        error = (dx * dx + dy * dy + dz * dz) ** 0.5
        max_error = max(max_error, error)
        error_sum += error
        error_sq_sum += error * error

    count = max(float(len(legacy_positions)), 1.0)
    mean_error = error_sum / count
    rms_error = (error_sq_sum / count) ** 0.5
    if max_error > absolute_tolerance:
        mismatches.append(
            f"max_position_error: tolerance={absolute_tolerance} observed={max_error}"
        )

    return InvaginationGeometryComparison(
        matches=not mismatches,
        mismatches=tuple(mismatches),
        max_position_error=max_error,
        mean_position_error=mean_error,
        rms_position_error=rms_error,
    )


def compare_cell_sorting_trajectory(
    legacy_series: LegacySnapshotSeries,
    executable: Path,
    *,
    initial_seed: int = -11111,
    noise_seed: int | None = None,
    cell_types_file: Path | None = None,
    node_positions_file: Path | None = None,
    noise_seed_words_file: Path | None = None,
    relative_tolerance: float = 0.05,
) -> CellSortingTrajectoryComparison:
    frames: list[CellSortingTrajectoryFrameComparison] = []
    for legacy in legacy_series.frames:
        v2 = run_v2_cell_sorting_summary(
            executable,
            steps=legacy.getot,
            initial_seed=initial_seed,
            noise_seed=noise_seed,
            cell_types_file=cell_types_file,
            node_positions_file=node_positions_file,
            noise_seed_words_file=noise_seed_words_file,
        )
        comparison = compare_cell_sorting_summaries(
            legacy,
            v2,
            relative_tolerance=relative_tolerance,
        )
        frames.append(
            CellSortingTrajectoryFrameComparison(
                legacy=legacy,
                v2=v2,
                comparison=comparison,
            )
        )

    matches = all(frame.comparison.matches for frame in frames)
    return CellSortingTrajectoryComparison(matches=matches, frames=tuple(frames))
