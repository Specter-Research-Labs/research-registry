import os

import pytest

LEAN_PROJECT = os.environ.get("LEAN_PROJECT_PATH")
needs_lean = pytest.mark.skipif(
    LEAN_PROJECT is None, reason="set LEAN_PROJECT_PATH to a built Lean project"
)
