from __future__ import annotations

import errno
import sys
from pathlib import Path

import _pytest.pathlib

# Pytest may be invoked with a cwd other than the dossier root; prepend the root so
# local imports (e.g. `corpus`, `prover`) resolve consistently.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Optional repo-local symlinks such as `logs-remote` can point at an offline remote volume.
# Pytest probes each root direntry with `DirEntry.is_file()` before ignore hooks run, and on
# macOS that probe can raise ENOLCK for the symlink target. Treat that like a missing entry so
# explicitly requested test paths still collect.
if errno.ENOLCK not in _pytest.pathlib._IGNORED_ERRORS:
    _pytest.pathlib._IGNORED_ERRORS = (*_pytest.pathlib._IGNORED_ERRORS, errno.ENOLCK)
