import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple

import pytest
from typer.testing import CliRunner

from embryomaker_v2.cli import _trajectory_bootstrap_frame, app
from embryomaker_v2.legacy_snapshot import LegacySnapshotSeries, LegacySnapshotSummary

runner = CliRunner()


class StageCase(NamedTuple):
    command: str
    run_script: str
    manifest: str
    preset: str
    script_fragments: tuple[str, ...]
    lane: str | None = None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _make_legacy_root(root: Path) -> Path:
    legacy_root = root / "legacy"
    legacy_root.mkdir()
    (legacy_root / "compile_EmbryoMaker.sh").write_text(
        "#!/usr/bin/env bash\n",
        encoding="utf-8",
    )
    (legacy_root / "config_file.txt").write_text("0\n0\n0\n0\n1\n", encoding="utf-8")
    return legacy_root


def test_stage_commands_write_manifest_and_script() -> None:
    cases = (
        StageCase(
            command="stage-cell-sorting",
            run_script="run_legacy_cell_sorting.sh",
            manifest="cell_sorting_manifest.json",
            preset="2",
            script_fragments=('rm -rf "$ARTIFACTS_ROOT"', 'EMAKER_PATH="./bin"'),
        ),
        StageCase(
            command="stage-invagination",
            run_script="run_legacy_invagination.sh",
            manifest="invagination_manifest.json",
            preset="3",
            script_fragments=('lines[4] = "3"',),
            lane="invagination",
        ),
    )

    with runner.isolated_filesystem():
        root = Path.cwd()
        legacy_root = _make_legacy_root(root)

        for case in cases:
            run_root = root / f"staged-{case.command}"
            result = runner.invoke(
                app,
                [
                    "baseline",
                    case.command,
                    str(legacy_root),
                    "--run-root",
                    str(run_root),
                    "--iterations-per-snapshot",
                    "12",
                    "--snapshot-count",
                    "34",
                ],
            )

            assert result.exit_code == 0
            assert "run_command: ./bin 0 01 12 34" in result.stdout
            stage_script = run_root / case.run_script
            manifest_path = run_root / case.manifest
            assert stage_script.is_file()
            assert manifest_path.is_file()

            stage_script_text = stage_script.read_text(encoding="utf-8")
            assert '"$EMAKER_PATH" 0 01 12 34' in stage_script_text
            for fragment in case.script_fragments:
                assert fragment in stage_script_text

            manifest = _read_json(manifest_path)
            assert manifest["expected_exit_code"] == 231
            assert manifest["run_command"] == "./bin 0 01 12 34"
            assert manifest["preset_selection"]["line_number"] == 5
            assert manifest["preset_selection"]["value"] == case.preset
            if case.lane is not None:
                assert manifest["lane"] == case.lane
            else:
                assert manifest["binary_resolution"]["primary_path"] == "bin"
                assert manifest["binary_resolution"]["fallback_path"] == "bin/EMaker"


def test_build_docker_image_writes_context_and_invokes_docker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], check: bool) -> SimpleNamespace:
        assert check is True
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("embryomaker_v2.cli.subprocess.run", fake_run)
    context_root = tmp_path / "docker-image"

    result = runner.invoke(
        app,
        [
            "baseline",
            "build-docker-image",
            "--context-root",
            str(context_root),
            "--image",
            "embryomaker-v2-legacy-baseline:test",
        ],
    )

    assert result.exit_code == 0
    dockerfile = context_root / "Dockerfile"
    manifest_path = context_root / "cell_sorting_docker_image_manifest.json"
    assert dockerfile.is_file()
    assert manifest_path.is_file()

    dockerfile_text = dockerfile.read_text(encoding="utf-8")
    assert "FROM debian:bookworm-slim" in dockerfile_text
    assert "apt-get install -y gfortran freeglut3-dev" in dockerfile_text

    manifest = _read_json(manifest_path)
    assert manifest["image"] == "embryomaker-v2-legacy-baseline:test"
    assert manifest["platform"] == "linux/amd64"
    assert "--skip-install-packages" in manifest["stage_command"]

    assert commands == [
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "-t",
            "embryomaker-v2-legacy-baseline:test",
            "--pull",
            str(context_root.resolve()),
        ]
    ]


def test_trajectory_bootstrap_frame_rejects_nonzero_getot() -> None:
    with pytest.raises(ValueError, match="trajectory bootstrap frame must start at getot 0"):
        _trajectory_bootstrap_frame(
            LegacySnapshotSeries(
                frames=(
                    LegacySnapshotSummary(
                        path=Path("10.dat"),
                        getot=10,
                        rtime=0.25,
                        node_count=8,
                        cell_count=1,
                        gene_count=1,
                        contact_count=0,
                        max_distance_from_origin=0.0,
                        mean_distance_from_origin=0.0,
                        mean_neighbor_count=0.0,
                        type1_cell_count=1,
                        type2_cell_count=0,
                    ),
                )
            )
        )
