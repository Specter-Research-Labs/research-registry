from __future__ import annotations

from lenia_swarm_analysis._commands import OBSERVER
from lenia_swarm_analysis._dispatch import dispatch_command_group


def main(argv: list[str] | None = None) -> int:
    return dispatch_command_group(argv, OBSERVER)
