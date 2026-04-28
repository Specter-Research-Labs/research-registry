import os
import shlex
import subprocess
from pathlib import Path

from runtime_env import assert_wonton_python_runtime

DOSSIER_ROOT = Path(__file__).parent.resolve()
MATHLIB_REQUIRE_BLOCK = """[[require]]
name = "mathlib"
git = "https://github.com/leanprover-community/mathlib4"
rev = "{lean_version}"
"""


def _normalize_lean_version(raw: str) -> str:
    if raw.startswith("leanprover/lean4:"):
        return raw.split(":", 1)[1]
    return raw


def _quote(args: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in args)


def _run(args: list[str], *, cwd: Path) -> None:
    print(f"+ {_quote(args)}", flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def _configured_project_path() -> Path:
    raw = os.environ.get("LEAN_PROJECT_PATH")
    if raw:
        return Path(raw).expanduser().resolve()
    return DOSSIER_ROOT / "lean_project"


def _leantree_repl_dir() -> Path:
    from leantree.core.project import LeanProject

    return LeanProject._get_default_repl_path()


def _ensure_mathlib_requirement(lakefile_path: Path, lean_version: str) -> None:
    if not lakefile_path.exists():
        raise FileNotFoundError(f"lakefile.toml not found: {lakefile_path}")
    text = lakefile_path.read_text(encoding="utf-8")
    if 'name = "mathlib"' in text:
        return
    block = MATHLIB_REQUIRE_BLOCK.format(lean_version=lean_version)
    suffix = "" if text.endswith("\n") else "\n"
    lakefile_path.write_text(f"{text}{suffix}\n{block}", encoding="utf-8")


def _scaffold_project(project_path: Path, lean_version: str) -> None:
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "lean-toolchain").write_text(
        f"leanprover/lean4:{lean_version}\n",
        encoding="utf-8",
    )
    _run(["lake", "init", ".", "lib.toml"], cwd=project_path)
    _ensure_mathlib_requirement(project_path / "lakefile.toml", lean_version)


def main() -> None:
    assert_wonton_python_runtime(dossier_root=DOSSIER_ROOT, command_name="setup_lean.py")
    lean_version = _normalize_lean_version(
        os.environ.get("ELAN_DEFAULT_TOOLCHAIN", "leanprover/lean4:v4.25.0")
    )
    project_path = _configured_project_path()

    print(f"Using Lean version: {lean_version}", flush=True)
    print(f"Using Lean project path: {project_path}", flush=True)
    _run(["elan", "toolchain", "install", f"leanprover/lean4:{lean_version}"], cwd=DOSSIER_ROOT)
    print("Building Lean REPL...", flush=True)
    _run(["lake", "build"], cwd=_leantree_repl_dir())

    lakefile_path = project_path / "lakefile.toml"
    if lakefile_path.exists():
        print(f"Using existing Lean project at: {project_path}", flush=True)
    else:
        print(f"Creating Lean project at: {project_path}", flush=True)
        print(
            "This will initialize the project, fetch Mathlib caches, and build locally.",
            flush=True,
        )
        _scaffold_project(project_path, lean_version)

    _ensure_mathlib_requirement(project_path / "lakefile.toml", lean_version)

    print("Fetching Mathlib caches...", flush=True)
    _run(["lake", "exe", "cache", "get"], cwd=project_path)
    print("Building Lean project...", flush=True)
    _run(["lake", "build"], cwd=project_path)

    print(f"Done! Lean project is ready at: {project_path}")
    print()
    print("Next steps:")
    print(f"  export LEAN_PROJECT_PATH={project_path}")
    print("  uv run python wonton.py lean")


if __name__ == "__main__":
    main()
