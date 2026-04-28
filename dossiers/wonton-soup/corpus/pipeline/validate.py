from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from collections import defaultdict
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
_BACKFILL_SUMMARY_CODES = {
    "missing_or_empty": "missing or empty file",
    "missing": "missing file",
    "not_unsat": "problem is not marked unsat",
    "no_constr": "SerAPI returned no constr",
}


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


@dataclass(frozen=True)
class TreeValidationSummary:
    corpus_ref: str
    build_dir: Path
    validated_count: int
    extractable_count: int
    non_extractable_count: int
    extractable_rate: float
    validation_path: Path
    derived_dir: Path | None


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
    if text in _BACKFILL_SUMMARY_CODES:
        return text, _BACKFILL_SUMMARY_CODES[text]
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
    elif backend == "tptp":
        # Minimal v1: ensure referenced files exist and are non-empty.
        rows = []
        tptp_root = Path(str(manifest.get("build_config", {}).get("tptp_root") or ""))
        if not tptp_root.exists():
            raise FileNotFoundError(
                "TPTP root not found (manifest build_config.tptp_root): "
                f"{tptp_root}"
            )
        for row in iter_jsonl(items_path):
            item_id = row.get("item_id")
            payload = row.get("payload")
            rel = payload.get("relpath") if isinstance(payload, dict) else None
            if not isinstance(item_id, str) or not isinstance(rel, str):
                raise ValueError(f"Invalid TPTP item row in {items_path}")
            path = tptp_root / rel
            ok = path.exists() and path.is_file() and path.stat().st_size > 0
            if ok:
                rows.append(_valid_validation_row(item_id))
            else:
                rows.append(_invalid_validation_row(item_id, "missing_or_empty"))
    elif backend == "smtlib":
        rows = []
        problems_root = build_dir / "problems"
        if not problems_root.exists():
            raise FileNotFoundError(f"SMT-LIB problems dir not found: {problems_root}")
        for row in iter_jsonl(items_path):
            item_id = row.get("item_id")
            payload = row.get("payload")
            rel = payload.get("relpath") if isinstance(payload, dict) else None
            if not isinstance(item_id, str) or not isinstance(rel, str):
                raise ValueError(f"Invalid SMT-LIB item row in {items_path}")
            path = problems_root / rel
            if not path.exists():
                rows.append(_invalid_validation_row(item_id, "missing"))
                continue
            raw = path.read_bytes()
            ok = b":status" in raw.lower() and b"unsat" in raw.lower()
            if ok:
                rows.append(_valid_validation_row(item_id))
            else:
                rows.append(_invalid_validation_row(item_id, "not_unsat"))
    elif backend == "coq":
        # Minimal v1: SerAPI can query the qualname after importing its module.
        from atp.coq.runner import CoqConfig
        from atp.coq.serapi import SerapiSession, extract_constr_sexpr

        config = CoqConfig()
        session = SerapiSession(config.serapi)
        try:
            rows = []
            for row in iter_jsonl(items_path):
                item_id = row.get("item_id")
                payload = row.get("payload")
                module = payload.get("module") if isinstance(payload, dict) else None
                qual = payload.get("qualname") if isinstance(payload, dict) else None
                if (
                    not isinstance(item_id, str)
                    or not isinstance(module, str)
                    or not isinstance(qual, str)
                ):
                    raise ValueError(f"Invalid Coq item row in {items_path}")
                try:
                    session.send(f"Require Import {module}.")
                    responses = session.send(f'(Query () (Definition "{qual}"))')
                    constr = extract_constr_sexpr(responses)
                    if constr is None:
                        rows.append(_invalid_validation_row(item_id, "no_constr"))
                    else:
                        rows.append(_valid_validation_row(item_id))
                except Exception as exc:
                    rows.append(_invalid_validation_row(item_id, exc))
        finally:
            session.close()
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


def _extract_decl_name(source: str) -> str | None:
    """Extract the declaration name from a Lean source span."""
    m = _DECL_NAME_RE.search(source)
    return m.group(1) if m else None


def _lean_tree_extract_check(
    *,
    lean_project: Path,
    items_path: Path,
    mathlib_root: Path,
) -> list[dict[str, Any]]:
    """Check tree extractability for each item by loading source files via leantree."""
    from leantree.core.lean_file import LeanTheorem, StoredError
    from leantree.core.project import LeanProject

    items_by_module: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_items: list[dict[str, Any]] = []
    for row in iter_jsonl(items_path):
        item_id = row.get("item_id")
        payload = row.get("payload")
        if not isinstance(item_id, str) or not isinstance(payload, dict):
            raise ValueError(f"Invalid item row in {items_path}")
        source = payload.get("source")
        if not isinstance(source, dict):
            raise ValueError(f"Missing payload.source for {item_id}")
        module = source.get("module")
        if not isinstance(module, str):
            raise ValueError(f"Missing payload.source.module for {item_id}")
        all_items.append(row)
        items_by_module[module].append(row)

    project = LeanProject(str(lean_project))

    results: dict[str, dict[str, Any]] = {}
    for module, module_items in items_by_module.items():
        rel_path = module.replace(".", "/") + ".lean"
        source_file = mathlib_root / rel_path
        if not source_file.exists():
            for item in module_items:
                results[item["item_id"]] = {
                    "item_id": item["item_id"],
                    "tree_extractable": False,
                    "error": "no_source_file",
                }
            continue

        try:
            lean_file = project.load_file(source_file)
        except Exception as exc:
            for item in module_items:
                results[item["item_id"]] = {
                    "item_id": item["item_id"],
                    "tree_extractable": False,
                    "error": f"load_file_failed: {str(exc)[:150]}",
                }
            continue

        # Build a map of qualname -> theorem extractability from loaded file.
        # LeanTheorem.name is None from load_file(), so we extract names from source spans.
        file_content = source_file.read_text(encoding="utf-8")
        theorem_by_name: dict[str, LeanTheorem] = {}
        for thm in lean_file.theorems:
            if isinstance(thm, StoredError):
                continue
            source_text = thm.span.read_from_string(file_content)
            name = _extract_decl_name(source_text)
            if name is not None:
                # The name from the span is the short name (e.g. "id").
                # The corpus qualname includes the module prefix (e.g. "Mathlib.Logic.Basic.id").
                # Store both: full qualified and short, preferring full qualified.
                full_name = f"{module}.{name}" if "." not in name else name
                theorem_by_name[full_name] = thm
                theorem_by_name[name] = thm

        for item in module_items:
            item_id = item["item_id"]
            qualname = item["payload"]["source"].get("qualname", "")
            thm = theorem_by_name.get(qualname)
            if thm is None:
                # Try short name (qualname without module prefix)
                short = qualname.removeprefix(module + ".")
                thm = theorem_by_name.get(short)
            if thm is None:
                results[item_id] = {
                    "item_id": item_id,
                    "tree_extractable": False,
                    "error": "no_match",
                }
                continue

            trees_ok = 0
            trees_failed = 0
            for block in thm.by_blocks:
                if isinstance(block, StoredError):
                    trees_failed += 1
                elif block.tree is None or isinstance(block.tree, StoredError):
                    trees_failed += 1
                else:
                    trees_ok += 1
            trees_total = trees_ok + trees_failed
            results[item_id] = {
                "item_id": item_id,
                "tree_extractable": trees_ok > 0,
                "trees_ok": trees_ok,
                "trees_failed": trees_failed,
                "trees_total": trees_total,
            }

    # Preserve items.jsonl ordering
    rows: list[dict[str, Any]] = []
    for item in all_items:
        item_id = item["item_id"]
        rows.append(results[item_id])
    return rows


def _derive_tree_extractable_slice(
    *,
    build_dir: Path,
    backend: str,
    corpus_id: str,
    parent_build_id: str,
    parent_manifest: dict[str, Any],
    parent_items_path: Path,
    validation_path: Path,
    extractable_ids: set[str],
    min_extractable_rate: float,
) -> Path:
    derived_root = build_dir / "derived" / "tree-extractable"
    derived_root.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, Any]] = []
    for row in iter_jsonl(parent_items_path):
        item_id = row.get("item_id")
        if isinstance(item_id, str) and item_id in extractable_ids:
            items.append(row)

    tmp_dir = derived_root / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_items = tmp_dir / f"items.{os.getpid()}.jsonl.tmp"
    write_jsonl(tmp_items, items)
    derived_items_sha = sha256_file(tmp_items)
    validation_sha = sha256_file(validation_path)

    fingerprint = {
        "kind": "derived_tree_extractable",
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
        copied = derived_dir / "tree_validation.jsonl"
        if not copied.exists():
            shutil.copy2(validation_path, copied)
        if tmp_items.exists():
            tmp_items.unlink()
        return derived_dir

    derived_dir.mkdir(parents=True, exist_ok=False)
    tmp_items.replace(derived_dir / "items.jsonl")
    shutil.copy2(validation_path, derived_dir / "tree_validation.jsonl")

    provenance = list(parent_manifest.get("provenance") or [])
    provenance.append(
        {
            "kind": "derived",
            "derived_kind": "tree-extractable",
            "parent_build_id": parent_build_id,
            "validation_sha256": validation_sha,
            "min_extractable_rate": min_extractable_rate,
        }
    )
    build_config = dict(parent_manifest.get("build_config") or {})
    build_config.update(
        {
            "derived_kind": "tree-extractable",
            "parent_build_id": parent_build_id,
            "validation_sha256": validation_sha,
            "min_extractable_rate": min_extractable_rate,
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


def validate_tree_extractability(
    *,
    corpus_ref: str,
    lean_project: Path | None = None,
    min_extractable_rate: float = 0.5,
    allow_low_extractability: bool = False,
) -> TreeValidationSummary:
    """Run tree extractability validation and derive a tree-extractable slice."""
    ref = parse_corpus_ref(corpus_ref)
    if ref.derived is not None:
        raise ValueError(
            "validate-tree-extractability expects a base corpus ref (no #derived). "
            f"Got: {corpus_ref!r}"
        )
    build_dir = resolve_corpus_build_dir(ref)
    manifest = _load_manifest(build_dir)
    backend = str(manifest.get("backend") or ref.backend)
    if backend != "lean":
        raise ValueError(
            f"Tree extractability validation is only supported for lean corpora, got: {backend}"
        )
    corpus_id = str(manifest.get("corpus_id") or ref.corpus_id)
    parent_build_id = str(manifest.get("build_id") or "")
    if not parent_build_id:
        raise ValueError(f"manifest.json missing build_id: {build_dir / 'manifest.json'}")

    items_path = _items_path(build_dir, manifest)

    project_dir = lean_project or (DOSSIER_ROOT / "lean_project")
    mathlib_root = project_dir / ".lake" / "packages" / "mathlib"
    if not mathlib_root.exists():
        raise FileNotFoundError(
            f"mathlib not found at {mathlib_root} (run lean setup first)"
        )

    rows = _lean_tree_extract_check(
        lean_project=project_dir,
        items_path=items_path,
        mathlib_root=mathlib_root,
    )

    validation_path = build_dir / "tree_validation.jsonl"
    write_jsonl(validation_path, rows)

    extractable_ids = {
        r["item_id"]
        for r in rows
        if r.get("tree_extractable") is True and isinstance(r.get("item_id"), str)
    }
    extractable_count = len(extractable_ids)
    validated_count = len(rows)
    non_extractable_count = validated_count - extractable_count
    extractable_rate = (extractable_count / validated_count) if validated_count else 0.0

    if validated_count == 0:
        raise RuntimeError(f"No items checked for {corpus_ref}")
    if (extractable_rate < min_extractable_rate) and not allow_low_extractability:
        raise RuntimeError(
            f"Extractable rate too low for {corpus_ref}: {extractable_rate:.1%} "
            f"({extractable_count}/{validated_count}); "
            f"set --allow-low-extractability to override."
        )

    derived_dir = _derive_tree_extractable_slice(
        build_dir=build_dir,
        backend=backend,
        corpus_id=corpus_id,
        parent_build_id=parent_build_id,
        parent_manifest=manifest,
        parent_items_path=items_path,
        validation_path=validation_path,
        extractable_ids=extractable_ids,
        min_extractable_rate=min_extractable_rate,
    )
    return TreeValidationSummary(
        corpus_ref=corpus_ref,
        build_dir=build_dir,
        validated_count=validated_count,
        extractable_count=extractable_count,
        non_extractable_count=non_extractable_count,
        extractable_rate=extractable_rate,
        validation_path=validation_path,
        derived_dir=derived_dir,
    )
