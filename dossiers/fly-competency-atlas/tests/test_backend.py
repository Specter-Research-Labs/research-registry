from pathlib import Path

from typer.testing import CliRunner

from fly_competency_atlas.backend import (
    BACKEND_APP,
    HostReport,
    detect_host,
    docker_run_command,
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
    assert command[-1] == "fruitflybrain/fbl:latest"


def _host_report(blocker: str | None) -> HostReport:
    return HostReport(
        system="linux",
        machine="x86_64",
        docker_available=True,
        docker_version="Docker 28",
        nvidia_smi_available=True,
        execution_capable_local_backend=blocker is None,
        recommended_processor_url=None,
        recommended_path="local",
        blocker=blocker,
    )


def test_start_execs_docker_with_requested_ports(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        "fly_competency_atlas.backend.detect_host",
        lambda: _host_report(None),
    )
    monkeypatch.setattr(
        "fly_competency_atlas.backend.os.execvp",
        lambda file, args: calls.append((file, list(args))),
    )
    database_dir = tmp_path / "db"
    result = CliRunner().invoke(
        BACKEND_APP,
        ["start", "--name", "fbl", "--processor-port", "9000", "--database-dir", str(database_dir)],
    )
    assert result.exit_code == 0, result.output
    assert database_dir.is_dir()
    assert calls[0][0] == "docker"
    assert "9000:8081" in calls[0][1]
    assert f"{database_dir.resolve()}:/home/ffbo/orientdb/databases" in calls[0][1]


def test_start_refuses_blocked_host(monkeypatch) -> None:
    monkeypatch.setattr(
        "fly_competency_atlas.backend.detect_host",
        lambda: _host_report("no CUDA"),
    )
    monkeypatch.setattr(
        "fly_competency_atlas.backend.os.execvp",
        lambda file, args: (_ for _ in ()).throw(AssertionError("must not launch")),
    )
    result = CliRunner().invoke(BACKEND_APP, ["start"])
    assert result.exit_code == 1
    assert "no CUDA" in result.output


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
