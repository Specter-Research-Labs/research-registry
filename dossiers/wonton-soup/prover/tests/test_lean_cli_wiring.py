from __future__ import annotations

import re
from pathlib import Path

import wonton

LEAN_CLI = Path(wonton.__file__).resolve().parent / "orchestrator" / "lean_cli.py"


def test_every_arg_lean_cli_reads_is_a_wonton_lean_option() -> None:
    source = LEAN_CLI.read_text(encoding="utf-8")
    read = set(re.findall(r"args\.(\w+)", source)) | set(
        re.findall(r'getattr\(args,\s*"(\w+)"', source)
    )
    missing = read - set(wonton._LEAN_COMMAND_PARAM_NAMES)
    assert not missing, f"lean_cli.py reads args not passed by wonton lean: {sorted(missing)}"
