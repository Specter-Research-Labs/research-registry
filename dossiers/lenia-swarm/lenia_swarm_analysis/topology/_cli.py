from __future__ import annotations

from lenia_swarm_analysis._commands import GROUPS_BY_NAME
from lenia_swarm_analysis._dispatch import dispatch_command_group

GROUP = GROUPS_BY_NAME["topology"]
COMMANDS = GROUP.commands


def main(argv: list[str] | None = None) -> int:
    return dispatch_command_group(argv, GROUP)


if __name__ == "__main__":
    raise SystemExit(main())
