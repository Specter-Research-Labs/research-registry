from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
from dataclasses import asdict, dataclass
from typing import Any

import typer

from fly_competency_atlas.backend import BACKEND_APP
from fly_competency_atlas.lamina import LAMINA_APP
from fly_competency_atlas.registry import catalog
from fly_competency_atlas.upstream import UpstreamError, fetch_datasets, fetch_tutorials

app = typer.Typer(no_args_is_help=True, add_completion=False)
app.add_typer(BACKEND_APP, name="backend")
app.add_typer(LAMINA_APP, name="lamina")

_DOCTOR_PACKAGES = (
    "flybrainlab",
    "neuromynerva",
    "jupyterlab",
    "nxt-gem",
)


@dataclass(frozen=True)
class PackageStatus:
    package: str
    installed: bool
    version: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def main() -> None:
    app()


@app.command()
def doctor(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    payload = {
        "harness_python": {
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "flybrainlab_user_side_runtime": {
            "recommended_python": "3.9.x",
            "why": (
                "FlyBrainLab upstream still pins JupyterLab >=3.0,<3.6 for the user-side stack."
            ),
            "bootstrap_script": (
                "./scripts/bootstrap_flybrainlab_user_side.sh "
                "/path/to/python3.9 .venv-flybrainlab"
            ),
        },
        "packages": [status.to_dict() for status in _package_statuses()],
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"Harness interpreter: {payload['harness_python']['version']}")
    typer.echo(f"Executable: {payload['harness_python']['executable']}")
    typer.echo("FlyBrainLab user-side runtime: Python 3.9.x in a separate env")
    typer.echo(
        "Reason: FlyBrainLab upstream still expects JupyterLab >=3.0,<3.6 for the "
        "interactive client."
    )
    typer.echo(f"Bootstrap: {payload['flybrainlab_user_side_runtime']['bootstrap_script']}")
    typer.echo("")
    for status in _package_statuses():
        version = status.version if status.version is not None else "missing"
        typer.echo(f"{status.package}: {version}")


@app.command("catalog")
def catalog_command(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    entries = [entry.to_dict() for entry in catalog()]
    if json_output:
        typer.echo(json.dumps(entries, indent=2, sort_keys=True))
        return
    for entry in catalog():
        typer.echo(f"{entry.slug} [{entry.readiness}]")
        typer.echo(f"  {entry.name}")
        typer.echo(f"  kind={entry.surface_kind} upstream={entry.upstream_surface}")
        typer.echo(f"  claims={', '.join(entry.first_claims)}")
        typer.echo(f"  metrics={', '.join(entry.first_metrics)}")
        typer.echo(f"  tasks={', '.join(entry.first_tasks)}")
        typer.echo("")


@app.command()
def inventory(
    source: str = typer.Option("all", "--source", help="One of: all, tutorials, datasets."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    if source not in {"all", "tutorials", "datasets"}:
        raise typer.BadParameter("source must be one of: all, tutorials, datasets")
    payload: dict[str, Any] = {}
    try:
        if source in {"all", "tutorials"}:
            payload["tutorials"] = [record.to_dict() for record in fetch_tutorials()]
        if source in {"all", "datasets"}:
            payload["datasets"] = [record.to_dict() for record in fetch_datasets()]
    except UpstreamError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    if "tutorials" in payload:
        typer.echo("Tutorials")
        for record in payload["tutorials"]:
            typer.echo(f"  {record['level']}: {record['name']}")
            typer.echo(f"    {record['url']}")
    if "datasets" in payload:
        if "tutorials" in payload:
            typer.echo("")
        typer.echo("Datasets")
        for record in payload["datasets"]:
            typer.echo(f"  {record['dataset']}: {record['version']} ({record['last_update']})")
            if record["loading_script_url"] is not None:
                typer.echo(f"    loading={record['loading_script_url']}")
            if record["neuronlp_url"] is not None:
                typer.echo(f"    neuronlp={record['neuronlp_url']}")


def _package_statuses() -> tuple[PackageStatus, ...]:
    statuses = []
    for package in _DOCTOR_PACKAGES:
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            statuses.append(PackageStatus(package=package, installed=False, version=None))
            continue
        statuses.append(PackageStatus(package=package, installed=True, version=version))
    return tuple(statuses)
