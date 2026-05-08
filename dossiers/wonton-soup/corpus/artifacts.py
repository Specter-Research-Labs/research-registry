from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from runtime_paths import resolve_corpora_root as _resolve_runtime_corpora_root

DOSSIER_NAME = "wonton-soup"
DOSSIER_ROOT = Path(__file__).resolve().parents[1]


class CorpusArtifactError(RuntimeError):
    pass


def resolve_corpora_root() -> Path:
    """Resolve the root directory for corpus artifacts.

    - If SPCTR_LOCAL_ARTIFACT_ROOT is set: <root>/wonton-soup/artifacts/corpora/
    - If SPECTER_ARTIFACT_ROOT is set: local staging under SPECTER_RUNTIME_ROOT/.../corpora/
      when SPECTER_RUNTIME_ROOT is configured, else repo-local tmp/runtime-artifacts/.../corpora/
    - Else: canonical local dossiers/wonton-soup/artifacts/corpora/ (local-only; gitignored)
    """
    return _resolve_runtime_corpora_root()


def resolve_corpus_artifact_root() -> Path:
    """Compatibility alias for `resolve_corpora_root`."""
    return resolve_corpora_root()


_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _validate_id(label: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise CorpusArtifactError(f"{label} must be a non-empty string")
    if "/" in value or "\\" in value:
        raise CorpusArtifactError(f"{label} must not contain path separators: {value!r}")
    if value in {".", ".."}:
        raise CorpusArtifactError(f"{label} is not a valid id: {value!r}")
    if not _SAFE_ID_RE.match(value):
        raise CorpusArtifactError(
            f"{label} must match {_SAFE_ID_RE.pattern} (got {value!r})"
        )


def timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    # Canonical encoding for stable build_id hashing.
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8", errors="strict")


def compute_build_id(fingerprint: Mapping[str, Any]) -> str:
    return _sha256_bytes(_canonical_json_bytes(fingerprint))


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as f:
        f.write(text)
        tmp_path = Path(f.name)
    tmp_path.replace(path)
    if not path.exists():
        raise CorpusArtifactError(f"Missing after atomic write: {path}")


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception as exc:  # pragma: no cover
                raise CorpusArtifactError(f"Invalid JSONL at {path}:{line_no}") from exc
            if not isinstance(obj, dict):
                raise CorpusArtifactError(f"Expected JSON object at {path}:{line_no}")
            yield obj


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    """Write JSONL deterministically (canonical JSON per line, stable newlines)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            line = json.dumps(
                row,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            f.write(line)
            f.write("\n")
    tmp_path.replace(path)
    if not path.exists():  # pragma: no cover
        raise CorpusArtifactError(f"{path.name} missing after write in {path.parent}")


def _default_split_scheme() -> dict[str, Any]:
    return {
        "kind": "sha256_mod_100",
        "buckets": 100,
        "splits": {
            "train": [0, 79],
            "valid": [80, 89],
            "test": [90, 99],
        },
    }


@dataclass(frozen=True)
class CorpusBuildRef:
    backend: str
    corpus_id: str
    build_id: str
    build_dir: Path


@dataclass(frozen=True)
class CorpusRef:
    backend: str
    corpus_id: str
    build_id: str | None = None
    derived: str | None = None

    def to_string(self) -> str:
        suffix = ""
        if self.build_id is not None:
            suffix += f"@{self.build_id}"
        if self.derived is not None:
            suffix += f"#{self.derived}"
        return f"{self.backend}:{self.corpus_id}{suffix}"


def parse_corpus_ref(raw: str) -> CorpusRef:
    """Parse a corpus ref string: <backend>:<corpus_id>[@<build_id>][#<derived_path>]."""
    if not isinstance(raw, str) or not raw.strip():
        raise CorpusArtifactError("corpus_ref must be a non-empty string")
    text = raw.strip()
    if ":" not in text:
        raise CorpusArtifactError(
            "Invalid corpus ref; expected '<backend>:<corpus_id>[@<build_id>][#<derived>]': "
            f"{raw!r}"
        )
    backend, rest = text.split(":", 1)
    derived = None
    if "#" in rest:
        rest, derived = rest.split("#", 1)
        derived = derived.strip()
        if not derived:
            raise CorpusArtifactError(f"Empty derived selector in corpus ref: {raw!r}")
        parts = [p for p in derived.split("/") if p]
        if any(p in {".", ".."} for p in parts) or any("\\" in p for p in parts):
            raise CorpusArtifactError(f"Invalid derived selector in corpus ref: {raw!r}")
        derived = "/".join(parts)

    build_id = None
    corpus_id = rest
    if "@" in rest:
        corpus_id, build_id = rest.split("@", 1)
        build_id = build_id.strip()
        if not build_id:
            raise CorpusArtifactError(f"Empty build_id in corpus ref: {raw!r}")

    corpus_id = corpus_id.strip()
    backend = backend.strip()
    _validate_id("backend", backend)
    _validate_id("corpus_id", corpus_id)
    if build_id is not None:
        _validate_id("build_id", build_id)
    return CorpusRef(
        backend=backend,
        corpus_id=corpus_id,
        build_id=build_id,
        derived=derived,
    )


def resolve_build_dir(
    backend: str,
    corpus_id: str,
    *,
    build_id: str | None = None,
) -> CorpusBuildRef:
    _validate_id("backend", backend)
    _validate_id("corpus_id", corpus_id)
    root = resolve_corpora_root()
    corpus_root = root / backend / corpus_id
    if build_id is None:
        current = corpus_root / "CURRENT"
        if not current.exists():
            raise CorpusArtifactError(
                f"Missing CURRENT pointer for {backend}/{corpus_id}. "
                f"Expected: {current}"
            )
        build_id = current.read_text().strip()
        if not build_id:
            raise CorpusArtifactError(f"Empty CURRENT pointer: {current}")
    _validate_id("build_id", build_id)
    build_dir = corpus_root / build_id
    if not build_dir.exists():
        raise CorpusArtifactError(f"Corpus build not found: {build_dir}")
    return CorpusBuildRef(
        backend=backend,
        corpus_id=corpus_id,
        build_id=build_id,
        build_dir=build_dir,
    )

def resolve_corpus_build_dir(ref: CorpusRef) -> Path:
    """Resolve the build directory for a corpus ref (ignores `ref.derived`)."""
    build_ref = resolve_build_dir(ref.backend, ref.corpus_id, build_id=ref.build_id)
    return build_ref.build_dir


def write_current_id(parent_dir: Path, build_id: str) -> None:
    parent_dir.mkdir(parents=True, exist_ok=True)
    _validate_id("build_id", build_id)
    _atomic_write_text(parent_dir / "CURRENT", build_id + "\n")


def write_json_atomic(path: Path, payload: Any) -> None:
    _atomic_write_json(path, payload)


def make_manifest(
    *,
    backend: str,
    corpus_id: str,
    build_id: str,
    provenance: list[dict[str, Any]],
    build_config: dict[str, Any],
    items_file: str,
    items_sha256: str,
    item_id_scheme: str,
    items_total: int,
) -> dict[str, Any]:
    _validate_id("backend", backend)
    _validate_id("corpus_id", corpus_id)
    _validate_id("build_id", build_id)
    if not isinstance(items_file, str) or not items_file:
        raise CorpusArtifactError("items_file must be a non-empty string")
    if not isinstance(items_sha256, str) or not items_sha256:
        raise CorpusArtifactError("items_sha256 must be a non-empty string")
    if not isinstance(item_id_scheme, str) or not item_id_scheme.strip():
        raise CorpusArtifactError("item_id_scheme must be a non-empty string")
    if not isinstance(items_total, int) or items_total < 0:
        raise CorpusArtifactError("items_total must be an int >= 0")

    return {
        "format_version": 1,
        "backend": backend,
        "corpus_id": corpus_id,
        "build_id": build_id,
        "created_at": timestamp(),
        "provenance": provenance,
        "build_config": build_config,
        "counts": {"items_total": items_total},
        "items_file": items_file,
        "items_sha256": items_sha256,
        "item_id_scheme": item_id_scheme,
        "split_scheme": _default_split_scheme(),
    }


def load_manifest(build_dir: Path) -> dict[str, Any]:
    path = build_dir / "manifest.json"
    if not path.exists():
        raise CorpusArtifactError(f"manifest.json not found: {path}")
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise CorpusArtifactError(f"manifest.json must be a JSON object: {path}")
    return data


@dataclass(frozen=True)
class CorpusListEntry:
    backend: str
    corpus_id: str
    current_build_id: str | None
    build_ids: list[str]
    items_total: int | None
    derived_current: dict[str, str | None]
    problems: list[str]


def _list_id_dirs(parent: Path) -> list[str]:
    if not parent.exists():
        return []
    names: list[str] = []
    for child in parent.iterdir():
        if child.is_dir() and _SAFE_ID_RE.match(child.name):
            names.append(child.name)
    names.sort()
    return names


def list_corpora(root: Path | None = None) -> list[CorpusListEntry]:
    """List available corpus artifact builds under the corpora root.

    - Enumerates <root>/<backend>/<corpus_id> directories.
    - Resolves CURRENT (if present) and reads items_total from that build's manifest.
    - Surfaces derived slices for the CURRENT build (e.g. derived/valid, derived/feasible).
    """
    corpora_root = root or resolve_corpora_root()
    if not corpora_root.exists():
        return []

    entries: list[CorpusListEntry] = []
    for backend in _list_id_dirs(corpora_root):
        backend_dir = corpora_root / backend
        for corpus_id in _list_id_dirs(backend_dir):
            corpus_dir = backend_dir / corpus_id
            build_ids = _list_id_dirs(corpus_dir)
            problems: list[str] = []

            current_build_id: str | None = None
            current_path = corpus_dir / "CURRENT"
            if current_path.exists():
                text = current_path.read_text(encoding="utf-8", errors="strict").strip()
                if not text:
                    problems.append("CURRENT is empty")
                else:
                    current_build_id = text
                    if current_build_id not in build_ids:
                        problems.append(f"CURRENT points to missing build: {current_build_id}")

            items_total: int | None = None
            derived_current: dict[str, str | None] = {}
            if current_build_id is not None and (corpus_dir / current_build_id).exists():
                build_dir = corpus_dir / current_build_id
                try:
                    manifest = load_manifest(build_dir)
                    counts = manifest.get("counts")
                    if isinstance(counts, dict):
                        n = counts.get("items_total")
                        if isinstance(n, int):
                            items_total = n
                except Exception as exc:
                    problems.append(f"manifest read failed: {str(exc).splitlines()[0]}")

                derived_root = build_dir / "derived"
                if derived_root.exists():
                    for child in sorted(derived_root.iterdir(), key=lambda p: p.name):
                        if not child.is_dir():
                            continue
                        name = child.name
                        if name == "tmp":
                            continue
                        current = child / "CURRENT"
                        derived_build_id: str | None = None
                        if current.exists():
                            text = current.read_text(
                                encoding="utf-8", errors="strict"
                            ).strip()
                            if not text:
                                problems.append(f"derived/{name}/CURRENT is empty")
                            else:
                                derived_build_id = text
                        derived_current[name] = derived_build_id

            entries.append(
                CorpusListEntry(
                    backend=backend,
                    corpus_id=corpus_id,
                    current_build_id=current_build_id,
                    build_ids=build_ids,
                    items_total=items_total,
                    derived_current=derived_current,
                    problems=problems,
                )
            )

    entries.sort(key=lambda e: (e.backend, e.corpus_id))
    return entries
