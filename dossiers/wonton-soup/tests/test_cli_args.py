"""Tests for CLI argument wiring used by lean_cli.py."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

DOSSIER = Path(__file__).resolve().parents[1]


def _import_app():
    """Import wonton app, skipping heavy runtime assertions."""
    import importlib
    import sys

    # runtime_env.assert_wonton_python_runtime() can fail outside the full
    # environment; patch it out so the module loads cleanly.
    stub = type(sys)("runtime_env")
    stub.assert_wonton_python_runtime = lambda: None
    sys.modules.setdefault("runtime_env", stub)

    sys.path.insert(0, str(DOSSIER))
    mod = importlib.import_module("wonton")
    return mod


def _attrs_read_by_lean_cli() -> set[str]:
    """Parse orchestrator/lean_cli.py for bare args.ATTR accesses."""
    src = (DOSSIER / "orchestrator" / "lean_cli.py").read_text()
    # args.foo (direct attribute access, not getattr)
    direct = set(re.findall(r"args\.(\w+)", src))
    # getattr(args, "foo" ...) — these have defaults so won't crash,
    # but still should be wired for correctness
    via_getattr = set(re.findall(r'getattr\(args,\s*"(\w+)"', src))
    return direct | via_getattr


def _lean_command_option_names() -> set[str]:
    """Read the real option-name tuple from wonton.py."""
    return set(_import_app()._LEAN_COMMAND_OPTION_NAMES)


def _lean_command_signature_params() -> set[str]:
    """Read _run_lean_command's real signature from wonton.py."""
    signature = inspect.signature(_import_app()._run_lean_command)
    return set(signature.parameters) - {"self"}


# Names that lean_cli.py uses but that are added by _run_lean_command itself
# (not from CLI options). These are safe to exclude.
_INTERNALLY_ADDED = {
    "no_sync",  # derived from --sync/--no-sync
}


def test_lean_cli_args_are_wired():
    """Every attribute lean_cli.py reads from args must be present in the
    namespace built by _LEAN_COMMAND_OPTION_NAMES or added internally."""
    needed = _attrs_read_by_lean_cli()
    provided = _lean_command_option_names() | _INTERNALLY_ADDED
    missing = needed - provided
    assert not missing, (
        f"lean_cli.py reads args.X for attributes not in "
        f"_LEAN_COMMAND_OPTION_NAMES or _INTERNALLY_ADDED: {sorted(missing)}"
    )


def test_lean_command_option_names_match_signature():
    """_LEAN_COMMAND_OPTION_NAMES should be a subset of _run_lean_command's
    keyword args (plus no_sync which is derived)."""
    option_names = _lean_command_option_names()
    sig_params = _lean_command_signature_params()
    extra = option_names - sig_params - {"no_sync"}
    assert not extra, (
        f"_LEAN_COMMAND_OPTION_NAMES contains names not in "
        f"_run_lean_command signature: {sorted(extra)}"
    )
