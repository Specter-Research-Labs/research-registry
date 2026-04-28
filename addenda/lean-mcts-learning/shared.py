from __future__ import annotations

import gzip
import importlib
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, cast

REPO_MARKER = Path("dossiers") / "wonton-soup"
TRACE_RE = re.compile(r"^(?P<prefix>.+)_mcts_trace\.jsonl(?:\.gz)?$")


def resolve_repo_root(explicit: str | None = None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
    else:
        root = Path(__file__).resolve().parents[2]
    if not (root / REPO_MARKER).is_dir():
        raise FileNotFoundError(f"Could not find dossiers/wonton-soup under {root}")
    return root


def _wonton_root(repo_root: Path) -> Path:
    return repo_root / REPO_MARKER


def _add_sys_path(path: Path) -> None:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def _import_wonton_module(repo_root: Path, module_name: str) -> ModuleType:
    _add_sys_path(_wonton_root(repo_root))
    return importlib.import_module(module_name)


def import_wonton_symbol(repo_root: Path, module_name: str, symbol: str) -> Any:
    return getattr(_import_wonton_module(repo_root, module_name), symbol)


def load_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict JSON: {path}")
    return data


def write_json_object(path: Path, payload: dict[str, Any], *, newline: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, indent=2)
    if newline:
        text += "\n"
    tmp.write_text(text)
    tmp.replace(path)
    if not path.exists():
        raise RuntimeError(f"Missing after atomic write: {path}")


def iter_jsonl_objects(path: Path) -> Iterable[dict[str, Any]]:
    if path.suffix == ".gz":
        handle = gzip.open(path, "rt")
    else:
        handle = path.open("rt")
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                yield obj


def read_run_config(run_dir: Path) -> dict[str, object]:
    path = run_dir / "run_config.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing run_config.json: {path}")
    return load_json_object(path)


def read_run_id(run_dir: Path) -> str:
    run_id = read_run_config(run_dir).get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError(f"run_config.json missing run_id: {run_dir / 'run_config.json'}")
    return run_id


def resolve_single_provider_run(run_dir: Path, provider: str | None) -> Path:
    if provider:
        if run_dir.name == f"provider={provider}":
            return run_dir
        provider_dir = run_dir / f"provider={provider}"
        if not provider_dir.is_dir():
            raise FileNotFoundError(f"Provider subrun not found: {provider_dir}")
        return provider_dir

    provider_dirs = sorted(
        path for path in run_dir.iterdir() if path.is_dir() and path.name.startswith("provider=")
    )
    if provider_dirs:
        names = ", ".join(path.name.replace("provider=", "") for path in provider_dirs)
        raise ValueError(
            "run_dir appears to be a multi-provider root; pass --provider. "
            f"Available providers: {names}"
        )
    return run_dir


def corpus_candidates(run_config: dict[str, object]) -> list[str]:
    resolved = run_config.get("resolved")
    resolved_dict = cast(dict[str, Any], resolved) if isinstance(resolved, dict) else {}
    candidates: list[str] = []
    for value in (
        run_config.get("corpus_spec"),
        resolved_dict.get("corpus_spec"),
        run_config.get("corpus"),
        resolved_dict.get("corpus"),
    ):
        if isinstance(value, str) and value and value not in candidates:
            candidates.append(value)
    if not candidates:
        raise ValueError("run_config missing corpus/corpus_spec")
    return candidates


def find_family_prior_model(out_root: Path, run_id: str) -> Path:
    run_out = out_root / run_id
    direct = run_out / "family_prior.json"
    if direct.exists():
        return direct
    models = sorted(run_out.glob("provider=*/family_prior.json"))
    if not models:
        raise FileNotFoundError(f"No family_prior.json under {run_out}")
    if len(models) > 1:
        raise ValueError(
            f"Multiple provider models found under {run_out}; choose one manually: "
            + ", ".join(str(path) for path in models)
        )
    return models[0]


def iter_trace_paths(run_dir: Path) -> list[Path]:
    result: list[Path] = []
    for path in sorted(run_dir.glob("*/*_mcts_trace.jsonl*")):
        if not path.is_file() or path.name.startswith("._"):
            continue
        if not (path.name.endswith(".jsonl") or path.name.endswith(".jsonl.gz")):
            continue
        result.append(path)
    return result


def iter_variant_prefixes(theorem_dir: Path) -> list[str]:
    prefixes: set[str] = set()
    for trace in theorem_dir.iterdir():
        if not trace.is_file() or trace.name.startswith("._"):
            continue
        match = TRACE_RE.match(trace.name)
        if match:
            prefixes.add(match.group("prefix"))
    return sorted(prefixes)


def trace_path_for_prefix(theorem_dir: Path, prefix: str) -> Path:
    plain = theorem_dir / f"{prefix}_mcts_trace.jsonl"
    if plain.exists():
        return plain
    gz = theorem_dir / f"{prefix}_mcts_trace.jsonl.gz"
    if gz.exists():
        return gz
    raise FileNotFoundError(f"Missing trace file for prefix={prefix}: {theorem_dir}")
