"""What produced a run: source, Lean toolchain, Python lock and tactic limits.

The source is recorded as a commit on the trunk plus a patch of everything in
the dossier that differs from it, so a run from an unpushed or dirty checkout
can still be rebuilt from the public history and `source.patch`.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from importlib.metadata import version
from pathlib import Path
from typing import Any

from prover.adapters.lean import (
    DECLARATION_MAX_HEARTBEATS,
    MAX_REC_DEPTH,
    TACTIC_HEARTBEATS,
    TACTIC_WALL_GUARD_MS,
)

DOSSIER_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATCH_NAME = "source.patch"


def _run(args: list[str], cwd: Path, ok_codes: tuple[int, ...] = (0,)) -> bytes:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, check=False)
    if proc.returncode not in ok_codes:
        raise RuntimeError(
            f"{' '.join(args)} failed in {cwd} ({proc.returncode}): {proc.stderr.decode().strip()}"
        )
    return proc.stdout


def _repo_root(start: Path) -> tuple[str, Path]:
    for candidate in (start, *start.parents):
        if (candidate / ".jj").is_dir():
            return "jj", candidate
        if (candidate / ".git").exists():
            return "git", candidate
    raise RuntimeError(f"{start} is not inside a jj or git checkout")


def _jj_source(root: Path, dossier: str) -> tuple[str, bytes]:
    base = (
        _run(["jj", "log", "-r", "heads(::@ & ::trunk())", "--no-graph", "-T", "commit_id"], root)
        .decode()
        .strip()
    )
    patch = _run(["jj", "diff", "--git", "--from", base, "--to", "@", "--", dossier], root)
    return base, patch


def _git_source(root: Path, dossier: str) -> tuple[str, bytes]:
    base = _run(["git", "merge-base", "HEAD", "origin/main"], root).decode().strip()
    patch = _run(["git", "diff", "--binary", base, "--", dossier], root)
    untracked = _run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z", "--", dossier], root
    ).split(b"\0")
    for path in filter(None, untracked):
        patch += _run(
            ["git", "diff", "--binary", "--no-index", "/dev/null", path.decode()],
            root,
            ok_codes=(1,),
        )
    return base, patch


def source_provenance() -> tuple[dict[str, Any], bytes]:
    """The trunk commit the dossier derives from and the dossier's diff against it."""
    vcs, root = _repo_root(DOSSIER_ROOT)
    dossier = str(DOSSIER_ROOT.relative_to(root))
    base, patch = _jj_source(root, dossier) if vcs == "jj" else _git_source(root, dossier)
    info = {
        "vcs": vcs,
        "base_commit": base,
        "dirty": bool(patch),
        "patch": SOURCE_PATCH_NAME if patch else None,
        "patch_sha256": hashlib.sha256(patch).hexdigest() if patch else None,
    }
    return info, patch


def lean_provenance(project_path: Path) -> dict[str, Any]:
    """Toolchain and Mathlib revision of the Lean project the REPL runs in.

    The project is either Mathlib itself or a package that requires it, and the
    Mathlib revision is read from wherever that layout pins it.
    """
    toolchain = (project_path / "lean-toolchain").read_text(encoding="utf-8").strip()
    manifest = json.loads((project_path / "lake-manifest.json").read_text(encoding="utf-8"))
    if manifest["name"] == "mathlib":
        rev = _run(["git", "rev-parse", "HEAD"], project_path).decode().strip()
        dirty = bool(_run(["git", "status", "--porcelain", "--untracked-files=no"], project_path))
        mathlib = {"source": "project", "rev": rev, "dirty": dirty}
    else:
        packages = [p for p in manifest["packages"] if p["name"] == "mathlib"]
        if len(packages) != 1:
            raise ValueError(f"{project_path}/lake-manifest.json does not pin mathlib")
        mathlib = {"source": "lake-manifest", "rev": packages[0]["rev"], "dirty": False}
    return {"toolchain": toolchain, "mathlib": mathlib}


def python_provenance() -> dict[str, Any]:
    lock = (DOSSIER_ROOT / "uv.lock").read_bytes()
    return {"leantree": version("leantree"), "uv_lock_sha256": hashlib.sha256(lock).hexdigest()}


def tactic_limit() -> dict[str, Any]:
    return {
        "kind": "heartbeats",
        "tactic_heartbeats": TACTIC_HEARTBEATS,
        "wall_guard_ms": TACTIC_WALL_GUARD_MS,
        "declaration_max_heartbeats": DECLARATION_MAX_HEARTBEATS,
        "max_rec_depth": MAX_REC_DEPTH,
    }


def record_run_provenance(log_dir: Path, project_path: Path, *, resume: bool) -> dict[str, Any]:
    """Collect provenance and write `source.patch` next to the run config.

    A resumed run must match the provenance it started with, because results
    from two different sources in one run dir cannot be told apart later.
    """
    source, patch = source_provenance()
    provenance = {
        "source": source,
        "lean": lean_provenance(project_path),
        "python": python_provenance(),
        "tactic_limit": tactic_limit(),
    }
    if resume:
        started = json.loads((log_dir / "run_config.json").read_text(encoding="utf-8"))
        if started["provenance"] != provenance:
            raise RuntimeError(
                f"cannot resume {log_dir}: provenance changed since the run started\n"
                f"started: {json.dumps(started['provenance'], sort_keys=True)}\n"
                f"now:     {json.dumps(provenance, sort_keys=True)}"
            )
    if patch:
        (log_dir / SOURCE_PATCH_NAME).write_bytes(patch)
    return provenance
