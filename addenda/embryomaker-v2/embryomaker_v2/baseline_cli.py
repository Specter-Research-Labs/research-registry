from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast

import typer

from embryomaker_v2.baseline_support import (
    compare_cell_sorting_payload,
    compare_cell_sorting_trajectory_payload,
    compare_invagination_bootstrap_payload,
    compare_invagination_payload,
    legacy_baseline_lane,
    legacy_docker_baseline_recipe,
    parity_lanes,
    render_recipe,
    render_stage_summary,
    repo_root,
    run_checked,
    stage_baseline_bundle,
    write_docker_image_bundle,
    write_docker_stage_bundle,
    write_json,
)
from embryomaker_v2.legacy_snapshot import (
    parse_legacy_snapshot,
    summarize_legacy_epithelial_snapshot,
    summarize_legacy_snapshot,
)

baseline_app = typer.Typer(no_args_is_help=True, help="Original baseline and parity tools")


def _emit(lines: tuple[str, ...]) -> None:
    for line in lines:
        typer.echo(line)


def _tool_line(name: str) -> str:
    path = shutil.which(name)
    return f"{name}: {path}" if path is not None else f"{name}: missing"


def _default_invagination_executable(executable: Path | None) -> Path:
    return executable or (repo_root() / "kernel" / "build" / "em2_legacy_invagination_summary")


def _default_cell_sorting_executable(executable: Path | None) -> Path:
    return executable or (repo_root() / "kernel" / "build" / "em2_legacy_cell_sorting_summary")


def _require_built_executable(path: Path) -> Path:
    if not path.is_file():
        raise typer.BadParameter(
            f"missing built summary executable: {path}. Build the kernel first."
        )
    return path


def _payload_map(value: object) -> dict[str, object]:
    return cast(dict[str, object], value)


def _payload_list(value: object) -> list[object]:
    return cast(list[object], value)


def _string_list(value: object) -> list[str]:
    return cast(list[str], value)


@baseline_app.command("doctor")
def baseline_doctor() -> None:
    _emit(
        (
            "baseline_toolchain:",
            *(
                _tool_line(name)
                for name in ("gfortran", "clang++", "cmake", "git", "nix", "brew", "docker", "orb")
            ),
            "recommended_target: linux-x86_64 with pinned gfortran and freeglut",
        )
    )


@baseline_app.command("lanes")
def baseline_lanes() -> None:
    _emit(tuple(parity_lanes()))


@baseline_app.command("recipe")
def baseline_recipe(
    lane: str = typer.Option(
        "cell-sorting",
        help="Legacy preset lane to describe.",
    ),
) -> None:
    _emit(render_recipe(legacy_baseline_lane(lane)))


@baseline_app.command("build-docker-image")
def baseline_build_docker_image(
    context_root: Path | None = typer.Option(
        None,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Directory where the Docker build context and manifest will be written.",
    ),
    image: str = typer.Option(legacy_docker_baseline_recipe().default_image),
    base_image: str = typer.Option(legacy_docker_baseline_recipe().base_image),
    platform: str = typer.Option(legacy_docker_baseline_recipe().platform),
    pull: bool = typer.Option(
        True,
        "--pull/--no-pull",
        help="Refresh the base image before building the cached legacy toolchain image.",
    ),
) -> None:
    _, resolved_context_root, dockerfile_path, manifest_path = write_docker_image_bundle(
        context_root=context_root,
        image=image,
        base_image=base_image,
        platform=platform,
    )
    build_command = ["docker", "build", "--platform", platform, "-t", image]
    if pull:
        build_command.append("--pull")
    build_command.append(str(resolved_context_root))
    run_checked(build_command)
    _emit(
        (
            f"context_root: {resolved_context_root}",
            f"dockerfile: {dockerfile_path}",
            f"manifest: {manifest_path}",
            f"image: {image}",
            f"platform: {platform}",
            "stage_hint: use --skip-install-packages with this image",
        )
    )


def _stage_lane(
    *,
    lane_slug: str,
    legacy_root: Path,
    run_root: Path | None,
    iterations_per_snapshot: int,
    snapshot_count: int,
) -> None:
    _, resolved_run_root, script_path, manifest_path, _ = stage_baseline_bundle(
        lane=legacy_baseline_lane(lane_slug),
        legacy_root=legacy_root,
        run_root=run_root,
        iterations_per_snapshot=iterations_per_snapshot,
        snapshot_count=snapshot_count,
    )
    _emit(
        render_stage_summary(
            legacy_root=legacy_root,
            run_root=resolved_run_root,
            script_path=script_path,
            manifest_path=manifest_path,
            iterations_per_snapshot=iterations_per_snapshot,
            snapshot_count=snapshot_count,
        )
    )


@baseline_app.command("stage-cell-sorting")
def baseline_stage_cell_sorting(
    legacy_root: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Path to a local checkout of the original EmbryoMaker root.",
    ),
    run_root: Path | None = typer.Option(
        None,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Directory where the staged legacy baseline bundle will be written.",
    ),
    iterations_per_snapshot: int = typer.Option(10, min=1),
    snapshot_count: int = typer.Option(100, min=1),
) -> None:
    _stage_lane(
        lane_slug="cell-sorting",
        legacy_root=legacy_root,
        run_root=run_root,
        iterations_per_snapshot=iterations_per_snapshot,
        snapshot_count=snapshot_count,
    )


@baseline_app.command("stage-invagination")
def baseline_stage_invagination(
    legacy_root: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Path to a local checkout of the original EmbryoMaker root.",
    ),
    run_root: Path | None = typer.Option(
        None,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Directory where the staged legacy baseline bundle will be written.",
    ),
    iterations_per_snapshot: int = typer.Option(10, min=1),
    snapshot_count: int = typer.Option(100, min=1),
) -> None:
    _stage_lane(
        lane_slug="invagination",
        legacy_root=legacy_root,
        run_root=run_root,
        iterations_per_snapshot=iterations_per_snapshot,
        snapshot_count=snapshot_count,
    )


def _stage_docker_lane(
    *,
    lane_slug: str,
    legacy_root: Path,
    run_root: Path | None,
    iterations_per_snapshot: int,
    snapshot_count: int,
    image: str,
    container_platform: str,
    install_packages: bool,
) -> None:
    (
        resolved_run_root,
        script_path,
        manifest_path,
        docker_script_path,
        docker_manifest_path,
    ) = write_docker_stage_bundle(
        lane=legacy_baseline_lane(lane_slug),
        legacy_root=legacy_root,
        run_root=run_root,
        iterations_per_snapshot=iterations_per_snapshot,
        snapshot_count=snapshot_count,
        image=image,
        container_platform=container_platform,
        install_packages=install_packages,
    )
    _emit(
        (
            f"legacy_root: {legacy_root}",
            f"run_root: {resolved_run_root}",
            f"stage_script: {script_path}",
            f"docker_stage_script: {docker_script_path}",
            f"manifest: {manifest_path}",
            f"docker_manifest: {docker_manifest_path}",
            f"docker_image: {image}",
            f"docker_platform: {container_platform}",
            f"docker_install_packages: {install_packages}",
        )
    )


@baseline_app.command("stage-cell-sorting-docker")
def baseline_stage_cell_sorting_docker(
    legacy_root: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Path to a local checkout of the original EmbryoMaker root.",
    ),
    run_root: Path | None = typer.Option(
        None,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Directory where the staged legacy baseline bundle will be written.",
    ),
    iterations_per_snapshot: int = typer.Option(10, min=1),
    snapshot_count: int = typer.Option(100, min=1),
    image: str = typer.Option(legacy_docker_baseline_recipe().base_image),
    container_platform: str = typer.Option(legacy_docker_baseline_recipe().platform),
    install_packages: bool = typer.Option(
        True,
        "--install-packages/--skip-install-packages",
        help="Install toolchain packages inside the container at runtime.",
    ),
) -> None:
    _stage_docker_lane(
        lane_slug="cell-sorting",
        legacy_root=legacy_root,
        run_root=run_root,
        iterations_per_snapshot=iterations_per_snapshot,
        snapshot_count=snapshot_count,
        image=image,
        container_platform=container_platform,
        install_packages=install_packages,
    )


@baseline_app.command("stage-invagination-docker")
def baseline_stage_invagination_docker(
    legacy_root: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Path to a local checkout of the original EmbryoMaker root.",
    ),
    run_root: Path | None = typer.Option(
        None,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Directory where the staged legacy baseline bundle will be written.",
    ),
    iterations_per_snapshot: int = typer.Option(10, min=1),
    snapshot_count: int = typer.Option(100, min=1),
    image: str = typer.Option(legacy_docker_baseline_recipe().base_image),
    container_platform: str = typer.Option(legacy_docker_baseline_recipe().platform),
    install_packages: bool = typer.Option(
        True,
        "--install-packages/--skip-install-packages",
        help="Install toolchain packages inside the container at runtime.",
    ),
) -> None:
    _stage_docker_lane(
        lane_slug="invagination",
        legacy_root=legacy_root,
        run_root=run_root,
        iterations_per_snapshot=iterations_per_snapshot,
        snapshot_count=snapshot_count,
        image=image,
        container_platform=container_platform,
        install_packages=install_packages,
    )


@baseline_app.command("snapshot-summary")
def baseline_snapshot_summary(
    snapshot_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to a legacy .dat snapshot file.",
    ),
) -> None:
    snapshot = parse_legacy_snapshot(snapshot_path)
    summary = summarize_legacy_snapshot(snapshot)
    _emit(
        (
            f"snapshot: {snapshot_path}",
            f"run_name: {snapshot.run_name}",
            f"getot: {summary.getot}",
            f"rtime: {summary.rtime}",
            f"node_count: {summary.node_count}",
            f"cell_count: {summary.cell_count}",
            f"gene_count: {summary.gene_count}",
            f"contact_count: {summary.contact_count}",
            f"max_distance_from_origin: {summary.max_distance_from_origin}",
            f"mean_distance_from_origin: {summary.mean_distance_from_origin}",
            f"mean_neighbor_count: {summary.mean_neighbor_count}",
            f"type1_cell_count: {summary.type1_cell_count}",
            f"type2_cell_count: {summary.type2_cell_count}",
        )
    )


@baseline_app.command("snapshot-epithelium")
def baseline_snapshot_epithelium(
    snapshot_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to a legacy .dat snapshot file.",
    ),
) -> None:
    snapshot = parse_legacy_snapshot(snapshot_path)
    summary = summarize_legacy_epithelial_snapshot(snapshot)
    _emit(
        (
            f"snapshot: {snapshot_path}",
            f"run_name: {snapshot.run_name}",
            f"getot: {summary.getot}",
            f"rtime: {summary.rtime}",
            f"node_count: {summary.node_count}",
            f"cell_count: {summary.cell_count}",
            f"epithelial_node_count: {summary.epithelial_node_count}",
            f"apical_node_count: {summary.apical_node_count}",
            f"basal_node_count: {summary.basal_node_count}",
            f"paired_epithelial_node_count: {summary.paired_epithelial_node_count}",
            f"epithelial_cell_count: {summary.epithelial_cell_count}",
            f"gene1_positive_node_count: {summary.gene1_positive_node_count}",
            f"gene2_positive_node_count: {summary.gene2_positive_node_count}",
            f"gene1_positive_cell_count: {summary.gene1_positive_cell_count}",
            f"gene2_positive_cell_count: {summary.gene2_positive_cell_count}",
            f"polarized_expression_cell_count: {summary.polarized_expression_cell_count}",
            f"zero_pla_node_count: {summary.zero_pla_node_count}",
            f"zero_kvol_node_count: {summary.zero_kvol_node_count}",
            f"mean_grd: {summary.mean_grd}",
            f"mean_cod: {summary.mean_cod}",
            f"mean_pld: {summary.mean_pld}",
            f"mean_vod: {summary.mean_vod}",
        )
    )


@baseline_app.command("compare-invagination-bootstrap")
def baseline_compare_invagination_bootstrap(
    snapshot_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to a legacy .dat snapshot file.",
    ),
    executable: Path | None = typer.Option(
        None,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to the built em2_legacy_invagination_summary executable.",
    ),
    relative_tolerance: float = typer.Option(1e-12, min=0.0),
    json_out: Path | None = typer.Option(
        None,
        file_okay=True,
        dir_okay=False,
        help="Write a structured JSON comparison bundle to this path.",
    ),
) -> None:
    summary_executable = _require_built_executable(_default_invagination_executable(executable))
    payload = compare_invagination_bootstrap_payload(
        snapshot_path=snapshot_path,
        executable=summary_executable,
        relative_tolerance=relative_tolerance,
    )
    legacy = _payload_map(payload["legacy"])
    v2 = _payload_map(payload["v2"])
    _emit(
        (
            f"snapshot: {snapshot_path}",
            f"executable: {summary_executable}",
            f"legacy_getot: {legacy['getot']}",
            f"legacy_rtime: {legacy['rtime']}",
            f"v2_getot: {v2['getot']}",
            f"v2_rtime: {v2['rtime']}",
            f"matches: {payload['matches']}",
            f"decision: {payload['decision']}",
            f"reason: {payload['reason']}",
        )
    )
    if json_out is not None:
        write_json(json_out, payload)
        typer.echo(f"json_out: {json_out}")
    if not payload["matches"]:
        typer.echo("mismatches:")
        for mismatch in _string_list(payload["mismatches"]):
            typer.echo(f"- {mismatch}")


@baseline_app.command("compare-invagination")
def baseline_compare_invagination(
    snapshot_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to the legacy target .dat snapshot file.",
    ),
    bootstrap_snapshot: Path = typer.Option(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to the legacy bootstrap .dat snapshot file used to seed the v2 run.",
    ),
    executable: Path | None = typer.Option(
        None,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to the built em2_legacy_invagination_summary executable.",
    ),
    steps: int | None = typer.Option(
        None,
        min=0,
        help=(
            "Number of v2 iterations to run. When omitted, compare by the legacy "
            "snapshot rtime."
        ),
    ),
    relative_tolerance: float = typer.Option(1e-12, min=0.0),
    absolute_tolerance: float = typer.Option(
        1e-3,
        min=0.0,
        help="Maximum allowed node-wise Euclidean position error.",
    ),
    json_out: Path | None = typer.Option(
        None,
        file_okay=True,
        dir_okay=False,
        help="Write a structured JSON comparison bundle to this path.",
    ),
) -> None:
    summary_executable = _require_built_executable(_default_invagination_executable(executable))
    payload = compare_invagination_payload(
        snapshot_path=snapshot_path,
        bootstrap_snapshot=bootstrap_snapshot,
        executable=summary_executable,
        steps=steps,
        relative_tolerance=relative_tolerance,
        absolute_tolerance=absolute_tolerance,
    )
    legacy = _payload_map(payload["legacy"])
    v2 = _payload_map(payload["v2"])
    geometry = _payload_map(payload["geometry"])
    _emit(
        (
            f"snapshot: {snapshot_path}",
            f"bootstrap_snapshot: {bootstrap_snapshot}",
            f"executable: {summary_executable}",
            f"legacy_getot: {legacy['getot']}",
            f"legacy_rtime: {legacy['rtime']}",
            f"v2_getot: {v2['getot']}",
            f"v2_rtime: {v2['rtime']}",
            f"summary_matches: {payload['summary_matches']}",
            f"geometry_matches: {payload['geometry_matches']}",
            f"max_position_error: {geometry['max_position_error']}",
            f"mean_position_error: {geometry['mean_position_error']}",
            f"rms_position_error: {geometry['rms_position_error']}",
            f"matches: {payload['matches']}",
            f"decision: {payload['decision']}",
            f"reason: {payload['reason']}",
        )
    )
    if json_out is not None:
        write_json(json_out, payload)
        typer.echo(f"json_out: {json_out}")
    if payload["summary_mismatches"]:
        typer.echo("summary_mismatches:")
        for mismatch in _string_list(payload["summary_mismatches"]):
            typer.echo(f"- {mismatch}")
    if payload["geometry_mismatches"]:
        typer.echo("geometry_mismatches:")
        for mismatch in _string_list(payload["geometry_mismatches"]):
            typer.echo(f"- {mismatch}")


@baseline_app.command("compare-cell-sorting")
def baseline_compare_cell_sorting(
    snapshot_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to a legacy .dat snapshot file.",
    ),
    executable: Path | None = typer.Option(
        None,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to the built em2_legacy_cell_sorting_summary executable.",
    ),
    steps: int | None = typer.Option(
        None,
        min=0,
        help="Number of v2 iterations to run. Defaults to the legacy snapshot getot.",
    ),
    initial_seed: int = typer.Option(-11111),
    noise_seed: int | None = typer.Option(None),
    relative_tolerance: float = typer.Option(0.05, min=0.0),
    json_out: Path | None = typer.Option(
        None,
        file_okay=True,
        dir_okay=False,
        help="Write a structured JSON comparison bundle to this path.",
    ),
) -> None:
    summary_executable = _require_built_executable(_default_cell_sorting_executable(executable))
    payload = compare_cell_sorting_payload(
        snapshot_path=snapshot_path,
        executable=summary_executable,
        steps=steps,
        initial_seed=initial_seed,
        noise_seed=noise_seed,
        relative_tolerance=relative_tolerance,
    )
    legacy = _payload_map(payload["legacy"])
    v2 = _payload_map(payload["v2"])
    _emit(
        (
            f"snapshot: {snapshot_path}",
            f"executable: {summary_executable}",
            f"legacy_getot: {legacy['getot']}",
            f"v2_steps: {v2['steps']}",
            f"matches: {payload['matches']}",
            f"decision: {payload['decision']}",
            f"reason: {payload['reason']}",
        )
    )
    if json_out is not None:
        write_json(json_out, payload)
        typer.echo(f"json_out: {json_out}")
    if not payload["matches"]:
        typer.echo("mismatches:")
        for mismatch in _string_list(payload["mismatches"]):
            typer.echo(f"- {mismatch}")


@baseline_app.command("compare-cell-sorting-trajectory")
def baseline_compare_cell_sorting_trajectory(
    snapshot_dir: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Directory containing legacy .dat snapshots for the cell-sorting lane.",
    ),
    executable: Path | None = typer.Option(
        None,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
        help="Path to the built em2_legacy_cell_sorting_summary executable.",
    ),
    initial_seed: int = typer.Option(-11111),
    noise_seed: int | None = typer.Option(None),
    relative_tolerance: float = typer.Option(0.05, min=0.0),
    json_out: Path | None = typer.Option(
        None,
        file_okay=True,
        dir_okay=False,
        help="Write a structured JSON comparison bundle to this path.",
    ),
) -> None:
    summary_executable = _require_built_executable(_default_cell_sorting_executable(executable))
    try:
        payload = compare_cell_sorting_trajectory_payload(
            snapshot_dir=snapshot_dir,
            executable=summary_executable,
            initial_seed=initial_seed,
            noise_seed=noise_seed,
            relative_tolerance=relative_tolerance,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    lines = [
        f"snapshot_dir: {snapshot_dir}",
        f"executable: {summary_executable}",
        f"frame_count: {payload['frame_count']}",
        f"matches: {payload['matches']}",
        f"decision: {payload['decision']}",
        f"reason: {payload['reason']}",
    ]
    if payload["resolved_snapshot_dir"] != str(snapshot_dir):
        lines.insert(1, f"resolved_snapshot_dir: {payload['resolved_snapshot_dir']}")
    for key in (
        "bootstrap_cell_types_source",
        "bootstrap_node_positions_source",
        "bootstrap_noise_seed_source",
    ):
        value = payload[key]
        if value is not None:
            lines.insert(-4, f"{key}: {value}")
    _emit(tuple(lines))
    if json_out is not None:
        write_json(json_out, payload)
        typer.echo(f"json_out: {json_out}")
    for frame_value in _payload_list(payload["frames"]):
        frame = _payload_map(frame_value)
        legacy = _payload_map(frame["legacy"])
        typer.echo(
            f"frame: {frame['label']} getot={legacy['getot']} matches={frame['matches']}"
        )
        for mismatch in _string_list(frame["mismatches"]):
            typer.echo(f"- {mismatch}")
