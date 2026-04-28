from __future__ import annotations

import contextlib
import io
import os
import sys
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

_VERBOSE_TTLANG_ENV_VARS = (
    "LENIA_TT_SHOW_TTLANG_COMPILE",
    "TTLANG_AUTO_PROFILE",
    "TTLANG_EMIT_RUNNER",
    "TTLANG_FINAL_MLIR",
    "TTLANG_INITIAL_MLIR",
    "TTLANG_PERF_DUMP",
    "TTLANG_PERF_SERV",
    "TTLANG_SIGNPOST_PROFILE",
    "TTLANG_VERBOSE_PASSES",
)


def run_ttlang_kernel(kernel: Callable[..., T], *args, **kwargs) -> T:
    """Run a TT-Lang kernel without dumping generated C++ during normal runs."""
    if _show_ttlang_output():
        return kernel(*args, **kwargs)

    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            return kernel(*args, **kwargs)
    except Exception:
        _replay_captured_stdout(captured.getvalue())
        raise


def _show_ttlang_output() -> bool:
    return any(_truthy_env(name) for name in _VERBOSE_TTLANG_ENV_VARS)


def _truthy_env(name: str) -> bool:
    value = os.environ.get(name)
    return value is not None and value.strip().lower() not in {"", "0", "false", "no", "off"}


def _replay_captured_stdout(text: str) -> None:
    if not text:
        return
    print("[ttlang stdout captured before failure]", file=sys.stderr)
    print(text, file=sys.stderr, end="" if text.endswith("\n") else "\n")
