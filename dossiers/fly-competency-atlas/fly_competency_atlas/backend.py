from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import typer

BACKEND_APP = typer.Typer(no_args_is_help=True, add_completion=False)

_DEFAULT_IMAGE = "fruitflybrain/fbl:latest"
_DEFAULT_NAME = "flybrainlab-backend"
_DEFAULT_UI_PORT = 9999
_DEFAULT_PROCESSOR_PORT = 8081


class BackendError(RuntimeError):
    """Raised when the backend helper cannot continue safely."""


@dataclass(frozen=True)
class HostReport:
    system: str
    machine: str
    docker_available: bool
    docker_version: str | None
    nvidia_smi_available: bool
    execution_capable_local_backend: bool
    recommended_processor_url: str | None
    recommended_path: str
    blocker: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@BACKEND_APP.command("doctor")
def doctor(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    report = detect_host()
    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return
    typer.echo(f"Host: {report.system} {report.machine}")
    if report.docker_available:
        typer.echo(f"Docker: {report.docker_version}")
    else:
        typer.echo("Docker: missing")
    typer.echo(f"NVIDIA GPU tooling: {'present' if report.nvidia_smi_available else 'missing'}")
    typer.echo(
        "Execution-capable local backend: "
        + ("yes" if report.execution_capable_local_backend else "no")
    )
    if report.recommended_processor_url is not None:
        typer.echo(f"Recommended processor url: {report.recommended_processor_url}")
    typer.echo(f"Recommended path: {report.recommended_path}")
    if report.blocker is not None:
        typer.echo(f"Blocker: {report.blocker}")


@BACKEND_APP.command("probe")
def probe(
    processor_url: str = typer.Option(
        ...,
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
    runtime_python: Path | None = typer.Option(
        None,
        "--runtime-python",
        envvar="FLYBRAINLAB_RUNTIME_PYTHON",
        help="Python interpreter inside the dedicated FlyBrainLab env.",
    ),
    user: str = typer.Option("guest", "--user"),
    secret: str = typer.Option("guestpass", "--secret"),
    connect_timeout_s: int = typer.Option(20, "--connect-timeout-s"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    runtime_python = runtime_python or default_runtime_python()
    if not runtime_python.exists():
        raise BackendError(
            f"runtime python does not exist: {runtime_python}. Create it with "
            "./scripts/bootstrap_flybrainlab_user_side.sh /path/to/python3.9 .venv-flybrainlab"
        )
    command = [
        str(runtime_python),
        "-m",
        "fly_competency_atlas.backend_runtime",
        "--processor-url",
        processor_url,
        "--user",
        user,
        "--secret",
        secret,
        "--connect-timeout-s",
        str(connect_timeout_s),
    ]
    if dataset is not None:
        command.extend(["--dataset", dataset])
    env = _runtime_env(runtime_python)
    result = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
    payload = _load_payload(result.stdout)
    if json_output and payload is not None:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    elif payload is not None:
        _print_probe_payload(payload)
    elif result.stdout.strip():
        typer.echo(result.stdout.rstrip())
    if result.stderr.strip():
        typer.echo(result.stderr.rstrip(), err=True)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


def detect_host() -> HostReport:
    system = platform.system().lower()
    machine = platform.machine().lower()
    docker_version = _command_version(("docker", "--version"))
    docker_available = docker_version is not None
    nvidia_smi_available = shutil.which("nvidia-smi") is not None
    processor_url = f"ws://localhost:{_DEFAULT_PROCESSOR_PORT}/ws"
    if system == "darwin" and machine in {"arm64", "aarch64"}:
        return HostReport(
            system=system,
            machine=machine,
            docker_available=docker_available,
            docker_version=docker_version,
            nvidia_smi_available=nvidia_smi_available,
            execution_capable_local_backend=False,
            recommended_processor_url=None,
            recommended_path="remote Linux x86_64 host with NVIDIA GPU, or FFBO AMI",
            blocker=(
                "FlyBrainLab full execution depends on NVIDIA CUDA. Apple silicon can run the "
                "user-side tools, but not a credible local Neurokernel backend."
            ),
        )
    if system != "linux":
        return HostReport(
            system=system,
            machine=machine,
            docker_available=docker_available,
            docker_version=docker_version,
            nvidia_smi_available=nvidia_smi_available,
            execution_capable_local_backend=False,
            recommended_processor_url=None,
            recommended_path="Linux x86_64 host with NVIDIA GPU",
            blocker=(
                "The upstream full backend expects a Linux CUDA stack. Use a Linux x86_64 "
                "machine or cloud GPU host."
            ),
        )
    if machine not in {"x86_64", "amd64"}:
        return HostReport(
            system=system,
            machine=machine,
            docker_available=docker_available,
            docker_version=docker_version,
            nvidia_smi_available=nvidia_smi_available,
            execution_capable_local_backend=False,
            recommended_processor_url=None,
            recommended_path="Linux x86_64 host with NVIDIA GPU",
            blocker="The upstream backend is built around x86_64 CUDA tooling.",
        )
    if not docker_available:
        return HostReport(
            system=system,
            machine=machine,
            docker_available=docker_available,
            docker_version=docker_version,
            nvidia_smi_available=nvidia_smi_available,
            execution_capable_local_backend=False,
            recommended_processor_url=None,
            recommended_path="install Docker first, then launch the FlyBrainLab image",
            blocker="Docker is not installed on this host.",
        )
    if not nvidia_smi_available:
        return HostReport(
            system=system,
            machine=machine,
            docker_available=docker_available,
            docker_version=docker_version,
            nvidia_smi_available=nvidia_smi_available,
            execution_capable_local_backend=False,
            recommended_processor_url=None,
            recommended_path="Linux x86_64 host with NVIDIA GPU and Docker GPU support",
            blocker=(
                "No NVIDIA GPU tooling detected. The upstream full backend requires CUDA for "
                "Neurokernel execution."
            ),
        )
    return HostReport(
        system=system,
        machine=machine,
        docker_available=docker_available,
        docker_version=docker_version,
        nvidia_smi_available=nvidia_smi_available,
        execution_capable_local_backend=True,
        recommended_processor_url=processor_url,
        recommended_path="launch the upstream Docker image locally",
        blocker=None,
    )


def default_runtime_python() -> Path:
    return Path(__file__).resolve().parent.parent / ".venv-flybrainlab/bin/python"


def docker_run_command(
    *,
    image: str = _DEFAULT_IMAGE,
    name: str = _DEFAULT_NAME,
    ui_port: int = _DEFAULT_UI_PORT,
    processor_port: int = _DEFAULT_PROCESSOR_PORT,
    database_dir: Path | None = None,
) -> tuple[str, ...]:
    command: list[str] = [
        "docker",
        "run",
        "--name",
        name,
        "--gpus",
        "all",
        "-p",
        f"{ui_port}:8888",
        "-p",
        f"{processor_port}:8081",
    ]
    if database_dir is not None:
        command.extend(
            [
                "-v",
                f"{database_dir.resolve()}:/home/ffbo/orientdb/databases",
            ]
        )
    command.extend(["-it", image])
    return tuple(command)


def format_docker_run_command(
    *,
    image: str = _DEFAULT_IMAGE,
    name: str = _DEFAULT_NAME,
    ui_port: int = _DEFAULT_UI_PORT,
    processor_port: int = _DEFAULT_PROCESSOR_PORT,
    database_dir: Path | None = None,
) -> str:
    return shlex.join(
        docker_run_command(
            image=image,
            name=name,
            ui_port=ui_port,
            processor_port=processor_port,
            database_dir=database_dir,
        )
    )


def _command_version(command: tuple[str, ...]) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or result.stderr.strip() or None


def _runtime_env(runtime_python: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{runtime_python.parent}{os.pathsep}{env.get('PATH', '')}"
    dossier_root = Path(__file__).resolve().parent.parent
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(dossier_root)
        if not existing_pythonpath
        else f"{dossier_root}{os.pathsep}{existing_pythonpath}"
    )
    return env


def _load_payload(stdout: str) -> dict[str, object] | None:
    if not stdout.strip():
        return None
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _print_probe_payload(payload: dict[str, object]) -> None:
    typer.echo(f"Processor: {payload.get('processor_url', 'unknown')}")
    typer.echo(f"Status: {payload.get('status', 'unknown')}")
    if "dataset" in payload and payload["dataset"] is not None:
        typer.echo(f"Dataset: {payload['dataset']}")
    datasets = payload.get("datasets")
    if isinstance(datasets, list) and datasets:
        typer.echo(f"Datasets: {', '.join(str(item) for item in datasets)}")
    if "execution_supported" in payload:
        execution_supported = bool(payload["execution_supported"])
        typer.echo(
            "Execution support: " + ("available" if execution_supported else "missing Neurokernel")
        )
    if "na_count" in payload:
        typer.echo(
            f"Servers: na={payload.get('na_count', 0)} "
            f"nlp={payload.get('nlp_count', 0)} nk={payload.get('nk_count', 0)}"
        )
    if "message" in payload and payload["message"] is not None:
        typer.echo(f"Message: {payload['message']}")
