from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from analysis.cross_assistant_paired_benchmark import load_benchmark_manifest
from corpus.artifacts import (
    compute_build_id,
    iter_jsonl,
    load_manifest,
    make_manifest,
    parse_corpus_ref,
    resolve_build_dir,
    resolve_corpus_artifact_root,
    sha256_file,
    write_current_id,
    write_json_atomic,
    write_jsonl,
)

LEAN_ITEM_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_']*$")


def _lean_ident_component(raw: str) -> str:
    """Encode an arbitrary Lean name fragment into a Lean identifier fragment.

    Artifact corpora use item_id as the Lean declaration name, so item_id must match
    `[A-Za-z_][A-Za-z0-9_']*`.
    """
    if not isinstance(raw, str) or not raw:
        return "anon"
    parts: list[str] = []
    for ch in raw:
        if (
            ("A" <= ch <= "Z")
            or ("a" <= ch <= "z")
            or ("0" <= ch <= "9")
            or ch in {"_", "'"}
        ):
            parts.append(ch)
        else:
            parts.append(f"_x{ord(ch):02x}")
    out = "".join(parts)
    if not (("A" <= out[0] <= "Z") or ("a" <= out[0] <= "z") or out[0] == "_"):
        out = "_" + out
    return out


def _lean_stmt_to_sorry(statement: str) -> str:
    """Convert a theorem/lemma declaration into a theorem {name} ... := by\n  sorry.

    The input should be a Lean declaration (possibly spanning multiple lines) that
    contains ':= by'. We keep the header and replace the proof with `sorry`.
    """
    idx = statement.find(":= by")
    if idx == -1:
        raise ValueError("Expected ':= by' in declaration")
    header = statement[:idx].rstrip()
    header = re.sub(r"^(protected\s+)?(theorem|lemma)\b", "theorem", header, count=1)
    # Replace the declared name with {name}. We assume the first identifier after 'theorem'
    # is the declaration name.
    header = re.sub(r"^(theorem\s+)([A-Za-z0-9_'.]+)\b", r"\1{name}", header, count=1)
    return header + " := by\n  sorry"


def _resolve_lake_binary() -> str:
    lake = shutil.which("lake")
    if lake:
        return lake
    elan_lake = Path.home() / ".elan" / "bin" / "lake"
    if elan_lake.is_file():
        return str(elan_lake)
    raise FileNotFoundError(
        "Lean tool 'lake' not found on PATH or at ~/.elan/bin/lake. "
        "Install elan or export PATH so corpus extraction can run."
    )


@dataclass(frozen=True)
class BuiltCorpus:
    backend: str
    corpus_id: str
    build_id: str
    build_dir: Path

    def ref(self) -> str:
        return f"{self.backend}:{self.corpus_id}@{self.build_id}"


def _write_items_jsonl(tmp_path: Path, items: list[dict[str, Any]]) -> tuple[str, int]:
    """Write items.jsonl in canonical JSON order; returns (sha256, count)."""
    write_jsonl(tmp_path, items)
    return sha256_file(tmp_path), len(items)


def _finalize_build(
    *,
    backend: str,
    corpus_id: str,
    provenance: list[dict[str, Any]],
    build_config: dict[str, Any],
    item_id_scheme: str,
    items: list[dict[str, Any]],
) -> BuiltCorpus:
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("items must be a list of dicts")
        if not isinstance(item.get("item_id"), str) or not item["item_id"]:
            raise ValueError("Each item must have a non-empty string item_id")
        if "payload" not in item or not isinstance(item["payload"], dict):
            raise ValueError(f"Item missing payload dict: {item.get('item_id')}")

    items.sort(key=lambda d: d["item_id"])
    ids = [it["item_id"] for it in items]
    dupes: list[str] = []
    for prev, curr in zip(ids, ids[1:]):
        if curr == prev:
            if not dupes or dupes[-1] != curr:
                dupes.append(curr)
    if dupes:
        raise ValueError(f"Duplicate item_id(s): {dupes[:10]}")

    root = resolve_corpus_artifact_root()
    base_dir = root / backend / corpus_id
    base_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w",
        dir=base_dir,
        prefix="items.",
        suffix=".jsonl.tmp",
        delete=False,
        encoding="utf-8",
        newline="\n",
    ) as f:
        tmp_items_path = Path(f.name)
    try:
        items_sha256, items_total = _write_items_jsonl(tmp_items_path, items)
        fingerprint = {
            "backend": backend,
            "corpus_id": corpus_id,
            "provenance": provenance,
            "build_config": build_config,
            "item_id_scheme": item_id_scheme,
            "items_sha256": items_sha256,
            "items_total": items_total,
        }
        build_id = compute_build_id(fingerprint)
        build_dir = base_dir / build_id
        items_file = "items.jsonl"

        if build_dir.exists():
            manifest_path = build_dir / "manifest.json"
            if not manifest_path.exists():
                raise RuntimeError(f"Build dir exists but manifest missing: {manifest_path}")
            manifest = json.loads(manifest_path.read_text())
            if not isinstance(manifest, dict):
                raise RuntimeError(f"Invalid manifest.json: {manifest_path}")
            if str(manifest.get("items_sha256") or "") != items_sha256:
                raise RuntimeError(
                    "Existing build has different items_sha256; refusing to reuse "
                    f"({build_id} at {build_dir})"
                )
            write_current_id(base_dir, build_id)
            return BuiltCorpus(
                backend=backend,
                corpus_id=corpus_id,
                build_id=build_id,
                build_dir=build_dir,
            )

        build_dir.mkdir(parents=True, exist_ok=False)
        tmp_items_path.replace(build_dir / items_file)

        manifest = make_manifest(
            backend=backend,
            corpus_id=corpus_id,
            build_id=build_id,
            provenance=provenance,
            build_config=build_config,
            items_file=items_file,
            items_sha256=items_sha256,
            item_id_scheme=item_id_scheme,
            items_total=items_total,
        )
        write_json_atomic(build_dir / "manifest.json", manifest)
        write_current_id(base_dir, build_id)
        return BuiltCorpus(
            backend=backend,
            corpus_id=corpus_id,
            build_id=build_id,
            build_dir=build_dir,
        )
    finally:
        if tmp_items_path.exists():
            tmp_items_path.unlink()


def _read_mathlib_pins(lean_project: Path) -> tuple[str, str]:
    toolchain = (lean_project / "lean-toolchain").read_text(encoding="utf-8").strip()
    manifest_path = lean_project / "lake-manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    pkgs = data.get("packages") if isinstance(data, dict) else None
    if not isinstance(pkgs, list):
        raise ValueError(f"Invalid lake-manifest.json: {manifest_path}")
    mathlib = None
    for pkg in pkgs:
        if isinstance(pkg, dict) and pkg.get("name") == "mathlib":
            mathlib = pkg
            break
    if not isinstance(mathlib, dict):
        raise ValueError("mathlib package not found in lake-manifest.json")
    rev = str(mathlib.get("rev") or "").strip()
    if not rev:
        raise ValueError("mathlib rev missing in lake-manifest.json")
    return toolchain, rev


def _source_items_path(build_dir: Path, manifest: dict[str, Any]) -> Path:
    items_file = manifest.get("items_file") or "items.jsonl"
    if not isinstance(items_file, str) or not items_file:
        raise ValueError(f"Invalid source manifest items_file: {build_dir / 'manifest.json'}")
    items_path = build_dir / items_file
    if not items_path.exists():
        raise FileNotFoundError(f"Source corpus items not found: {items_path}")
    return items_path


def build_lean_subset(
    *,
    corpus_id: str,
    source_ref: str,
    theorems_path: Path,
) -> BuiltCorpus:
    requested = [
        line.strip()
        for line in theorems_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not requested:
        raise ValueError(f"No theorem identifiers found in {theorems_path}")
    if len(set(requested)) != len(requested):
        dupes = [
            theorem
            for theorem, count in Counter(requested).items()
            if count > 1
        ]
        raise ValueError(f"Duplicate theorem identifiers in {theorems_path}: {dupes[:10]}")

    if ":" not in source_ref:
        return _build_lean_subset_from_named_corpus(
            corpus_id=corpus_id,
            source_name=source_ref,
            theorems_path=theorems_path,
            requested=requested,
        )

    ref = parse_corpus_ref(source_ref)
    if ref.backend != "lean":
        raise ValueError(f"Expected Lean source ref, got {source_ref!r}")
    if ref.derived is not None:
        raise ValueError("build_lean_subset does not support derived source refs")
    source = resolve_build_dir(ref.backend, ref.corpus_id, build_id=ref.build_id)
    manifest = load_manifest(source.build_dir)
    items_path = _source_items_path(source.build_dir, manifest)
    by_id = {str(item.get("item_id")): item for item in iter_jsonl(items_path)}
    missing = [theorem for theorem in requested if theorem not in by_id]
    if missing:
        preview = ", ".join(missing[:10])
        raise ValueError(
            f"{len(missing)} requested theorem identifiers were not found in {source_ref}: "
            f"{preview}"
        )

    selected = [dict(by_id[theorem]) for theorem in requested]
    provenance = list(manifest.get("provenance") or [])
    provenance.append(
        {
            "kind": "lean_subset",
            "source_ref": source_ref,
            "source_build_id": source.build_id,
            "theorems_path": str(theorems_path),
        }
    )
    return _finalize_build(
        backend="lean",
        corpus_id=corpus_id,
        provenance=provenance,
        build_config={
            "source_ref": source_ref,
            "source_build_id": source.build_id,
            "requested_count": len(requested),
            "selected_count": len(selected),
            "theorems_path": str(theorems_path),
        },
        item_id_scheme=str(manifest.get("item_id_scheme") or "source_item_id"),
        items=selected,
    )


def _build_lean_subset_from_named_corpus(
    *,
    corpus_id: str,
    source_name: str,
    theorems_path: Path,
    requested: list[str],
) -> BuiltCorpus:
    from corpus.lean.harder_theorems import CORPUS_HARD
    from corpus.lean.research import CORPUS_RESEARCH
    from corpus.lean.theorems import (
        CORPUS,
        CORPUS_EXPANDED,
        CORPUS_MATHLIB,
        CORPUS_MINIF2F,
        CORPUS_PROVERBENCH,
        DEEPSEEK_CORPUS,
    )

    named = {
        "easy": CORPUS,
        "hard": CORPUS_HARD,
        "research": CORPUS_RESEARCH,
        "deepseek": DEEPSEEK_CORPUS,
        "expanded": CORPUS_EXPANDED,
        "mathlib": CORPUS_MATHLIB,
        "minif2f": CORPUS_MINIF2F,
        "proverbench": CORPUS_PROVERBENCH,
    }
    if source_name not in named:
        raise ValueError(f"Unknown named Lean source corpus: {source_name}")
    by_id = {theorem.name: theorem for theorem in named[source_name]}
    missing = [theorem for theorem in requested if theorem not in by_id]
    if missing:
        preview = ", ".join(missing[:10])
        raise ValueError(
            f"{len(missing)} requested theorem identifiers were not found in {source_name}: "
            f"{preview}"
        )
    selected = [
        {
            "item_id": theorem,
            "payload": {
                "statement": by_id[theorem].statement,
                "display_name": theorem,
                "source_corpus": source_name,
            },
        }
        for theorem in requested
    ]
    return _finalize_build(
        backend="lean",
        corpus_id=corpus_id,
        provenance=[
            {
                "kind": "lean_named_subset",
                "source_ref": source_name,
                "theorems_path": str(theorems_path),
            }
        ],
        build_config={
            "source_ref": source_name,
            "requested_count": len(requested),
            "selected_count": len(selected),
            "theorems_path": str(theorems_path),
        },
        item_id_scheme="named_corpus_item_id",
        items=selected,
    )


def build_lean_mathlib(
    *,
    corpus_id: str,
    lean_project: Path,
    limit: int | None = None,
    elementary_only: bool = True,
) -> BuiltCorpus:
    mathlib_root = lean_project / ".lake" / "packages" / "mathlib"
    if not mathlib_root.exists():
        raise FileNotFoundError(f"mathlib not found under {mathlib_root} (run Lean setup first)")

    toolchain, mathlib_rev = _read_mathlib_pins(lean_project)

    elementary_markers = [
        "Mathlib/Logic/",
        "Mathlib/Data/Bool/",
        "Mathlib/Data/Nat/Basic",
        "Mathlib/Data/Nat/Order",
        "Mathlib/Data/Nat/Defs",
        "Mathlib/Data/Int/Basic",
        "Mathlib/Data/Int/Order",
        "Mathlib/Data/List/Basic",
        "Mathlib/Data/List/Defs",
        "Mathlib/Data/Set/Basic",
        "Mathlib/Data/Set/Function",
        "Mathlib/Data/Finset/Basic",
        "Mathlib/Data/Option/Basic",
        "Mathlib/Data/Prod/Basic",
        "Mathlib/Data/Sum/Basic",
        "Mathlib/Order/Basic",
        "Mathlib/Algebra/Group/Basic",
        "Mathlib/Algebra/Ring/Basic",
        "Mathlib/Tactic/",
    ]

    module_prefixes: list[str] = []
    if elementary_only:
        for m in elementary_markers:
            module_prefixes.append(m.removesuffix("/").replace("/", "."))

    def _module_from_mathlib_relpath(rel: str) -> str:
        rel = rel.removesuffix(".lean")
        return rel.replace("/", ".")

    if elementary_only:
        mods: set[str] = set()
        for m in elementary_markers:
            if m.endswith("/"):
                root = mathlib_root / m.removesuffix("/")
                if not root.exists():
                    continue
                for path in sorted(root.glob("**/*.lean")):
                    rel = path.relative_to(mathlib_root).as_posix()
                    mods.add(_module_from_mathlib_relpath(rel))
            else:
                path = mathlib_root / f"{m}.lean"
                if not path.exists():
                    continue
                rel = path.relative_to(mathlib_root).as_posix()
                mods.add(_module_from_mathlib_relpath(rel))
        import_modules = sorted(mods)
        if not import_modules:
            import_modules = ["Mathlib"]
    else:
        import_modules = ["Mathlib"]

    repo_root = Path(__file__).resolve().parents[4]
    extractor_dir = repo_root / "addenda" / "lean-corpus-extractor"
    lake_bin = _resolve_lake_binary()
    extractor_bin = _resolve_lean_extractor_binary()

    def _run_extractor(
        *,
        imports: list[str],
        prefixes: list[str],
        limit: int | None,
    ) -> list[dict[str, Any]]:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=str(lean_project),
            prefix="mathlib_extract.",
            suffix=".jsonl",
            delete=False,
            encoding="utf-8",
            newline="\n",
        ) as f:
            out_path = Path(f.name)
        try:
            cmd = [
                lake_bin,
                "env",
                str(extractor_bin),
                "--out",
                str(out_path),
                "--pp-width",
                "200",
            ]
            for mod in imports:
                cmd.extend(["--import", mod])
            for p in prefixes:
                cmd.extend(["--module-prefix", p])
            if limit is not None:
                cmd.extend(["--limit", str(limit)])

            subprocess.run(cmd, cwd=lean_project, check=True)

            out: list[dict[str, Any]] = []
            with out_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if not isinstance(obj, dict):
                        continue
                    out.append(obj)
            return out
        finally:
            out_path.unlink(missing_ok=True)

    import_strategy: str
    imports_used: list[str]
    if elementary_only and limit is not None:
        import_strategy = "iterative_modules"
        imports_used = []
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for mod in import_modules:
            if len(items) >= limit:
                break
            batch = _run_extractor(imports=[mod], prefixes=[mod], limit=limit - len(items))
            imports_used.append(mod)
            for obj in batch:
                item_id = obj.get("item_id")
                if not isinstance(item_id, str) or not item_id:
                    continue
                if item_id in seen:
                    continue
                seen.add(item_id)
                items.append(obj)
                if len(items) >= limit:
                    break
    else:
        import_strategy = "full"
        imports_used = import_modules
        items = _run_extractor(imports=import_modules, prefixes=module_prefixes, limit=limit)

    provenance = [
        {"kind": "lean_toolchain", "toolchain": toolchain, "mathlib_rev": mathlib_rev},
        {
            "kind": "git",
            "repo": "mathlib4",
            "url": "https://github.com/leanprover-community/mathlib4",
            "rev": mathlib_rev,
        },
    ]
    build_config = {
        "source": "mathlib4_env",
        "elementary_only": elementary_only,
        "module_prefixes": module_prefixes,
        "limit": limit,
        "extractor": {
            "kind": "lean_env",
            "project": str(extractor_dir),
            "binary": str(extractor_bin),
            "import_strategy": import_strategy,
            "imports": imports_used,
            "imports_total_candidates": len(import_modules),
            "pp": {"width": 200, "unicode": False},
        },
    }
    item_id_scheme = (
        "encodeLeanIdent(<qualname>) "
        "(Lean environment extractor; collision-free encoding of non-alphanumerics)"
    )
    return _finalize_build(
        backend="lean",
        corpus_id=corpus_id,
        provenance=provenance,
        build_config=build_config,
        item_id_scheme=item_id_scheme,
        items=items,
    )


def _ensure_git_checkout(*, repo_url: str, rev: str, dest: Path) -> None:
    if dest.exists():
        got = subprocess.run(
            ["git", "-C", str(dest), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        if got != rev:
            raise RuntimeError(f"Existing checkout at {dest} is at {got}, expected {rev}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", repo_url, str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "checkout", rev], check=True)


def _sha256_lines(lines: list[str]) -> str:
    payload = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for value in raw:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if cleaned:
            out.append(cleaned)
    return out


def _read_1000_plus_frontmatter(path: Path) -> tuple[dict[str, Any], str | None]:
    text = path.read_text(encoding="utf-8", errors="strict")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"Expected frontmatter start delimiter in {path}")
    end_idx: int | None = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        raise ValueError(f"Expected closing frontmatter delimiter in {path}")
    frontmatter_lines = lines[1:end_idx]

    title: str | None = None
    for line in frontmatter_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            candidate = stripped.lstrip("#").strip()
            if candidate:
                title = candidate
            continue
        break

    parsed = yaml.safe_load("\n".join(frontmatter_lines))
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise ValueError(f"Frontmatter must be a YAML object in {path}")
    return parsed, title


def _collect_1000_plus_lean_identifiers(
    thm_root: Path,
) -> tuple[list[str], dict[str, list[dict[str, Any]]], dict[str, int]]:
    files = sorted(thm_root.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"No theorem files found under {thm_root}")

    refs_by_identifier: dict[str, list[dict[str, Any]]] = {}
    ordered_identifiers: list[str] = []
    seen_identifiers: set[str] = set()
    stats = {
        "entries_total": 0,
        "entries_with_lean": 0,
        "lean_formalized_entries": 0,
        "lean_formalized_with_identifiers_entries": 0,
        "identifier_mentions_total": 0,
        "identifier_unique_total": 0,
    }

    for path in files:
        stats["entries_total"] += 1
        payload, title = _read_1000_plus_frontmatter(path)

        wikidata = payload.get("wikidata")
        if not isinstance(wikidata, str) or not re.fullmatch(r"Q[0-9]+", wikidata.strip()):
            raise ValueError(f"Invalid or missing wikidata field in {path}")
        wikidata = wikidata.strip()

        raw_id_suffix = payload.get("id_suffix")
        id_suffix: str | None
        if raw_id_suffix is None:
            id_suffix = None
        elif isinstance(raw_id_suffix, str):
            cleaned = raw_id_suffix.strip()
            id_suffix = cleaned or None
        else:
            raise ValueError(f"id_suffix must be a string when present in {path}")

        wikipedia_links = _normalize_string_list(payload.get("wikipedia_links"))
        theorem_title = title or f"{wikidata}{id_suffix or ''}"

        lean_entries = payload.get("lean")
        if not isinstance(lean_entries, list):
            continue
        stats["entries_with_lean"] += 1

        for lean_entry in lean_entries:
            if not isinstance(lean_entry, dict):
                continue
            status = lean_entry.get("status")
            if not isinstance(status, str) or status.strip() != "formalized":
                continue
            stats["lean_formalized_entries"] += 1

            identifiers = _normalize_string_list(lean_entry.get("identifiers"))
            if not identifiers:
                continue
            stats["lean_formalized_with_identifiers_entries"] += 1

            library = lean_entry.get("library")
            url = lean_entry.get("url")
            date = lean_entry.get("date")
            comment = lean_entry.get("comment")
            authors = _normalize_string_list(lean_entry.get("authors"))

            theorem_ref = {
                "wikidata": wikidata,
                "id_suffix": id_suffix,
                "title": theorem_title,
                "wikipedia_links": wikipedia_links,
                "library": (
                    library.strip() if isinstance(library, str) and library.strip() else None
                ),
                "url": url.strip() if isinstance(url, str) and url.strip() else None,
                "authors": authors,
                "date": date.strip() if isinstance(date, str) and date.strip() else None,
                "comment": (
                    comment.strip() if isinstance(comment, str) and comment.strip() else None
                ),
            }

            for identifier in identifiers:
                stats["identifier_mentions_total"] += 1
                refs_by_identifier.setdefault(identifier, []).append(theorem_ref)
                if identifier in seen_identifiers:
                    continue
                seen_identifiers.add(identifier)
                ordered_identifiers.append(identifier)

    stats["identifier_unique_total"] = len(ordered_identifiers)
    return ordered_identifiers, refs_by_identifier, stats


def _resolve_lean_extractor_binary() -> Path:
    repo_root = Path(__file__).resolve().parents[4]
    extractor_dir = repo_root / "addenda" / "lean-corpus-extractor"
    if not extractor_dir.exists():
        raise FileNotFoundError(f"Lean extractor not found: {extractor_dir}")
    extractor_bin = extractor_dir / ".lake" / "build" / "bin" / "lean_corpus_extract"
    if not extractor_bin.exists():
        subprocess.run([_resolve_lake_binary(), "build"], cwd=extractor_dir, check=True)
    if not extractor_bin.exists():
        raise FileNotFoundError(f"Extractor binary missing after build: {extractor_bin}")
    return extractor_bin


def _extract_lean_named_theorems(
    *,
    lean_project: Path,
    names: list[str],
) -> list[dict[str, Any]]:
    unique_names: list[str] = []
    seen: set[str] = set()
    for name in names:
        cleaned = name.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique_names.append(cleaned)
    if not unique_names:
        return []

    extractor_bin = _resolve_lean_extractor_binary()
    with tempfile.NamedTemporaryFile(
        "w",
        dir=str(lean_project),
        prefix="named_extract.",
        suffix=".jsonl",
        delete=False,
        encoding="utf-8",
        newline="\n",
    ) as f:
        out_path = Path(f.name)
    try:
        cmd = [
            _resolve_lake_binary(),
            "env",
            str(extractor_bin),
            "--out",
            str(out_path),
            "--pp-width",
            "200",
            "--import",
            "Mathlib",
        ]
        for name in unique_names:
            cmd.extend(["--name", name])

        subprocess.run(cmd, cwd=lean_project, check=True)

        rows: list[dict[str, Any]] = []
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    continue
                rows.append(obj)
        return rows
    finally:
        out_path.unlink(missing_ok=True)


def build_lean_1000_plus(
    *,
    corpus_id: str,
    rev: str,
    lean_project: Path,
    repo_url: str = "https://github.com/1000-plus/1000-plus.github.io",
    limit: int | None = None,
    allow_missing_resolution: bool = True,
) -> BuiltCorpus:
    rev = rev.strip()
    if not rev:
        raise ValueError("--rev is required (pin a 1000-plus commit SHA)")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be >= 1")
    if not lean_project.exists():
        raise FileNotFoundError(f"Lean project not found: {lean_project}")

    toolchain, mathlib_rev = _read_mathlib_pins(lean_project)

    root = resolve_corpus_artifact_root()
    checkout = root / "sources" / "git" / "1000-plus.github.io" / rev
    _ensure_git_checkout(repo_url=repo_url, rev=rev, dest=checkout)
    thm_root = checkout / "_thm"
    if not thm_root.exists():
        raise FileNotFoundError(f"1000-plus theorem directory not found: {thm_root}")

    ordered_identifiers, refs_by_identifier, eligibility_stats = (
        _collect_1000_plus_lean_identifiers(thm_root)
    )
    if not ordered_identifiers:
        raise RuntimeError(
            "No eligible Lean formalized entries with identifiers in 1000-plus source"
        )

    selected_identifiers = (
        ordered_identifiers[:limit] if limit is not None else list(ordered_identifiers)
    )
    extracted_rows = _extract_lean_named_theorems(
        lean_project=lean_project,
        names=selected_identifiers,
    )
    selected_set = set(selected_identifiers)
    extracted_by_name: dict[str, dict[str, Any]] = {}
    for row in extracted_rows:
        display_name = row.get("display_name")
        item_id = row.get("item_id")
        payload = row.get("payload")
        if not isinstance(display_name, str) or not display_name:
            raise ValueError("Extractor row missing display_name")
        if display_name not in selected_set:
            continue
        if not isinstance(item_id, str) or not item_id:
            raise ValueError(f"Extractor row missing item_id for {display_name}")
        if not isinstance(payload, dict):
            raise ValueError(f"Extractor row missing payload for {display_name}")
        if display_name in extracted_by_name:
            raise ValueError(f"Duplicate extractor row for {display_name}")
        extracted_by_name[display_name] = row

    unresolved_identifiers = [
        name for name in selected_identifiers if name not in extracted_by_name
    ]
    if unresolved_identifiers and not allow_missing_resolution:
        raise RuntimeError(
            "Unresolved Lean identifiers in selected 1000-plus slice: "
            f"{len(unresolved_identifiers)} missing"
        )

    items: list[dict[str, Any]] = []
    for identifier in selected_identifiers:
        row = extracted_by_name.get(identifier)
        if row is None:
            continue

        statement = row["payload"].get("statement")
        source = row["payload"].get("source")
        if not isinstance(statement, str) or "{name}" not in statement:
            raise ValueError(f"Extractor statement is invalid for {identifier}")
        if not isinstance(source, dict):
            raise ValueError(f"Extractor source metadata missing for {identifier}")

        refs = refs_by_identifier.get(identifier) or []
        if not refs:
            raise ValueError(f"No 1000-plus metadata refs recorded for {identifier}")
        sorted_refs = sorted(
            refs,
            key=lambda ref: (
                str(ref.get("wikidata") or ""),
                str(ref.get("id_suffix") or ""),
                str(ref.get("url") or ""),
            ),
        )
        deduped_refs: list[dict[str, Any]] = []
        seen_ref_keys: set[tuple[str, str, str]] = set()
        for ref in sorted_refs:
            key = (
                str(ref.get("wikidata") or ""),
                str(ref.get("id_suffix") or ""),
                str(ref.get("url") or ""),
            )
            if key in seen_ref_keys:
                continue
            seen_ref_keys.add(key)
            deduped_refs.append(ref)

        enriched_source = dict(source)
        extractor_kind = enriched_source.get("kind")
        enriched_source["extractor_source_kind"] = (
            str(extractor_kind) if isinstance(extractor_kind, str) and extractor_kind else None
        )
        enriched_source["kind"] = "1000_plus_lean"
        enriched_source["repository"] = "1000-plus.github.io"
        enriched_source["repository_url"] = repo_url
        enriched_source["repository_rev"] = rev
        enriched_source["identifier"] = identifier
        enriched_source["thm_refs"] = deduped_refs

        items.append(
            {
                "item_id": row["item_id"],
                "display_name": row["display_name"],
                "payload": {
                    "statement": statement,
                    "source": enriched_source,
                },
            }
        )

    if not items:
        raise RuntimeError(
            "No selected 1000-plus Lean identifiers could be resolved in the local Lean environment"
        )

    unresolved_sha = _sha256_lines(unresolved_identifiers)
    provenance = [
        {"kind": "git", "repo": "1000-plus.github.io", "url": repo_url, "rev": rev},
        {"kind": "lean_toolchain", "toolchain": toolchain, "mathlib_rev": mathlib_rev},
    ]
    build_config = {
        "source": "1000-plus.github.io",
        "repo_url": repo_url,
        "rev": rev,
        "limit": limit,
        "lean_project": str(lean_project),
        "eligibility": {
            "lean_status": "formalized",
            "require_identifiers": True,
        },
        "entries_total": eligibility_stats["entries_total"],
        "entries_with_lean": eligibility_stats["entries_with_lean"],
        "lean_formalized_entries": eligibility_stats["lean_formalized_entries"],
        "lean_formalized_with_identifiers_entries": eligibility_stats[
            "lean_formalized_with_identifiers_entries"
        ],
        "identifier_mentions_total": eligibility_stats["identifier_mentions_total"],
        "identifier_candidate_total": eligibility_stats["identifier_unique_total"],
        "identifier_requested_count": len(selected_identifiers),
        "identifier_resolved_count": len(items),
        "identifier_unresolved_count": len(unresolved_identifiers),
        "identifier_unresolved_sha256": unresolved_sha,
        "identifier_unresolved_preview": unresolved_identifiers[:20],
    }
    item_id_scheme = "encodeLeanIdent(<qualname>) via lean-corpus-extractor --name"
    return _finalize_build(
        backend="lean",
        corpus_id=corpus_id,
        provenance=provenance,
        build_config=build_config,
        item_id_scheme=item_id_scheme,
        items=items,
    )


def build_lean_minif2f(
    *,
    corpus_id: str,
    rev: str,
    repo_url: str = "https://github.com/yangky11/miniF2F-lean4",
    splits: list[str] | None = None,
    limit: int | None = None,
    repo_path: Path | None = None,
) -> BuiltCorpus:
    if not rev.strip():
        raise ValueError("--rev is required (pin a commit SHA)")
    if splits is None:
        splits = ["Test", "Valid"]
    splits = [s.strip() for s in splits if s.strip()]
    if not splits:
        raise ValueError("splits must be non-empty")

    if repo_path is None:
        root = resolve_corpus_artifact_root()
        checkout = root / "sources" / "git" / "miniF2F-lean4" / rev
        _ensure_git_checkout(repo_url=repo_url, rev=rev, dest=checkout)
        repo_path = checkout
    if not repo_path.exists():
        raise FileNotFoundError(f"miniF2F repo not found: {repo_path}")

    items: list[dict[str, Any]] = []
    for split in splits:
        split_dir = repo_path / "MiniF2F" / split
        if not split_dir.exists():
            raise FileNotFoundError(f"miniF2F split dir not found: {split_dir}")
        for path in sorted(split_dir.glob("*.lean")):
            text = path.read_text(encoding="utf-8", errors="strict")
            m = re.search(r"\b(theorem|lemma)\s+([A-Za-z0-9_']+)\b", text)
            if not m:
                continue
            # Keep the original statement header up to ':= by', then replace proof with sorry.
            by_idx = text.find(":= by")
            if by_idx == -1:
                continue
            header = text[:by_idx].strip()
            header = re.sub(
                r"\b(theorem|lemma)\s+([A-Za-z0-9_']+)\b",
                "theorem {name}",
                header,
                count=1,
            )
            stmt = header + " := by\n  sorry"
            name = m.group(2)
            item_id = f"minif2f__{split.lower()}__{_lean_ident_component(name)}"
            items.append(
                {
                    "item_id": item_id,
                    "display_name": name,
                    "payload": {
                        "statement": stmt,
                        "source": {
                            "kind": "miniF2F-lean4",
                            "split": split,
                            "file": str(path.relative_to(repo_path).as_posix()),
                            "rev": rev,
                        },
                    },
                }
            )
            if limit is not None and len(items) >= limit:
                break
        if limit is not None and len(items) >= limit:
            break

    provenance = [
        {"kind": "git", "repo": "miniF2F-lean4", "url": repo_url, "rev": rev},
    ]
    build_config = {
        "source": "miniF2F-lean4",
        "repo_url": repo_url,
        "rev": rev,
        "splits": splits,
        "limit": limit,
    }
    item_id_scheme = "minif2f__<split>__<theorem_name_safe>"
    return _finalize_build(
        backend="lean",
        corpus_id=corpus_id,
        provenance=provenance,
        build_config=build_config,
        item_id_scheme=item_id_scheme,
        items=items,
    )


def build_lean_coq_paired_micro(
    *,
    corpus_id: str,
    pairs_path: Path,
    limit: int | None = None,
) -> BuiltCorpus:
    if limit is not None and limit <= 0:
        raise ValueError("limit must be >= 1")
    benchmark = load_benchmark_manifest(pairs_path)
    benchmark_id = benchmark.benchmark_id

    items: list[dict[str, Any]] = []
    for idx, pair in enumerate(benchmark.pairs):
        pair_id = pair.pair_id
        coq_theorem = pair.coq_theorem
        item_id = pair.lean_theorem
        if not LEAN_ITEM_ID_RE.match(item_id):
            raise ValueError(
                f"pairs[{idx}].lean_item_id must be a Lean identifier (got {item_id!r})"
            )
        display_name = pair.lean_display_name
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError(f"pairs[{idx}] missing lean_display_name")
        statement = pair.lean_statement
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError(f"pairs[{idx}] missing lean_statement")
        if "{name}" not in statement:
            raise ValueError(
                f"pairs[{idx}] lean_statement must contain '{{name}}' placeholder"
            )
        if ":= by" not in statement:
            raise ValueError(
                f"pairs[{idx}] lean_statement must end with ':= by ...' proof placeholder"
            )

        items.append(
            {
                "item_id": item_id,
                "display_name": display_name,
                "payload": {
                    "statement": statement,
                    "source": {
                        "kind": "coq_paired_micro",
                        "benchmark_id": benchmark_id,
                        "pair_id": pair_id,
                        "coq_theorem": coq_theorem,
                    },
                },
            }
        )
        if limit is not None and len(items) >= limit:
            break

    provenance = [
        {
            "kind": "file",
            "path": str(pairs_path.resolve()),
            "sha256": sha256_file(pairs_path),
        }
    ]
    build_config = {
        "source": "coq_paired_micro",
        "benchmark_id": benchmark_id,
        "pairs_path": str(pairs_path.resolve()),
        "pairs_total": len(benchmark.pairs),
        "limit": limit,
    }
    item_id_scheme = "pairs[].lean_item_id (manual Lean↔Coq pair benchmark corpus)"
    return _finalize_build(
        backend="lean",
        corpus_id=corpus_id,
        provenance=provenance,
        build_config=build_config,
        item_id_scheme=item_id_scheme,
        items=items,
    )


def build_lean_huggingface_deepseek_prover_v1(
    *,
    corpus_id: str,
    revision: str,
    split: str = "train",
    limit: int | None = None,
) -> BuiltCorpus:
    if not revision.strip():
        raise ValueError("--revision is required (pin a HuggingFace dataset revision)")
    from datasets import load_dataset

    ds = load_dataset("deepseek-ai/DeepSeek-Prover-V1", split=split, revision=revision)
    total = len(ds)
    width = len(str(total))
    items: list[dict[str, Any]] = []
    for idx, row in enumerate(ds):
        if limit is not None and len(items) >= limit:
            break
        if not isinstance(row, dict):
            continue
        formal = row.get("formal_statement")
        if not isinstance(formal, str) or not formal.strip():
            continue
        stmt = formal.strip()
        if stmt.startswith("theorem ") or stmt.startswith("lemma "):
            stmt = re.sub(r"^(theorem|lemma)\s+\S+", "theorem {name}", stmt, count=1)
        else:
            stmt = f"theorem {{name}} {stmt}"
        if ":= by" in stmt:
            stmt = _lean_stmt_to_sorry(stmt)
        else:
            stmt = stmt.rstrip()
            if stmt.endswith(":="):
                stmt = stmt + " by\n  sorry"
            elif not stmt.endswith("sorry"):
                stmt = stmt + " := by\n  sorry"
        item_id = f"hf_deepseek_prover_v1_{split}_{idx:0{width}d}"
        items.append(
            {
                "item_id": item_id,
                "display_name": row.get("name") if isinstance(row.get("name"), str) else None,
                "payload": {
                    "statement": stmt,
                    "source": {
                        "kind": "huggingface",
                        "dataset": "deepseek-ai/DeepSeek-Prover-V1",
                        "split": split,
                        "revision": revision,
                    },
                },
            }
        )

    provenance = [
        {
            "kind": "huggingface",
            "dataset": "deepseek-ai/DeepSeek-Prover-V1",
            "split": split,
            "revision": revision,
        }
    ]
    build_config = {
        "source": "huggingface",
        "dataset": "DeepSeek-Prover-V1",
        "split": split,
        "limit": limit,
    }
    item_id_scheme = "hf_deepseek_prover_v1_<split>_<row_index_zero_padded>"
    return _finalize_build(
        backend="lean",
        corpus_id=corpus_id,
        provenance=provenance,
        build_config=build_config,
        item_id_scheme=item_id_scheme,
        items=items,
    )


def build_lean_huggingface_proverbench(
    *,
    corpus_id: str,
    revision: str,
    split: str = "train",
    limit: int | None = None,
) -> BuiltCorpus:
    if not revision.strip():
        raise ValueError("--revision is required (pin a HuggingFace dataset revision)")
    from datasets import load_dataset

    def _convert(formal_statement: str, header: str) -> str:
        stmt = formal_statement.strip()
        # Fix common tokenization issue: "∑ i in" -> "∑ i ∈".
        stmt = re.sub(r"(∑\s+\w+\s+)in(\s+)", r"\1∈\2", stmt)
        stmt = re.sub(r"(∏\s+\w+\s+)in(\s+)", r"\1∈\2", stmt)
        stmt = re.sub(r"(⋃\s+\w+\s+)in(\s+)", r"\1∈\2", stmt)
        stmt = re.sub(r"(⋂\s+\w+\s+)in(\s+)", r"\1∈\2", stmt)

        if stmt.startswith("theorem "):
            stmt = re.sub(r"^theorem\s+\S+", "theorem {name}", stmt, count=1)
        elif stmt.startswith("lemma "):
            stmt = re.sub(r"^lemma\s+\S+", "theorem {name}", stmt, count=1)
        else:
            stmt = f"theorem {{name}} {stmt}"

        if ":= by" in stmt:
            stmt = _lean_stmt_to_sorry(stmt)
        else:
            stmt = stmt.rstrip()
            if stmt.endswith(":="):
                stmt = stmt + " by\n  sorry"
            elif not stmt.endswith("sorry"):
                stmt = stmt + " := by\n  sorry"

        prefix_lines: list[str] = []
        for line in header.splitlines():
            s = line.strip()
            if s.startswith("open ") or s.startswith("set_option "):
                prefix_lines.append(line.rstrip())
        if prefix_lines:
            stmt = "\n".join(prefix_lines) + "\n\n" + stmt
        return stmt

    ds = load_dataset("deepseek-ai/DeepSeek-ProverBench", split=split, revision=revision)
    total = len(ds)
    width = len(str(total))
    items: list[dict[str, Any]] = []
    for idx, row in enumerate(ds):
        if limit is not None and len(items) >= limit:
            break
        if not isinstance(row, dict):
            continue
        formal = row.get("formal_statement")
        header = row.get("header") if isinstance(row.get("header"), str) else ""
        if not isinstance(formal, str) or not formal.strip():
            continue
        stmt = _convert(formal, header)
        item_id = f"hf_deepseek_proverbench_{split}_{idx:0{width}d}"
        items.append(
            {
                "item_id": item_id,
                "display_name": row.get("name") if isinstance(row.get("name"), str) else None,
                "payload": {
                    "statement": stmt,
                    "source": {
                        "kind": "huggingface",
                        "dataset": "deepseek-ai/DeepSeek-ProverBench",
                        "split": split,
                        "revision": revision,
                        "area": row.get("area") if isinstance(row.get("area"), str) else None,
                    },
                },
            }
        )

    provenance = [
        {
            "kind": "huggingface",
            "dataset": "deepseek-ai/DeepSeek-ProverBench",
            "split": split,
            "revision": revision,
        }
    ]
    build_config = {
        "source": "huggingface",
        "dataset": "DeepSeek-ProverBench",
        "split": split,
        "limit": limit,
    }
    item_id_scheme = "hf_deepseek_proverbench_<split>_<row_index_zero_padded>"
    return _finalize_build(
        backend="lean",
        corpus_id=corpus_id,
        provenance=provenance,
        build_config=build_config,
        item_id_scheme=item_id_scheme,
        items=items,
    )


def build_smtlib_zenodo_unsat_slice(
    *,
    corpus_id: str,
    logic: str,
    limit: int,
    zenodo_record: str = "15493090",
    tar_path: Path | None = None,
    download_dir: Path | None = None,
) -> BuiltCorpus:
    logic = logic.strip()
    if not logic:
        raise ValueError("logic must be non-empty")
    if limit <= 0:
        raise ValueError("limit must be >= 1")

    root = resolve_corpus_artifact_root()
    downloads = download_dir or (root / "downloads" / "zenodo" / zenodo_record)
    downloads.mkdir(parents=True, exist_ok=True)

    def _download(url: str, dest: Path) -> None:
        if dest.exists():
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        import urllib.request

        with urllib.request.urlopen(url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Download failed: HTTP {resp.status} for {url}")
            with open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)

    if tar_path is None:
        tar_path = downloads / f"{logic}.tar.zst"
        url = f"https://zenodo.org/records/{zenodo_record}/files/{logic}.tar.zst"
        _download(url, tar_path)
    if not tar_path.exists():
        raise FileNotFoundError(f"Tar not found: {tar_path}")

    tar_sha256 = sha256_file(tar_path)
    tar_bin = shutil.which("gtar") or "tar"

    def _tar_supports_to_command() -> bool:
        try:
            result = subprocess.run(
                [tar_bin, "--help"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return False
        out = (result.stdout or "") + (result.stderr or "")
        return "--to-command" in out

    def _is_unsat_bytes(payload: bytes) -> bool:
        for raw in payload.splitlines():
            if b":status" in raw:
                low = raw.lower()
                if b"unsat" in low:
                    return True
                if b"sat" in low or b"unknown" in low:
                    return False
        return False

    def _collect_unsat_stream(tar_path: Path, out_dir: Path) -> list[str]:
        # Use GNU tar's --to-command to avoid extracting the full archive.
        count_path = out_dir / ".count"
        paths_path = out_dir / ".paths"
        script_path = out_dir / ".tar_to_command.py"
        count_path.write_text("0", encoding="utf-8")
        paths_path.write_text("", encoding="utf-8")
        script_path.write_text(
            "\n".join(
                [
                    "from __future__ import annotations",
                    "import os",
                    "from pathlib import Path",
                    "import sys",
                    "",
                    "def _is_unsat(payload: bytes) -> bool:",
                    "    for raw in payload.splitlines():",
                    "        if b\":status\" in raw:",
                    "            low = raw.lower()",
                    "            if b\"unsat\" in low:",
                    "                return True",
                    "            if b\"sat\" in low or b\"unknown\" in low:",
                    "                return False",
                    "    return False",
                    "",
                    "name = os.environ.get(\"TAR_FILENAME\") or os.environ.get(\"TAR_FILE\")",
                    "if not name or not name.endswith(\".smt2\"):",
                    "    raise SystemExit(0)",
                    "logic = os.environ.get(\"SMTLIB_LOGIC\", \"\")",
                    "marker = f\"non-incremental/{logic}/\"",
                    "if marker not in name:",
                    "    raise SystemExit(0)",
                    "rel = name.split(marker, 1)[1]",
                    "limit = int(os.environ.get(\"SMTLIB_LIMIT\", \"0\"))",
                    "count_path = Path(os.environ[\"SMTLIB_COUNT_FILE\"])",
                    (
                        "count = int(count_path.read_text().strip() or \"0\") "
                        "if count_path.exists() else 0"
                    ),
                    "if limit > 0 and count >= limit:",
                    "    raise SystemExit(0)",
                    "payload = sys.stdin.buffer.read()",
                    "if not payload or not _is_unsat(payload):",
                    "    raise SystemExit(0)",
                    "out_dir = Path(os.environ[\"SMTLIB_OUT\"])",
                    "dest = out_dir / rel",
                    "dest.parent.mkdir(parents=True, exist_ok=True)",
                    "dest.write_bytes(payload)",
                    "count += 1",
                    "count_path.write_text(str(count))",
                    "paths_path = Path(os.environ[\"SMTLIB_PATHS_FILE\"])",
                    "with paths_path.open(\"a\") as f:",
                    "    f.write(rel + \"\\n\")",
                ]
            ),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env.update(
            {
                "SMTLIB_LOGIC": logic,
                "SMTLIB_OUT": str(out_dir),
                "SMTLIB_LIMIT": str(limit),
                "SMTLIB_COUNT_FILE": str(count_path),
                "SMTLIB_PATHS_FILE": str(paths_path),
            }
        )
        process = subprocess.Popen(
            [
                tar_bin,
                "--zstd",
                "--to-command",
                f"{sys.executable} {script_path}",
                "-xf",
                str(tar_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        terminated_early = False
        try:
            while process.poll() is None:
                try:
                    count = int(count_path.read_text(encoding="utf-8").strip() or "0")
                except Exception:
                    count = 0
                if limit > 0 and count >= limit:
                    process.terminate()
                    terminated_early = True
                    break
            stdout, stderr = process.communicate()
            if process.returncode not in (0, None) and not terminated_early:
                raise RuntimeError(f"Extraction failed: {stderr.strip() or stdout.strip()}")
        finally:
            if script_path.exists():
                script_path.unlink()
        rel_paths = [
            ln.strip()
            for ln in paths_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        if count_path.exists():
            count_path.unlink()
        if paths_path.exists():
            paths_path.unlink()
        return rel_paths

    def _collect_unsat_full(tar_path: Path, out_dir: Path) -> list[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            extract_root = Path(tmpdir)
            subprocess.run(
                [tar_bin, "--zstd", "-xf", str(tar_path), "-C", str(extract_root)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            search_root = extract_root / "non-incremental" / logic
            if not search_root.exists():
                raise RuntimeError(f"Expected SMT-LIB logic path not found: {search_root}")
            rel_paths: list[str] = []
            for path in sorted(search_root.rglob("*.smt2")):
                if len(rel_paths) >= limit:
                    break
                payload = path.read_bytes()
                if not _is_unsat_bytes(payload):
                    continue
                rel = path.relative_to(search_root).as_posix()
                dest = out_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(payload)
                rel_paths.append(rel)
            return rel_paths

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        problems_dir = tmp_root / "problems"
        problems_dir.mkdir(parents=True, exist_ok=True)
        if _tar_supports_to_command():
            rel_paths = _collect_unsat_stream(tar_path, problems_dir)
        else:
            rel_paths = _collect_unsat_full(tar_path, problems_dir)
        if not rel_paths:
            raise RuntimeError(f"No :status unsat problems found for {logic}")
        rel_paths = sorted(set(rel_paths))
        items: list[dict[str, Any]] = []
        for rel in rel_paths[:limit]:
            item_id = f"{logic}/{Path(rel).with_suffix('').as_posix()}"
            items.append(
                {
                    "item_id": item_id,
                    "display_name": None,
                    "payload": {"logic": logic, "relpath": rel, "expected_status": "unsat"},
                }
            )

        built = _finalize_build(
            backend="smtlib",
            corpus_id=corpus_id,
            provenance=[
                {
                    "kind": "zenodo",
                    "record": zenodo_record,
                    "file": f"{logic}.tar.zst",
                    "sha256": tar_sha256,
                },
            ],
            build_config={
                "source": "zenodo",
                "record": zenodo_record,
                "logic": logic,
                "limit": limit,
            },
            item_id_scheme="<logic>/<relpath_without_suffix>",
            items=items,
        )
        dest = built.build_dir / "problems"
        if dest.exists():
            return built
        shutil.copytree(problems_dir, dest, dirs_exist_ok=False)
        return built


def build_tptp_local_index(
    *,
    corpus_id: str,
    tptp_root: Path,
    domains: list[str] | None = None,
    limit: int | None = None,
) -> BuiltCorpus:
    from corpus.external.tptp import list_tptp_problems

    problems = list_tptp_problems(tptp_root, domains=domains, limit=limit)
    items: list[dict[str, Any]] = []
    for p in problems:
        rel = p.path.relative_to(tptp_root).as_posix()
        items.append(
            {"item_id": p.name, "display_name": None, "payload": {"relpath": rel}}
        )
    provenance = [{"kind": "tptp", "root": str(tptp_root), "domains": domains or []}]
    build_config = {
        "source": "local_tptp",
        "tptp_root": str(tptp_root),
        "domains": domains or [],
        "limit": limit,
    }
    return _finalize_build(
        backend="tptp",
        corpus_id=corpus_id,
        provenance=provenance,
        build_config=build_config,
        item_id_scheme="<tptp_problem_name>",
        items=items,
    )


def build_coq_stdlib_index(
    *,
    corpus_id: str,
    modules: list[str],
    coqc_binary: str = "coqc",
    limit_per_module: int | None = None,
    limit_total: int | None = None,
    stdlib_root: Path | None = None,
) -> BuiltCorpus:
    from atp.coq.stdlib import extract_theorems_from_file, find_coq_stdlib_root, module_to_path

    if stdlib_root is None:
        stdlib_root = find_coq_stdlib_root(coqc_binary)
    if not stdlib_root.exists():
        raise FileNotFoundError(f"Coq stdlib root not found: {stdlib_root}")
    if not modules:
        raise ValueError("modules must be non-empty")

    items: list[dict[str, Any]] = []
    for module in modules:
        path = module_to_path(stdlib_root, module)
        names = extract_theorems_from_file(path)
        if limit_per_module is not None and limit_per_module > 0:
            names = names[:limit_per_module]
        for name in names:
            qual = f"{module}.{name}"
            items.append(
                {
                    "item_id": qual,
                    "display_name": None,
                    "payload": {"module": module, "theorem": name, "qualname": qual},
                }
            )
        if limit_total is not None and limit_total > 0 and len(items) >= limit_total:
            items = items[:limit_total]
            break

    try:
        v = subprocess.run(
            [coqc_binary, "-print-version"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        coqc_version = (v.stdout.strip() or v.stderr.strip() or "").strip()
    except FileNotFoundError:
        coqc_version = ""

    provenance = [
        {"kind": "local_install", "tool": "coqc", "version": coqc_version or None},
        {"kind": "coq_stdlib", "root": str(stdlib_root), "modules": modules},
    ]
    build_config = {
        "source": "coq_stdlib",
        "stdlib_root": str(stdlib_root),
        "modules": modules,
        "limit_per_module": limit_per_module,
        "limit_total": limit_total,
        "coqc_binary": coqc_binary,
    }
    return _finalize_build(
        backend="coq",
        corpus_id=corpus_id,
        provenance=provenance,
        build_config=build_config,
        item_id_scheme="<module>.<theorem_qualname>",
        items=items,
    )
