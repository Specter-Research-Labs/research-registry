import os

import pytest


def lean_project() -> str:
    path = os.environ.get("LEAN_PROJECT_PATH")
    if path is None:
        pytest.fail("LEAN_PROJECT_PATH is unset; export it to a built Lean project (setup_lean.py)")
    return path
