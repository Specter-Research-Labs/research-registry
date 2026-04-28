from __future__ import annotations

import json
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import typer

from embryomaker_v2.comparison import (
    V2CellSortingSummary,
    V2InvaginationSummary,
    compare_cell_sorting_summaries,
    compare_cell_sorting_trajectory,
    compare_invagination_geometry,
    compare_invagination_summaries,
    load_v2_node_positions,
    run_v2_cell_sorting_summary,
    run_v2_invagination_summary,
)
from embryomaker_v2.legacy_snapshot import (
    LegacyEpithelialSnapshotSummary,
    LegacySnapshotSeries,
    LegacySnapshotSummary,
    extract_legacy_cell_types,
    extract_legacy_node_positions,
    extract_legacy_rng_seed_words,
    load_legacy_snapshot_series,
    parse_legacy_snapshot,
    summarize_legacy_epithelial_snapshot,
    summarize_legacy_snapshot,
    write_legacy_invagination_bootstrap,
)


@dataclass(frozen=True)
class LegacyCellSortingPreset:
    nodes_per_cell: int
    radial_cell_layers: int
    planar_layers: int
    cell_count: int
    node_count: int
    noise_sphere_partitions: int
    integration_mode: str
    fixed_delta: bool
    neighbor_path: str
    rebuild_neighbors_per_rk_stage: bool
    capped_adhesion: bool
    max_adhesion: int
    gene_count: int
    noise_biased_by_energy: bool
    noise_rate: float
    adhesion_matrix: tuple[tuple[int, int], tuple[int, int]]


@dataclass(frozen=True)
class LegacyBaselineRecipe:
    target: str
    packages: tuple[str, ...]
    build_command: str
    preset_selection: str
    preset_warning: str
    run_command: str
    success_exit_code: int
    outputs: tuple[str, ...]


@dataclass(frozen=True)
class LegacyDockerBaselineRecipe:
    base_image: str
    default_image: str
    platform: str
    packages: tuple[str, ...]


@dataclass(frozen=True)
class LegacyBaselineLane:
    slug: str
    preset_id: int

    @property
    def file_stem(self) -> str:
        return self.slug.replace("-", "_")

    @property
    def default_run_root_name(self) -> str:
        return f"legacy-{self.slug}-baseline"

    @property
    def stage_script_name(self) -> str:
        return f"run_legacy_{self.file_stem}.sh"

    @property
    def docker_stage_script_name(self) -> str:
        return f"run_legacy_{self.file_stem}_docker.sh"

    @property
    def manifest_name(self) -> str:
        return f"{self.file_stem}_manifest.json"

    @property
    def docker_manifest_name(self) -> str:
        return f"{self.file_stem}_docker_manifest.json"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    write_text(path, json.dumps(payload, indent=2) + "\n")


def parity_lanes() -> list[str]:
    return [
        "lane0: mathematical transcription",
        "lane1: state-space parity",
        "lane2: execution parity",
        "lane3: baseline execution",
        "lane4: v2 comparison",
    ]


def legacy_cell_sorting_preset() -> LegacyCellSortingPreset:
    return LegacyCellSortingPreset(
        nodes_per_cell=8,
        radial_cell_layers=2,
        planar_layers=3,
        cell_count=21,
        node_count=168,
        noise_sphere_partitions=1000,
        integration_mode="rk4",
        fixed_delta=True,
        neighbor_path="neighbor_build -> iniboxes_p -> neighbor_build_simpleneigh",
        rebuild_neighbors_per_rk_stage=False,
        capped_adhesion=True,
        max_adhesion=50,
        gene_count=2,
        noise_biased_by_energy=True,
        noise_rate=0.5,
        adhesion_matrix=((100, 10), (10, 1)),
    )


def legacy_baseline_lane(slug: str) -> LegacyBaselineLane:
    lanes = {
        "cell-sorting": LegacyBaselineLane(slug="cell-sorting", preset_id=2),
        "invagination": LegacyBaselineLane(slug="invagination", preset_id=3),
    }
    try:
        return lanes[slug]
    except KeyError as exc:
        supported = ", ".join(sorted(lanes))
        raise typer.BadParameter(
            f"unsupported legacy baseline lane {slug!r}; choose one of: {supported}"
        ) from exc


def legacy_baseline_recipe_for_lane(lane: LegacyBaselineLane) -> LegacyBaselineRecipe:
    return LegacyBaselineRecipe(
        target="linux-x86_64",
        packages=("gfortran", "freeglut3-dev", "gnuplot (optional)"),
        build_command="./compile_EmbryoMaker.sh",
        preset_selection=f"set config_file.txt line 5 to {lane.preset_id}",
        preset_warning="the checked-in config_file.txt currently selects preset 1",
        run_command="./bin 0 01 10 100",
        success_exit_code=231,
        outputs=("output/<run-id>/*.dat", "name.dat"),
    )


def legacy_docker_baseline_recipe() -> LegacyDockerBaselineRecipe:
    return LegacyDockerBaselineRecipe(
        base_image="debian:bookworm-slim",
        default_image="embryomaker-v2-legacy-baseline:bookworm-slim",
        platform="linux/amd64",
        packages=("gfortran", "freeglut3-dev", "libglu1-mesa-dev", "libgl1-mesa-dev", "python3"),
    )


def render_recipe(lane: LegacyBaselineLane) -> tuple[str, ...]:
    recipe = legacy_baseline_recipe_for_lane(lane)
    lines = [
        f"lane: {lane.slug}",
        f"target: {recipe.target}",
        "packages:",
        *(f"- {package}" for package in recipe.packages),
        f"build_command: {recipe.build_command}",
        f"preset_selection: {recipe.preset_selection}",
        f"preset_warning: {recipe.preset_warning}",
        f"run_command: {recipe.run_command}",
        f"success_exit_code: {recipe.success_exit_code}",
        "outputs:",
        *(f"- {output}" for output in recipe.outputs),
    ]
    return tuple(lines)


def render_preset(preset: LegacyCellSortingPreset) -> tuple[str, ...]:
    return (
        "preset: legacy-cell-sorting",
        f"nodes_per_cell: {preset.nodes_per_cell}",
        f"radial_cell_layers: {preset.radial_cell_layers}",
        f"planar_layers: {preset.planar_layers}",
        f"cell_count: {preset.cell_count}",
        f"node_count: {preset.node_count}",
        f"noise_sphere_partitions: {preset.noise_sphere_partitions}",
        f"integration_mode: {preset.integration_mode}",
        f"fixed_delta: {preset.fixed_delta}",
        f"neighbor_path: {preset.neighbor_path}",
        f"rebuild_neighbors_per_rk_stage: {preset.rebuild_neighbors_per_rk_stage}",
        f"capped_adhesion: {preset.capped_adhesion}",
        f"max_adhesion: {preset.max_adhesion}",
        f"gene_count: {preset.gene_count}",
        f"noise_biased_by_energy: {preset.noise_biased_by_energy}",
        f"noise_rate: {preset.noise_rate}",
        "adhesion_matrix:",
        *(f"- {row[0]} {row[1]}" for row in preset.adhesion_matrix),
    )


def serialize_legacy_snapshot_summary(summary: LegacySnapshotSummary) -> dict[str, object]:
    return {
        "path": None if summary.path is None else str(summary.path),
        "getot": summary.getot,
        "rtime": summary.rtime,
        "node_count": summary.node_count,
        "cell_count": summary.cell_count,
        "gene_count": summary.gene_count,
        "contact_count": summary.contact_count,
        "max_distance_from_origin": summary.max_distance_from_origin,
        "mean_distance_from_origin": summary.mean_distance_from_origin,
        "mean_neighbor_count": summary.mean_neighbor_count,
        "type1_cell_count": summary.type1_cell_count,
        "type2_cell_count": summary.type2_cell_count,
    }


def serialize_v2_summary(summary: V2CellSortingSummary) -> dict[str, object]:
    return {
        "steps": summary.steps,
        "node_count": summary.node_count,
        "cell_count": summary.cell_count,
        "contact_count": summary.contact_count,
        "max_distance_from_origin": summary.max_distance_from_origin,
        "mean_distance_from_origin": summary.mean_distance_from_origin,
        "mean_neighbor_count": summary.mean_neighbor_count,
        "type1_cell_count": summary.type1_cell_count,
        "type2_cell_count": summary.type2_cell_count,
        "total_noise_attempts": summary.total_noise_attempts,
        "total_noise_accepted": summary.total_noise_accepted,
        "total_noise_rejected": summary.total_noise_rejected,
        "total_noise_zero_displacement": summary.total_noise_zero_displacement,
    }


def serialize_legacy_epithelial_summary(
    summary: LegacyEpithelialSnapshotSummary,
) -> dict[str, object]:
    return {
        "path": None if summary.path is None else str(summary.path),
        "getot": summary.getot,
        "rtime": summary.rtime,
        "node_count": summary.node_count,
        "cell_count": summary.cell_count,
        "epithelial_node_count": summary.epithelial_node_count,
        "apical_node_count": summary.apical_node_count,
        "basal_node_count": summary.basal_node_count,
        "paired_epithelial_node_count": summary.paired_epithelial_node_count,
        "epithelial_cell_count": summary.epithelial_cell_count,
        "gene1_positive_node_count": summary.gene1_positive_node_count,
        "gene2_positive_node_count": summary.gene2_positive_node_count,
        "gene1_positive_cell_count": summary.gene1_positive_cell_count,
        "gene2_positive_cell_count": summary.gene2_positive_cell_count,
        "polarized_expression_cell_count": summary.polarized_expression_cell_count,
        "zero_pla_node_count": summary.zero_pla_node_count,
        "zero_kvol_node_count": summary.zero_kvol_node_count,
        "mean_grd": summary.mean_grd,
        "mean_cod": summary.mean_cod,
        "mean_pld": summary.mean_pld,
        "mean_vod": summary.mean_vod,
    }


def serialize_v2_invagination_summary(summary: V2InvaginationSummary) -> dict[str, object]:
    return {
        "getot": summary.getot,
        "rtime": summary.rtime,
        "node_count": summary.node_count,
        "cell_count": summary.cell_count,
        "epithelial_node_count": summary.epithelial_node_count,
        "apical_node_count": summary.apical_node_count,
        "basal_node_count": summary.basal_node_count,
        "paired_epithelial_node_count": summary.paired_epithelial_node_count,
        "epithelial_cell_count": summary.epithelial_cell_count,
        "gene1_positive_node_count": summary.gene1_positive_node_count,
        "gene2_positive_node_count": summary.gene2_positive_node_count,
        "gene1_positive_cell_count": summary.gene1_positive_cell_count,
        "gene2_positive_cell_count": summary.gene2_positive_cell_count,
        "polarized_expression_cell_count": summary.polarized_expression_cell_count,
        "zero_pla_node_count": summary.zero_pla_node_count,
        "zero_kvol_node_count": summary.zero_kvol_node_count,
        "mean_grd": summary.mean_grd,
        "mean_cod": summary.mean_cod,
        "mean_pld": summary.mean_pld,
        "mean_vod": summary.mean_vod,
    }


def serialize_invagination_geometry(
    max_position_error: float,
    mean_position_error: float,
    rms_position_error: float,
) -> dict[str, object]:
    return {
        "max_position_error": max_position_error,
        "mean_position_error": mean_position_error,
        "rms_position_error": rms_position_error,
    }


def frame_label(summary: LegacySnapshotSummary) -> str:
    if summary.path is None:
        return f"{summary.getot}.dat"
    return summary.path.name


def single_frame_decision(mismatches: tuple[str, ...]) -> tuple[str, str]:
    if not mismatches:
        return "pass", "all comparison metrics matched within the declared tolerance"
    count = len(mismatches)
    metric_noun = "metric" if count == 1 else "metrics"
    return "fail", f"{count} comparison {metric_noun} exceeded the declared tolerance"


def trajectory_decision(frame_labels: tuple[str, ...]) -> tuple[str, str]:
    if not frame_labels:
        return "pass", "all trajectory frames matched within the declared tolerance"
    frame_count = len(frame_labels)
    frame_noun = "frame" if frame_count == 1 else "frames"
    label_preview = ", ".join(frame_labels[:3])
    if frame_count > 3:
        label_preview += ", ..."
    return (
        "fail",
        f"{frame_count} trajectory {frame_noun} exceeded the declared tolerance ({label_preview})",
    )


def snapshot_frame_paths(directory: Path) -> tuple[Path, ...]:
    return tuple(path for path in sorted(directory.glob("*.dat")) if path.name != "name.dat")


def single_snapshot_child(directory: Path) -> Path | None:
    matches = [
        child
        for child in sorted(directory.iterdir())
        if child.is_dir() and snapshot_frame_paths(child)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            "multiple legacy snapshot directories found in "
            f"{directory}; pass one directory directly"
        )
    return None


def resolve_legacy_snapshot_dir(directory: Path) -> Path:
    if snapshot_frame_paths(directory):
        return directory

    output_dir = directory / "output"
    if output_dir.is_dir():
        if snapshot_frame_paths(output_dir):
            return output_dir
        resolved_output_child = single_snapshot_child(output_dir)
        if resolved_output_child is not None:
            return resolved_output_child

    resolved_child = single_snapshot_child(directory)
    if resolved_child is not None:
        return resolved_child

    raise ValueError(f"no legacy .dat snapshots found in {directory}")


def trajectory_bootstrap_frame(legacy_series: LegacySnapshotSeries) -> LegacySnapshotSummary:
    frame = legacy_series.frames[0]
    if frame.getot != 0:
        raise ValueError(
            "trajectory bootstrap frame must start at getot 0 so the v2 comparison "
            f"does not silently skip the early legacy dynamics (got {frame.getot})"
        )
    return frame


def render_stage_script(
    *,
    lane: LegacyBaselineLane,
    legacy_root: Path,
    workspace_root: Path,
    artifacts_root: Path,
    iterations_per_snapshot: int,
    snapshot_count: int,
    expected_exit_code: int,
) -> str:
    quoted_legacy_root = shlex.quote(str(legacy_root))
    quoted_workspace_root = shlex.quote(str(workspace_root))
    quoted_artifacts_root = shlex.quote(str(artifacts_root))
    return f"""#!/usr/bin/env bash
set -euo pipefail

LEGACY_ROOT={quoted_legacy_root}
WORKSPACE_ROOT={quoted_workspace_root}
ARTIFACTS_ROOT={quoted_artifacts_root}
WORKTREE_ROOT="$WORKSPACE_ROOT/EmbryoMaker"
CONFIG_PATH="$WORKTREE_ROOT/config_file.txt"

rm -rf "$WORKTREE_ROOT"
rm -rf "$ARTIFACTS_ROOT"
mkdir -p "$WORKSPACE_ROOT" "$ARTIFACTS_ROOT"
cp -R "$LEGACY_ROOT" "$WORKTREE_ROOT"

python3 - "$CONFIG_PATH" <<'PY'
from pathlib import Path
import sys

config_path = Path(sys.argv[1])
lines = config_path.read_text(encoding="utf-8").splitlines()
if len(lines) < 5:
    raise SystemExit("config_file.txt has fewer than 5 lines")
lines[4] = "{lane.preset_id}"
draw_flags_header = "#draw function flags (will determine what is bein displayed)"
preselection_header = "#Preselection of nodes and cells"
try:
    draw_flags_start = lines.index(draw_flags_header)
    preselection_start = lines.index(preselection_header)
except ValueError as exc:
    raise SystemExit("config_file.txt is missing expected draw-flag markers") from exc
draw_flag_count = 0
for line in lines[draw_flags_start + 1 : preselection_start]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if stripped[0].isdigit() or (
        stripped[0] == "-" and len(stripped) > 1 and stripped[1].isdigit()
    ):
        draw_flag_count += 1
if draw_flag_count == 40:
    lines.insert(preselection_start, "0")
elif draw_flag_count != 41:
    raise SystemExit(
        f"config_file.txt has {{draw_flag_count}} draw flags; expected 40 or 41"
    )
config_path.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
PY

(
  cd "$WORKTREE_ROOT"
  chmod +x ./compile_EmbryoMaker.sh
  ./compile_EmbryoMaker.sh
) 2>&1 | tee "$ARTIFACTS_ROOT/compile.log"

uname -a > "$ARTIFACTS_ROOT/uname.txt"
if command -v gfortran >/dev/null 2>&1; then
  gfortran --version > "$ARTIFACTS_ROOT/gfortran.version.txt"
fi
cp "$CONFIG_PATH" "$ARTIFACTS_ROOT/config_file.txt"

EMAKER_PATH="./bin"
EMAKER_HOST_PATH="$WORKTREE_ROOT/bin"
if [[ -d "$WORKTREE_ROOT/bin" ]]; then
  EMAKER_PATH="./bin/EMaker"
  EMAKER_HOST_PATH="$WORKTREE_ROOT/bin/EMaker"
fi
if [[ ! -x "$EMAKER_HOST_PATH" ]]; then
  printf 'expected legacy executable at %s or %s/EMaker\\n' \\
    "$WORKTREE_ROOT/bin" "$WORKTREE_ROOT/bin" >&2
  exit 1
fi

set +e
(
  cd "$WORKTREE_ROOT"
  "$EMAKER_PATH" 0 01 {iterations_per_snapshot} {snapshot_count}
) >"$ARTIFACTS_ROOT/run.stdout.log" 2>"$ARTIFACTS_ROOT/run.stderr.log"
status=$?
set -e

printf '%s\\n' "$status" > "$ARTIFACTS_ROOT/exit_code.txt"
if [[ "$status" -ne {expected_exit_code} ]]; then
  printf 'unexpected legacy exit code: %s\\n' "$status" >&2
  exit 1
fi

if [[ -d "$WORKTREE_ROOT/output" ]]; then
  rm -rf "$ARTIFACTS_ROOT/output"
  cp -R "$WORKTREE_ROOT/output" "$ARTIFACTS_ROOT/output"
fi
if [[ -f "$WORKTREE_ROOT/name.dat" ]]; then
  cp "$WORKTREE_ROOT/name.dat" "$ARTIFACTS_ROOT/name.dat"
fi

printf 'legacy {lane.slug} baseline completed in %s\\n' "$ARTIFACTS_ROOT"
"""


def render_docker_stage_script(
    *,
    legacy_root: Path,
    run_root: Path,
    stage_script: Path,
    image: str,
    platform: str,
    packages: tuple[str, ...],
    install_packages: bool,
) -> str:
    quoted_legacy_root = shlex.quote(str(legacy_root))
    quoted_run_root = shlex.quote(str(run_root))
    quoted_image = shlex.quote(image)
    quoted_platform = shlex.quote(platform)
    package_install_command = " ".join(shlex.quote(package) for package in packages)
    container_command_lines = ["set -euo pipefail"]
    if install_packages:
        container_command_lines.extend(
            [
                "export DEBIAN_FRONTEND=noninteractive",
                "apt-get update >/dev/null",
                f"apt-get install -y {package_install_command} >/dev/null",
            ]
        )
    container_command_lines.append(f"bash {shlex.quote(str(stage_script))}")
    quoted_container_command = shlex.quote("\n".join(container_command_lines))
    return f"""#!/usr/bin/env bash
set -euo pipefail

LEGACY_ROOT={quoted_legacy_root}
RUN_ROOT={quoted_run_root}

mkdir -p "$RUN_ROOT"

docker run --rm --platform {quoted_platform} \\
  -v "$LEGACY_ROOT":"$LEGACY_ROOT":ro \\
  -v "$RUN_ROOT":"$RUN_ROOT" \\
  {quoted_image} bash -lc {quoted_container_command}
"""


def render_docker_image_dockerfile(*, base_image: str, packages: tuple[str, ...]) -> str:
    install_packages = " ".join(shlex.quote(package) for package in packages)
    return f"""FROM {base_image}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \\
    && apt-get install -y {install_packages} \\
    && rm -rf /var/lib/apt/lists/*
"""


def write_docker_image_bundle(
    *,
    context_root: Path | None,
    image: str,
    base_image: str,
    platform: str,
) -> tuple[LegacyDockerBaselineRecipe, Path, Path, Path]:
    recipe = legacy_docker_baseline_recipe()
    resolved_context_root = (
        context_root or (repo_root() / "tmp" / "legacy-cell-sorting-docker-image")
    ).resolve()
    dockerfile_path = resolved_context_root / "Dockerfile"
    manifest_path = resolved_context_root / "cell_sorting_docker_image_manifest.json"
    stage_command = shlex.join(
        [
            "uv",
            "run",
            "embryomaker-v2",
            "baseline",
            "stage-cell-sorting-docker",
            "/path/to/EmbryoMaker",
            "--image",
            image,
            "--container-platform",
            platform,
            "--skip-install-packages",
        ]
    )
    manifest = {
        "image": image,
        "base_image": base_image,
        "platform": platform,
        "packages": list(recipe.packages),
        "dockerfile": str(dockerfile_path),
        "stage_command": stage_command,
        "notes": [
            "Build this image once to cache the legacy baseline toolchain.",
            "Use --skip-install-packages with the staged Docker runner "
            "when this image is available.",
        ],
    }
    write_text(
        dockerfile_path,
        render_docker_image_dockerfile(base_image=base_image, packages=recipe.packages),
    )
    write_text(manifest_path, json.dumps(manifest, indent=2) + "\n")
    return recipe, resolved_context_root, dockerfile_path, manifest_path


def run_checked(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"missing required executable: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise typer.Exit(code=exc.returncode) from exc


def stage_baseline_bundle(
    *,
    lane: LegacyBaselineLane,
    legacy_root: Path,
    run_root: Path | None,
    iterations_per_snapshot: int,
    snapshot_count: int,
) -> tuple[LegacyBaselineRecipe, Path, Path, Path, Path]:
    compile_script = legacy_root / "compile_EmbryoMaker.sh"
    config_path = legacy_root / "config_file.txt"
    if not compile_script.is_file():
        raise typer.BadParameter("compile_EmbryoMaker.sh is missing in the legacy root")
    if not config_path.is_file():
        raise typer.BadParameter("config_file.txt is missing in the legacy root")

    recipe = legacy_baseline_recipe_for_lane(lane)
    resolved_run_root = (
        run_root or (repo_root() / "tmp" / lane.default_run_root_name)
    ).resolve()
    workspace_root = resolved_run_root / "workspace"
    artifacts_root = resolved_run_root / "artifacts"
    script_path = resolved_run_root / lane.stage_script_name
    manifest_path = resolved_run_root / lane.manifest_name
    stage_manifest = {
        "lane": lane.slug,
        "target": recipe.target,
        "legacy_root": str(legacy_root),
        "workspace_root": str(workspace_root),
        "artifacts_root": str(artifacts_root),
        "compile_command": recipe.build_command,
        "run_command": f"./bin 0 01 {iterations_per_snapshot} {snapshot_count}",
        "expected_exit_code": recipe.success_exit_code,
        "binary_resolution": {
            "primary_path": "bin",
            "fallback_path": "bin/EMaker",
        },
        "preset_selection": {
            "config_file_path": "config_file.txt",
            "line_number": 5,
            "value": str(lane.preset_id),
        },
        "outputs": list(recipe.outputs),
        "notes": [
            "The staged runner copies the legacy checkout into a disposable "
            "workspace before patching config_file.txt.",
            "On a fresh checkout the legacy compile script renames the binary "
            "to a top-level file named bin, so the staged runner resolves "
            "./bin first and ./bin/EMaker only if bin is a directory.",
            "The staged runner passes automatic mode as 01 rather than 1 "
            "because the legacy startup path only allocates its random-seed "
            "arrays when the second CLI argument has length greater than 1.",
            "The checked-in config_file.txt is one draw flag short for the "
            "legacy parser, so the staged runner inserts a final zero-valued "
            "draw flag before the preselection section.",
            "The staged runner executes that binary through a relative path "
            "because the legacy getarg(0) path handling truncates long "
            "absolute executable paths.",
        ],
    }
    write_text(
        script_path,
        render_stage_script(
            lane=lane,
            legacy_root=legacy_root,
            workspace_root=workspace_root,
            artifacts_root=artifacts_root,
            iterations_per_snapshot=iterations_per_snapshot,
            snapshot_count=snapshot_count,
            expected_exit_code=recipe.success_exit_code,
        ),
    )
    script_path.chmod(script_path.stat().st_mode | 0o111)
    write_text(manifest_path, json.dumps(stage_manifest, indent=2) + "\n")
    return recipe, resolved_run_root, script_path, manifest_path, artifacts_root


def render_stage_summary(
    *,
    legacy_root: Path,
    run_root: Path,
    script_path: Path,
    manifest_path: Path,
    iterations_per_snapshot: int,
    snapshot_count: int,
) -> tuple[str, ...]:
    return (
        f"legacy_root: {legacy_root}",
        f"run_root: {run_root}",
        f"stage_script: {script_path}",
        f"manifest: {manifest_path}",
        f"run_command: ./bin 0 01 {iterations_per_snapshot} {snapshot_count}",
    )


def write_docker_stage_bundle(
    *,
    lane: LegacyBaselineLane,
    legacy_root: Path,
    run_root: Path | None,
    iterations_per_snapshot: int,
    snapshot_count: int,
    image: str,
    container_platform: str,
    install_packages: bool,
) -> tuple[Path, Path, Path, Path, Path]:
    _, resolved_run_root, script_path, manifest_path, artifacts_root = stage_baseline_bundle(
        lane=lane,
        legacy_root=legacy_root,
        run_root=run_root,
        iterations_per_snapshot=iterations_per_snapshot,
        snapshot_count=snapshot_count,
    )
    docker_recipe = legacy_docker_baseline_recipe()
    docker_script_path = resolved_run_root / lane.docker_stage_script_name
    docker_manifest_path = resolved_run_root / lane.docker_manifest_name
    docker_manifest = {
        "lane": lane.slug,
        "image": image,
        "platform": container_platform,
        "stage_script": str(script_path),
        "legacy_root": str(legacy_root),
        "run_root": str(resolved_run_root),
        "artifacts_root": str(artifacts_root),
        "packages": list(docker_recipe.packages),
        "install_packages": install_packages,
        "native_manifest": str(manifest_path),
        "notes": [
            "This wrapper mounts the staged baseline bundle back into the same "
            "absolute paths inside the container so the native Linux script "
            "remains the single source of truth.",
            "Use this on Apple Silicon hosts when Linux x86_64 artifacts are needed.",
            "Set --skip-install-packages when the container image already "
            "includes the legacy toolchain.",
        ],
    }
    write_text(
        docker_script_path,
        render_docker_stage_script(
            legacy_root=legacy_root,
            run_root=resolved_run_root,
            stage_script=script_path,
            image=image,
            platform=container_platform,
            packages=docker_recipe.packages,
            install_packages=install_packages,
        ),
    )
    docker_script_path.chmod(docker_script_path.stat().st_mode | 0o111)
    write_text(docker_manifest_path, json.dumps(docker_manifest, indent=2) + "\n")
    return resolved_run_root, script_path, manifest_path, docker_script_path, docker_manifest_path


def compare_invagination_bootstrap_payload(
    *,
    snapshot_path: Path,
    executable: Path,
    relative_tolerance: float,
) -> dict[str, object]:
    snapshot = parse_legacy_snapshot(snapshot_path)
    legacy = summarize_legacy_epithelial_snapshot(snapshot)
    with tempfile.TemporaryDirectory(prefix="legacy-invagination-bootstrap-") as temp_dir:
        bootstrap_file = Path(temp_dir) / "invagination_bootstrap.txt"
        write_legacy_invagination_bootstrap(snapshot, bootstrap_file)
        v2 = run_v2_invagination_summary(executable, bootstrap_file=bootstrap_file)
    comparison = compare_invagination_summaries(
        legacy,
        v2,
        relative_tolerance=relative_tolerance,
    )
    decision, reason = single_frame_decision(comparison.mismatches)
    return {
        "lane": "invagination",
        "scope": "bootstrap",
        "snapshot": str(snapshot_path),
        "executable": str(executable),
        "relative_tolerance": relative_tolerance,
        "decision": decision,
        "reason": reason,
        "matches": comparison.matches,
        "mismatches": list(comparison.mismatches),
        "legacy": serialize_legacy_epithelial_summary(legacy),
        "v2": serialize_v2_invagination_summary(v2),
    }


def compare_invagination_payload(
    *,
    snapshot_path: Path,
    bootstrap_snapshot: Path,
    executable: Path,
    steps: int | None,
    relative_tolerance: float,
    absolute_tolerance: float,
) -> dict[str, object]:
    bootstrap = parse_legacy_snapshot(bootstrap_snapshot)
    target = parse_legacy_snapshot(snapshot_path)
    legacy = summarize_legacy_epithelial_snapshot(target)
    legacy_positions = extract_legacy_node_positions(target)

    with tempfile.TemporaryDirectory(prefix="legacy-invagination-compare-") as temp_dir:
        bootstrap_file = Path(temp_dir) / "invagination_bootstrap.txt"
        positions_out = Path(temp_dir) / "invagination_positions.txt"
        write_legacy_invagination_bootstrap(bootstrap, bootstrap_file)
        v2 = run_v2_invagination_summary(
            executable,
            bootstrap_file=bootstrap_file,
            target_rtime=target.rtime if steps is None else None,
            steps=steps,
            positions_out=positions_out,
        )
        v2_positions = load_v2_node_positions(positions_out)

    summary_comparison = compare_invagination_summaries(
        legacy,
        v2,
        relative_tolerance=relative_tolerance,
    )
    geometry_comparison = compare_invagination_geometry(
        legacy_positions,
        v2_positions,
        absolute_tolerance=absolute_tolerance,
    )
    all_mismatches = summary_comparison.mismatches + geometry_comparison.mismatches
    matches = summary_comparison.matches and geometry_comparison.matches
    decision, reason = single_frame_decision(all_mismatches)
    return {
        "lane": "invagination",
        "scope": "single-frame",
        "snapshot": str(snapshot_path),
        "bootstrap_snapshot": str(bootstrap_snapshot),
        "executable": str(executable),
        "relative_tolerance": relative_tolerance,
        "absolute_tolerance": absolute_tolerance,
        "decision": decision,
        "reason": reason,
        "matches": matches,
        "summary_matches": summary_comparison.matches,
        "geometry_matches": geometry_comparison.matches,
        "mismatches": list(all_mismatches),
        "summary_mismatches": list(summary_comparison.mismatches),
        "geometry_mismatches": list(geometry_comparison.mismatches),
        "legacy": serialize_legacy_epithelial_summary(legacy),
        "v2": serialize_v2_invagination_summary(v2),
        "geometry": serialize_invagination_geometry(
            geometry_comparison.max_position_error,
            geometry_comparison.mean_position_error,
            geometry_comparison.rms_position_error,
        ),
    }


def compare_cell_sorting_payload(
    *,
    snapshot_path: Path,
    executable: Path,
    steps: int | None,
    initial_seed: int,
    noise_seed: int | None,
    relative_tolerance: float,
) -> dict[str, object]:
    snapshot = parse_legacy_snapshot(snapshot_path)
    legacy = summarize_legacy_snapshot(snapshot)
    v2 = run_v2_cell_sorting_summary(
        executable,
        steps=legacy.getot if steps is None else steps,
        initial_seed=initial_seed,
        noise_seed=noise_seed,
    )
    comparison = compare_cell_sorting_summaries(
        legacy,
        v2,
        relative_tolerance=relative_tolerance,
    )
    decision, reason = single_frame_decision(comparison.mismatches)
    return {
        "lane": "cell-sorting",
        "scope": "single-frame",
        "snapshot": str(snapshot_path),
        "executable": str(executable),
        "relative_tolerance": relative_tolerance,
        "seeds": {
            "initial_seed": initial_seed,
            "noise_seed": noise_seed,
        },
        "decision": decision,
        "reason": reason,
        "matches": comparison.matches,
        "mismatches": list(comparison.mismatches),
        "legacy": serialize_legacy_snapshot_summary(legacy),
        "v2": serialize_v2_summary(v2),
    }


def compare_cell_sorting_trajectory_payload(
    *,
    snapshot_dir: Path,
    executable: Path,
    initial_seed: int,
    noise_seed: int | None,
    relative_tolerance: float,
) -> dict[str, object]:
    resolved_snapshot_dir = resolve_legacy_snapshot_dir(snapshot_dir)
    legacy_series = load_legacy_snapshot_series(resolved_snapshot_dir)
    bootstrap_frame = trajectory_bootstrap_frame(legacy_series)
    bootstrap_cell_types_source = bootstrap_frame.path
    bootstrap_node_positions_source = bootstrap_frame.path
    bootstrap_noise_seed_source = bootstrap_frame.path if noise_seed is None else None
    with tempfile.TemporaryDirectory(prefix="legacy-bootstrap-") as temp_dir:
        cell_types_file = None
        node_positions_file = None
        noise_seed_words_file = None
        if bootstrap_cell_types_source is not None:
            initial_snapshot = parse_legacy_snapshot(bootstrap_cell_types_source)
            cell_types_file = Path(temp_dir) / "cell_types.txt"
            cell_types_file.write_text(
                "".join(f"{value}\n" for value in extract_legacy_cell_types(initial_snapshot)),
                encoding="utf-8",
            )
            node_positions_file = Path(temp_dir) / "node_positions.txt"
            node_positions_file.write_text(
                "".join(
                    f"{x:.17g} {y:.17g} {z:.17g}\n"
                    for x, y, z in extract_legacy_node_positions(initial_snapshot)
                ),
                encoding="utf-8",
            )
        if bootstrap_noise_seed_source is not None:
            noise_seed_words_file = Path(temp_dir) / "noise_seed_words.txt"
            noise_seed_words_file.write_text(
                "".join(
                    f"{value}\n"
                    for value in extract_legacy_rng_seed_words(bootstrap_noise_seed_source)
                ),
                encoding="utf-8",
            )
        comparison = compare_cell_sorting_trajectory(
            legacy_series,
            executable,
            initial_seed=initial_seed,
            noise_seed=noise_seed,
            cell_types_file=cell_types_file,
            node_positions_file=node_positions_file,
            noise_seed_words_file=noise_seed_words_file,
            relative_tolerance=relative_tolerance,
        )
    mismatched_frame_labels = tuple(
        frame_label(frame.legacy) for frame in comparison.frames if not frame.comparison.matches
    )
    decision, reason = trajectory_decision(mismatched_frame_labels)
    return {
        "lane": "cell-sorting",
        "scope": "trajectory",
        "snapshot_dir": str(snapshot_dir),
        "resolved_snapshot_dir": str(resolved_snapshot_dir),
        "executable": str(executable),
        "relative_tolerance": relative_tolerance,
        "seeds": {
            "initial_seed": initial_seed,
            "noise_seed": noise_seed,
        },
        "bootstrap_cell_types_source": None
        if bootstrap_cell_types_source is None
        else str(bootstrap_cell_types_source),
        "bootstrap_node_positions_source": None
        if bootstrap_node_positions_source is None
        else str(bootstrap_node_positions_source),
        "bootstrap_noise_seed_source": None
        if bootstrap_noise_seed_source is None
        else str(bootstrap_noise_seed_source),
        "decision": decision,
        "reason": reason,
        "matches": comparison.matches,
        "frame_count": len(comparison.frames),
        "frames": [
            {
                "snapshot": None if frame.legacy.path is None else str(frame.legacy.path),
                "label": frame_label(frame.legacy),
                "decision": "pass" if frame.comparison.matches else "fail",
                "reason": single_frame_decision(frame.comparison.mismatches)[1],
                "matches": frame.comparison.matches,
                "mismatches": list(frame.comparison.mismatches),
                "legacy": serialize_legacy_snapshot_summary(frame.legacy),
                "v2": serialize_v2_summary(frame.v2),
            }
            for frame in comparison.frames
        ],
    }
