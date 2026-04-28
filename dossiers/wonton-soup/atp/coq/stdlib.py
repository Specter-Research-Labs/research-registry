from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from atp.coq.source import extract_theorems_from_source

DEFAULT_STDLIB_MODULES = [
    "Coq.Init.Logic",
    "Coq.Init.Datatypes",
    "Coq.Bool.Bool",
    "Coq.Lists.List",
    "Coq.Arith.PeanoNat",
    "Coq.Arith.Arith",
    "Coq.Relations.Relation_Definitions",
    "Coq.Sets.Ensembles",
]


def find_coq_stdlib_root(coqc_binary: str) -> Path:
    try:
        result = subprocess.run(
            [coqc_binary, "-where"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"coqc not found: {coqc_binary}") from exc
    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"coqc -where failed: {msg or 'unknown error'}")
    root = result.stdout.strip()
    if not root:
        raise RuntimeError("coqc -where returned empty output")
    return Path(root)


def _stdlib_theories_root(stdlib_root: Path) -> Path:
    theories = stdlib_root / "theories"
    if theories.exists():
        return theories
    if (stdlib_root / "Init").exists():
        return stdlib_root
    raise FileNotFoundError(f"Coq theories directory not found under {stdlib_root}")


def module_to_path(stdlib_root: Path, module: str) -> Path:
    module = module.strip()
    if not module:
        raise ValueError("module name must be non-empty")
    parts = module.split(".")
    if parts[0] == "Coq":
        parts = parts[1:]
    if not parts:
        raise ValueError(f"module name invalid: {module}")
    root = _stdlib_theories_root(stdlib_root)
    path = root.joinpath(*parts).with_suffix(".v")
    if not path.exists():
        raise FileNotFoundError(f"Coq module not found: {module} ({path})")
    return path

def extract_theorems_from_file(path: Path) -> list[str]:
    text = path.read_text()
    return extract_theorems_from_source(text)


def collect_stdlib_theorems(
    modules: Iterable[str],
    stdlib_root: Path,
    limit_per_module: int | None = None,
    limit_total: int | None = None,
) -> list[str]:
    selected: list[str] = []
    for module in modules:
        path = module_to_path(stdlib_root, module)
        names = extract_theorems_from_file(path)
        if limit_per_module is not None and limit_per_module > 0:
            names = names[:limit_per_module]
        selected.extend(names)
        if limit_total is not None and limit_total > 0 and len(selected) >= limit_total:
            return selected[:limit_total]
    return selected


def build_import_sentences(modules: Iterable[str]) -> list[str]:
    imports = []
    for module in modules:
        module = module.strip()
        if not module:
            raise ValueError("module name must be non-empty")
        imports.append(f"Require Import {module}.")
    return imports
