from __future__ import annotations

from types import SimpleNamespace

from lenia_swarm_analysis import _cli, _dispatch
from lenia_swarm_analysis._commands import GROUPS_BY_NAME
from lenia_swarm_analysis._dispatch import Subcommand


def test_dispatch_subcommands_loads_selected_module_and_forwards_args(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def fake_import_module(name: str) -> SimpleNamespace:
        def fake_main(argv: list[str]) -> int:
            calls.append((name, argv))
            return 7

        return SimpleNamespace(main=fake_main)

    monkeypatch.setattr(_dispatch, "import_module", fake_import_module)

    assert (
        _dispatch.dispatch_subcommands(
            ["selected", "--output", "packet.json"],
            prog="lenia-test",
            description="test dispatcher",
            package="lenia_swarm_analysis.test_package",
            commands=(
                Subcommand("other", "other_module", "Other command"),
                Subcommand("selected", "selected_module", "Selected command"),
            ),
        )
        == 7
    )
    assert calls == [
        (
            "lenia_swarm_analysis.test_package.selected_module",
            ["--output", "packet.json"],
        )
    ]


def test_root_cli_routes_analysis_family_and_forwards_args(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def fake_import_module(name: str) -> SimpleNamespace:
        def fake_main(argv: list[str]) -> int:
            calls.append((name, argv))
            return 0

        return SimpleNamespace(main=fake_main)

    monkeypatch.setattr(_dispatch, "import_module", fake_import_module)

    assert _cli.main(["fiber", "continuation", "--run-dir", "runs/a"]) == 0
    assert calls == [
        (
            "lenia_swarm_analysis.fiber._cli",
            ["continuation", "--run-dir", "runs/a"],
        )
    ]


def test_group_cli_uses_shared_registry_and_forwards_args(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def fake_import_module(name: str) -> SimpleNamespace:
        def fake_main(argv: list[str]) -> int:
            calls.append((name, argv))
            return 0

        return SimpleNamespace(main=fake_main)

    monkeypatch.setattr(_dispatch, "import_module", fake_import_module)

    assert (
        _dispatch.dispatch_command_group(
            ["continuation", "--run-dir", "runs/a"],
            GROUPS_BY_NAME["fiber"],
        )
        == 0
    )
    assert calls == [
        (
            "lenia_swarm_analysis.fiber.continuation",
            ["--run-dir", "runs/a"],
        )
    ]
