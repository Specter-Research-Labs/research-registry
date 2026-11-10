from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leantree.repl_adapter.error_metadata import build_error_record

from corpus.artifacts import (
    compute_build_id,
    iter_jsonl,
    make_manifest,
    parse_corpus_ref,
    resolve_corpus_build_dir,
    sha256_file,
    write_current_id,
    write_json_atomic,
    write_jsonl,
)

DOSSIER_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ValidationSummary:
    backend: str
    corpus_ref: str
    build_dir: Path
    validated_count: int
    valid_count: int
    invalid_count: int
    valid_rate: float
    validation_path: Path
    derived_valid_dir: Path | None


def _normalize_validation_error(error: Any) -> str | None:
    if error is None:
        return None
    if isinstance(error, Exception):
        text = str(error).strip()
        return text or None
    if isinstance(error, str):
        text = error.strip()
        return text or None
    return json.dumps(error, ensure_ascii=True, sort_keys=True)


def _summarize_validation_error(error: Any) -> tuple[str, str]:
    text = _normalize_validation_error(error)
    if text is None:
        raise ValueError("validation error is missing")
    record = build_error_record(error if isinstance(error, Exception) else text)
    error_kind = record.get("error_kind")
    error_summary = record.get("error_summary")
    return (
        error_kind if isinstance(error_kind, str) and error_kind else "exception",
        error_summary if isinstance(error_summary, str) and error_summary else text,
    )


def _valid_validation_row(item_id: str) -> dict[str, Any]:
    return {"item_id": item_id, "valid": True}


def _invalid_validation_row(item_id: str, error: Any) -> dict[str, Any]:
    error_text = _normalize_validation_error(error)
    if error_text is None:
        raise ValueError(f"Missing validation error text for {item_id}")
    error_kind, error_summary = _summarize_validation_error(error)
    return {
        "item_id": item_id,
        "valid": False,
        "error": error_text,
        "error_kind": error_kind,
        "error_summary": error_summary,
    }


def _load_manifest(build_dir: Path) -> dict[str, Any]:
    path = build_dir / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"manifest.json not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid manifest.json (not an object): {path}")
    return data


def _items_path(build_dir: Path, manifest: dict[str, Any]) -> Path:
    items_file = manifest.get("items_file") or "items.jsonl"
    if not isinstance(items_file, str) or not items_file:
        raise ValueError("manifest.items_file missing/invalid")
    path = build_dir / items_file
    if not path.exists():
        raise FileNotFoundError(f"items file not found: {path}")
    return path


def _write_validation_jsonl(build_dir: Path, rows: list[dict[str, Any]]) -> Path:
    out = build_dir / "validation.jsonl"
    write_jsonl(out, rows)
    return out


def _derive_valid_slice(
    *,
    build_dir: Path,
    backend: str,
    corpus_id: str,
    parent_build_id: str,
    parent_manifest: dict[str, Any],
    parent_items_path: Path,
    validation_path: Path,
    valid_ids: set[str],
    min_valid_rate: float,
) -> Path:
    derived_root = build_dir / "derived" / "valid"
    derived_root.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, Any]] = []
    for row in iter_jsonl(parent_items_path):
        item_id = row.get("item_id")
        if isinstance(item_id, str) and item_id in valid_ids:
            items.append(row)
    # parent_items_path is sorted; filtering preserves order.
    tmp_dir = derived_root / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_items = tmp_dir / f"items.{os.getpid()}.jsonl.tmp"
    write_jsonl(tmp_items, items)
    derived_items_sha = sha256_file(tmp_items)
    validation_sha = sha256_file(validation_path)

    fingerprint = {
        "kind": "derived_valid",
        "parent_build_id": parent_build_id,
        "parent_items_sha256": str(parent_manifest.get("items_sha256") or ""),
        "validation_sha256": validation_sha,
        "derived_items_sha256": derived_items_sha,
        "derived_items_total": len(items),
    }
    derived_build_id = compute_build_id(fingerprint)
    derived_dir = derived_root / derived_build_id
    if derived_dir.exists():
        write_current_id(derived_root, derived_build_id)
        copied = derived_dir / "validation.jsonl"
        if not copied.exists():
            shutil.copy2(validation_path, copied)
        if tmp_items.exists():
            tmp_items.unlink()
        return derived_dir

    derived_dir.mkdir(parents=True, exist_ok=False)
    tmp_items.replace(derived_dir / "items.jsonl")
    shutil.copy2(validation_path, derived_dir / "validation.jsonl")

    provenance = list(parent_manifest.get("provenance") or [])
    provenance.append(
        {
            "kind": "derived",
            "derived_kind": "valid",
            "parent_build_id": parent_build_id,
            "validation_sha256": validation_sha,
            "min_valid_rate": min_valid_rate,
        }
    )
    build_config = dict(parent_manifest.get("build_config") or {})
    build_config.update(
        {
            "derived_kind": "valid",
            "parent_build_id": parent_build_id,
            "validation_sha256": validation_sha,
            "min_valid_rate": min_valid_rate,
        }
    )
    manifest = make_manifest(
        backend=backend,
        corpus_id=corpus_id,
        build_id=derived_build_id,
        provenance=provenance,
        build_config=build_config,
        items_file="items.jsonl",
        items_sha256=derived_items_sha,
        item_id_scheme=str(parent_manifest.get("item_id_scheme") or ""),
        items_total=len(items),
    )
    manifest["parent"] = {
        "build_id": parent_build_id,
        "items_sha256": str(parent_manifest.get("items_sha256") or ""),
    }
    write_json_atomic(derived_dir / "manifest.json", manifest)
    write_current_id(derived_root, derived_build_id)
    if tmp_dir.exists():
        try:
            tmp_dir.rmdir()
        except OSError:
            pass
    return derived_dir


async def _lean_typecheck(
    *,
    lean_project: Path,
    items_path: Path,
) -> list[dict[str, Any]]:
    from leantree.core.project import LeanProject

    project = LeanProject(str(lean_project))
    out: list[dict[str, Any]] = []
    async with project.environment() as env:
        await env.send_command_async("import Mathlib")
        # Many Lean statements (especially from mathlib scans) contain terms whose types require
        # decidable equality. Make classical decidable equality available during elaboration so
        # typechecking is about statement well-formedness rather than missing instances.
        await env.send_command_async("section")
        await env.send_command_async("open scoped Classical")
        await env.send_command_async("attribute [instance] Classical.decEq")
        await env.send_command_async(
            "open BigOperators Real Nat Topology Rat Complex Set Int Polynomial Finset "
            "Function Filter"
        )
        await env.send_command_async("set_option maxRecDepth 2000")
        await env.send_command_async("set_option maxHeartbeats 200000")
        try:
            for idx, row in enumerate(iter_jsonl(items_path), 1):
                item_id = row.get("item_id")
                payload = row.get("payload")
                stmt = payload.get("statement") if isinstance(payload, dict) else None
                if not isinstance(item_id, str) or not item_id:
                    raise ValueError(f"Invalid item_id in {items_path}")
                if not isinstance(stmt, str) or "{name}" not in stmt:
                    raise ValueError(f"Invalid payload.statement for {item_id} in {items_path}")

                name = f"validate_{idx}"
                rendered = stmt.replace("{name}", name)

                try:
                    await env.send_command_async(rendered)
                    out.append(_valid_validation_row(item_id))
                except Exception as exc:
                    out.append(_invalid_validation_row(item_id, exc))
        finally:
            await env.send_command_async("end")
    return out


def validate_and_derive_valid(
    *,
    corpus_ref: str,
    lean_project: Path | None = None,
    min_valid_rate: float = 0.9,
    allow_low_validity: bool = False,
) -> ValidationSummary:
    ref = parse_corpus_ref(corpus_ref)
    if ref.derived is not None:
        raise ValueError(
            "validate expects a base corpus ref (no #derived). "
            f"Got: {corpus_ref!r}"
        )
    build_dir = resolve_corpus_build_dir(ref)
    manifest = _load_manifest(build_dir)
    backend = str(manifest.get("backend") or ref.backend)
    corpus_id = str(manifest.get("corpus_id") or ref.corpus_id)
    parent_build_id = str(manifest.get("build_id") or "")
    if not parent_build_id:
        raise ValueError(f"manifest.json missing build_id: {build_dir / 'manifest.json'}")

    items_path = _items_path(build_dir, manifest)

    if backend == "lean":
        project = lean_project or (DOSSIER_ROOT / "lean_project")
        rows = asyncio.run(_lean_typecheck(lean_project=project, items_path=items_path))
    else:
        raise ValueError(f"Unknown backend for validation: {backend}")

    # Preserve items.jsonl order so downstream derivations stay deterministic.
    validation_path = _write_validation_jsonl(build_dir, rows)
    valid_ids = {
        r["item_id"]
        for r in rows
        if r.get("valid") is True and isinstance(r.get("item_id"), str)
    }
    valid_count = len(valid_ids)
    validated_count = len(rows)
    invalid_count = validated_count - valid_count
    valid_rate = (valid_count / validated_count) if validated_count else 0.0

    if validated_count == 0:
        raise RuntimeError(f"No items validated for {corpus_ref}")
    if (valid_rate < min_valid_rate) and not allow_low_validity:
        raise RuntimeError(
            f"Validity rate too low for {corpus_ref}: {valid_rate:.1%} "
            f"({valid_count}/{validated_count}); set --allow-low-validity to override."
        )

    derived_dir = _derive_valid_slice(
        build_dir=build_dir,
        backend=backend,
        corpus_id=corpus_id,
        parent_build_id=parent_build_id,
        parent_manifest=manifest,
        parent_items_path=items_path,
        validation_path=validation_path,
        valid_ids=valid_ids,
        min_valid_rate=min_valid_rate,
    )
    return ValidationSummary(
        backend=backend,
        corpus_ref=corpus_ref,
        build_dir=build_dir,
        validated_count=validated_count,
        valid_count=valid_count,
        invalid_count=invalid_count,
        valid_rate=valid_rate,
        validation_path=validation_path,
        derived_valid_dir=derived_dir,
    )

# ---------------------------------------------------------------------------
# Tree extractability validation
# ---------------------------------------------------------------------------

_DECL_NAME_RE = re.compile(
    r"(?:^|(?<=\]\s)|(?<=\]\n))(?:(?:protected|private|noncomputable|unsafe)\s+)*"
    r"(?:theorem|lemma|def|nonrec\s+def)\s+"
    r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)",
    re.MULTILINE,
)

