from __future__ import annotations

import platform
import shutil
import subprocess

import typer

from embryomaker_v2.baseline_cli import baseline_app
from embryomaker_v2.baseline_support import (
    legacy_cell_sorting_preset,
    render_preset,
    repo_root,
)
from embryomaker_v2.baseline_support import (
    trajectory_bootstrap_frame as _trajectory_bootstrap_frame,
)

__all__ = ["app", "main", "_trajectory_bootstrap_frame", "subprocess"]


def _tool_line(name: str) -> str:
    path = shutil.which(name)
    return f"{name}: {path}" if path is not None else f"{name}: missing"


app = typer.Typer(no_args_is_help=True, help="EmbryoMaker v2 scaffold CLI")
preset_app = typer.Typer(no_args_is_help=True, help="Legacy parity presets")
app.add_typer(baseline_app, name="baseline")
app.add_typer(preset_app, name="preset")


def _emit(lines: tuple[str, ...]) -> None:
    for line in lines:
        typer.echo(line)


@preset_app.command("cell-sorting")
def preset_cell_sorting() -> None:
    _emit(render_preset(legacy_cell_sorting_preset()))


@app.command()
def doctor() -> None:
    _emit(
        (
            f"project_root: {repo_root()}",
            f"platform: {platform.platform()}",
            *(_tool_line(name) for name in ("clang++", "cmake", "python3", "uv")),
        )
    )


@app.command()
def layout() -> None:
    _emit(
        (
            "kernel_modules:",
            "- core",
            "- model",
            "- state",
            "- mechanics",
            "- fields",
            "- regulation",
            "- events",
            "- scheduler",
            "- io",
            "- api",
            "compiled_boundary:",
            "- neighbors and contacts",
            "- mechanics",
            "- fields",
            "- regulation",
            "- events",
            "- checkpoints",
            "python_boundary:",
            "- experiment authoring",
            "- sweeps",
            "- calibration",
            "- analysis",
            "- plotting",
        )
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
