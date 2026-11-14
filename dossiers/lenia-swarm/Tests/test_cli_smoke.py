from __future__ import annotations

import importlib
import pkgutil
import re

import pytest

import lenia_swarm_analysis
from lenia_swarm_analysis import _cli
from lenia_swarm_analysis._commands import ANATOMICAL_COMPILER, OBSERVER, ROOT_COMMANDS


def _help(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as exit_info:
        _cli.main([*argv, "--help"])
    assert exit_info.value.code == 0, argv
    return capsys.readouterr().out


def _subparser_names(group: str, capsys: pytest.CaptureFixture[str]) -> list[str]:
    choices = re.search(r"\{([^}]+)\}", _help([group], capsys))
    assert choices is not None, group
    return choices.group(1).split(",")


def test_every_module_imports() -> None:
    for module in pkgutil.walk_packages(lenia_swarm_analysis.__path__, "lenia_swarm_analysis."):
        importlib.import_module(module.name)


@pytest.mark.parametrize("command", [command.name for command in ROOT_COMMANDS])
def test_root_command_help(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert f"lenia-swarm-analysis {command}" in _help([command], capsys)


@pytest.mark.parametrize(
    ("group", "command"),
    [(group.name, command.name) for group in (OBSERVER, ANATOMICAL_COMPILER) for command in group.commands],
)
def test_group_command_help(group: str, command: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert f"lenia-swarm-analysis {group} {command}" in _help([group, command], capsys)


@pytest.mark.parametrize("group", ["morphospace", "waddington"])
def test_subparser_command_help(group: str, capsys: pytest.CaptureFixture[str]) -> None:
    names = _subparser_names(group, capsys)
    assert len(names) > 10
    for name in names:
        assert f"lenia-swarm-analysis {group} {name}" in _help([group, name], capsys)
