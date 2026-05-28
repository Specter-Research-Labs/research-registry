from __future__ import annotations

import argparse
from importlib import import_module
from typing import NamedTuple


class Subcommand(NamedTuple):
    name: str
    module: str
    help: str


def dispatch_subcommands(
    argv: list[str] | None,
    *,
    prog: str,
    description: str,
    package: str,
    commands: tuple[Subcommand, ...],
) -> int:
    parser = argparse.ArgumentParser(prog=prog, description=description)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in commands:
        subparsers.add_parser(command.name, add_help=False, help=command.help)

    args, remaining = parser.parse_known_args(argv)
    modules_by_command = {command.name: command.module for command in commands}
    module_name = modules_by_command.get(str(args.command))
    if module_name is None:
        raise SystemExit(f"unknown command: {args.command}")
    run = import_module(f"{package}.{module_name}").main
    return run(remaining)
