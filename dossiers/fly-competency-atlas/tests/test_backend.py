from pathlib import Path

from fly_competency_atlas.backend import (
    detect_host,
    docker_run_command,
    format_docker_run_command,
)
from fly_competency_atlas.backend_runtime import extract_datasets_from_error, valid_datasets


def test_detect_host_blocks_apple_silicon(monkeypatch) -> None:
    monkeypatch.setattr("fly_competency_atlas.backend.platform.system", lambda: "Darwin")
    monkeypatch.setattr("fly_competency_atlas.backend.platform.machine", lambda: "arm64")
    monkeypatch.setattr("fly_competency_atlas.backend._command_version", lambda _cmd: "Docker 28")
    monkeypatch.setattr(
        "fly_competency_atlas.backend.shutil.which",
        lambda name: "/usr/bin/docker" if name == "nvidia-smi" else None,
    )
    report = detect_host()
    assert report.execution_capable_local_backend is False
    assert report.blocker is not None
    assert "Apple silicon" in report.blocker


def test_detect_host_accepts_linux_nvidia(monkeypatch) -> None:
    monkeypatch.setattr("fly_competency_atlas.backend.platform.system", lambda: "Linux")
    monkeypatch.setattr("fly_competency_atlas.backend.platform.machine", lambda: "x86_64")
    monkeypatch.setattr("fly_competency_atlas.backend._command_version", lambda _cmd: "Docker 28")
    monkeypatch.setattr("fly_competency_atlas.backend.shutil.which", lambda _name: "/usr/bin/tool")
    report = detect_host()
    assert report.execution_capable_local_backend is True
    assert report.recommended_processor_url == "ws://localhost:8081/ws"


def test_docker_run_command_exposes_processor_port() -> None:
    database_dir = Path("/tmp/fbl-db").resolve()
    command = docker_run_command(
        name="fbl-test",
        ui_port=9999,
        processor_port=8081,
        database_dir=database_dir,
    )
    assert "-p" in command
    assert "8081:8081" in command
    assert f"{database_dir}:/home/ffbo/orientdb/databases" in command
    rendered = format_docker_run_command(
        name="fbl-test",
        ui_port=9999,
        processor_port=8081,
        database_dir=database_dir,
    )
    assert "fruitflybrain/fbl:latest" in rendered


def test_valid_datasets_requires_na_and_nlp() -> None:
    datasets = valid_datasets(
        {
            "na": {
                "a": {"dataset": "hemibrain"},
                "b": {"dataset": "optic_lobe"},
            },
            "nlp": {
                "c": {"dataset": "hemibrain"},
            },
        }
    )
    assert datasets == ("hemibrain",)


def test_extract_datasets_from_backend_error() -> None:
    message = (
        "Multiple valid datasets are available on the specified FFBO processor. "
        "However, you did not specify which dataset to connect to. "
        "Available datasets on the FFBO processor are the following:\n"
        "- hemibrain\n"
        "- optic_lobe\n\n"
        ". Please choose one of the above datasets during Client connection by passing the "
        "dataset argument."
    )
    assert extract_datasets_from_error(message) == ("hemibrain", "optic_lobe")
