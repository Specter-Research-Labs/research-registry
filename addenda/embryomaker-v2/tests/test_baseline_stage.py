import json
from pathlib import Path

from typer.testing import CliRunner

from embryomaker_v2.cli import app

runner = CliRunner()


def _make_legacy_root(tmp_path: Path) -> Path:
    legacy_root = tmp_path / "EmbryoMaker"
    legacy_root.mkdir()
    (legacy_root / "compile_EmbryoMaker.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (legacy_root / "config_file.txt").write_text("1\n2\n3\n4\n1\n", encoding="utf-8")
    return legacy_root


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_docker_stage_commands_write_native_and_container_runners(tmp_path: Path) -> None:
    legacy_root = _make_legacy_root(tmp_path)
    cases = [
        {
            "command": "stage-cell-sorting-docker",
            "run_root": tmp_path / "baseline-cell",
            "native_script": "run_legacy_cell_sorting.sh",
            "docker_script": "run_legacy_cell_sorting_docker.sh",
            "docker_manifest": "cell_sorting_docker_manifest.json",
            "native_fragments": ['rm -rf "$ARTIFACTS_ROOT"', 'EMAKER_PATH="./bin"'],
        },
        {
            "command": "stage-invagination-docker",
            "run_root": tmp_path / "baseline-invagination",
            "native_script": "run_legacy_invagination.sh",
            "docker_script": "run_legacy_invagination_docker.sh",
            "docker_manifest": "invagination_docker_manifest.json",
            "native_fragments": ['lines[4] = "3"'],
            "lane_manifest": "invagination_manifest.json",
            "lane": "invagination",
            "preset": "3",
        },
    ]

    for case in cases:
        run_root = case["run_root"]
        result = runner.invoke(
            app,
            [
                "baseline",
                str(case["command"]),
                str(legacy_root),
                "--run-root",
                str(run_root),
                "--snapshot-count",
                "2",
            ],
        )

        assert result.exit_code == 0
        native_script = run_root / str(case["native_script"])
        docker_script = run_root / str(case["docker_script"])
        docker_manifest = run_root / str(case["docker_manifest"])
        assert native_script.is_file()
        assert docker_script.is_file()
        assert docker_manifest.is_file()

        native_script_text = native_script.read_text(encoding="utf-8")
        assert '"$EMAKER_PATH" 0 01 10 2' in native_script_text
        for fragment in case["native_fragments"]:
            assert fragment in native_script_text

        docker_script_text = docker_script.read_text(encoding="utf-8")
        assert "--platform linux/amd64" in docker_script_text
        assert "debian:bookworm-slim" in docker_script_text
        assert str(native_script) in docker_script_text
        assert str(legacy_root) in docker_script_text
        assert str(run_root.resolve()) in docker_script_text

        docker_manifest_payload = _read_json(docker_manifest)
        assert docker_manifest_payload["install_packages"] is True
        if "lane" in case:
            manifest = _read_json(run_root / str(case["lane_manifest"]))
            assert manifest["lane"] == case["lane"]
            assert manifest["preset_selection"]["value"] == case["preset"]
            assert docker_manifest_payload["lane"] == case["lane"]
        else:
            assert (
                "apt-get install -y gfortran freeglut3-dev libglu1-mesa-dev "
                "libgl1-mesa-dev python3" in docker_script_text
            )


def test_stage_cell_sorting_docker_can_skip_package_install_for_prebuilt_image(
    tmp_path: Path,
) -> None:
    legacy_root = _make_legacy_root(tmp_path)
    run_root = tmp_path / "baseline"

    result = runner.invoke(
        app,
        [
            "baseline",
            "stage-cell-sorting-docker",
            str(legacy_root),
            "--run-root",
            str(run_root),
            "--image",
            "embryomaker-v2-legacy-baseline:bookworm-slim",
            "--skip-install-packages",
        ],
    )

    assert result.exit_code == 0
    docker_script = run_root / "run_legacy_cell_sorting_docker.sh"
    docker_manifest = run_root / "cell_sorting_docker_manifest.json"

    docker_script_text = docker_script.read_text(encoding="utf-8")
    assert "embryomaker-v2-legacy-baseline:bookworm-slim" in docker_script_text
    assert "apt-get install -y" not in docker_script_text

    manifest = _read_json(docker_manifest)
    assert manifest["install_packages"] is False
