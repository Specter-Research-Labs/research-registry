from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path


def _die(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _slugify(raw: str) -> str:
    s = raw.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def _typst_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _typst_tuple(items: list[str]) -> str:
    if not items:
        return "()"
    inner = ", ".join(_typst_string(x) for x in items)
    return f"({inner},)"


def _read_index(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _die(f"missing index file: {path}")
    except json.JSONDecodeError as e:
        _die(f"invalid JSON in index file: {path}\n{e}")
    if not isinstance(data, dict):
        _die(f"index file must be a JSON object: {path}")
    return data


def _write_registry_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _reserve_doc_id(index_path: Path, slug: str) -> str:
    data = _read_index(index_path)
    series = data.get("series")
    registry_rel = data.get("registry")
    if not isinstance(series, str) or not series:
        _die(f"index.json is missing a valid 'series': {index_path}")
    if not isinstance(registry_rel, str) or not registry_rel:
        _die(f"index.json is missing a valid 'registry': {index_path}")

    registry_path = (index_path.parent / registry_rel).resolve()
    if not registry_path.is_file():
        _die(f"registry not found: {registry_path}")

    reg = json.loads(registry_path.read_text(encoding="utf-8"))

    docs = reg.get("docs", {})
    series_docs = docs.get(series)
    if series_docs is None:
        series_docs = {"next_counter": 1, "entries": {}}
        docs[series] = series_docs
        reg["docs"] = docs

    if slug in series_docs["entries"]:
        return series_docs["entries"][slug]

    existing_ids = set(series_docs["entries"].values())
    counter = series_docs["next_counter"]
    while True:
        doc_id = f"{series}.{counter:03d}"
        if doc_id not in existing_ids:
            break
        counter += 1

    series_docs["entries"][slug] = doc_id
    series_docs["next_counter"] = counter + 1

    _write_registry_atomic(registry_path, reg)
    return doc_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Reserve a doc id and create a new Typst draft.")
    parser.add_argument("--title", required=True, help="Document title.")
    parser.add_argument("--slug", default=None, help="Slug for the filename (default: derived from title).")
    parser.add_argument(
        "--authors",
        default="",
        help="Semicolon-separated authors (example: 'A. Name; B. Name').",
    )
    parser.add_argument("--rev", default="r0", help="Revision string (default: r0).")
    args = parser.parse_args()

    addendum_root = Path(__file__).resolve().parents[1]
    index_path = addendum_root / "index.json"
    template_path = addendum_root / "template.typ"
    drafts_dir = addendum_root / "drafts"

    if not template_path.is_file():
        _die(f"missing template: {template_path}")

    title = args.title.strip()
    if not title:
        _die("--title must be non-empty")

    slug = _slugify(args.slug if args.slug is not None else title)
    if not slug:
        _die("could not derive a non-empty slug; pass --slug")

    doc_id = _reserve_doc_id(index_path, slug)
    today = dt.date.today()

    authors = [a.strip() for a in args.authors.split(";") if a.strip()]
    authors_tuple = _typst_tuple(authors)

    out_name = f"{doc_id}_{slug}.typ"
    out_path = drafts_dir / out_name
    if out_path.exists():
        _die(f"refusing to overwrite existing file: {out_path}")

    drafts_dir.mkdir(parents=True, exist_ok=True)

    tpl = template_path.read_text(encoding="utf-8")
    rendered = (
        tpl.replace("__DOC_ID__", doc_id)
        .replace("__TITLE__", title)
        .replace("__REV__", args.rev)
        .replace("__DATE__", today.isoformat())
        .replace("__AUTHORS_TUPLE__", authors_tuple)
    )
    import_rel = Path(os.path.relpath(addendum_root / "specter-fm.typ", out_path.parent)).as_posix()
    rendered = rendered.replace('"specter-fm.typ"', _typst_string(import_rel), 1)
    out_path.write_text(rendered, encoding="utf-8")

    print(doc_id)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
