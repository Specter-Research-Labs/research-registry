from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ARTIFACT_ENV = "SPECTER_ARTIFACT_ROOT"
ADDENDUM_NAME = "typst-field-manual"


def _die(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _artifact_root(fallback: Path) -> Path:
    raw = os.environ.get(ARTIFACT_ENV)
    if raw is None:
        return fallback
    trimmed = raw.strip()
    if not trimmed:
        _die(f"{ARTIFACT_ENV} is set but empty.")
    return Path(os.path.expanduser(trimmed)) / ADDENDUM_NAME


def _extract_title(md: str, slug: str) -> tuple[str, str]:
    """Return (title, body_without_first_heading).

    Pulls title from the first ``# `` heading.  If none, derives from
    the filename slug.
    """
    lines = md.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^#\s+(.+)$", line)
        if m:
            title = m.group(1).strip()
            rest = "\n".join(lines[i + 1 :]).lstrip("\n")
            return title, rest
    return slug.replace("-", " ").title(), md


def _extract_date(filename: str) -> str:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", filename)
    if m:
        return m.group(1)
    return date.today().isoformat()


def _slug_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    return re.sub(r"^\d{4}-\d{2}-\d{2}-?", "", stem)


def _md_to_typst(md_text: str) -> str:
    result = subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "typst"],
        input=md_text,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _escape_typst_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _build_typ_source(title: str, date_str: str, slug: str, body_typst: str) -> str:
    doc_id = f"SL-GEN-{slug}"
    t = _escape_typst_string(title)
    return (
        '#import "specter-fm.typ": dossier\n'
        '#import "tokens.typ": tokens\n'
        "\n"
        "#let horizontalrule = line(length: 100%, stroke: tokens.rules.thin + tokens.colors.rule)\n"
        "\n"
        "#show: dossier.with(\n"
        f'  "{_escape_typst_string(doc_id)}",\n'
        f'  "{t}",\n'
        f'  "{_escape_typst_string(date_str)}",\n'
        '  authors: ("Specter Labs",),\n'
        ")\n"
        "\n"
        "#set heading(numbering: none)\n"
        "\n"
        f"{body_typst}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert markdown files to PDF via the Specter field-manual template.",
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="Markdown files to convert.")
    args = parser.parse_args()

    for tool in ("pandoc", "typst"):
        if shutil.which(tool) is None:
            _die(f"{tool} not found in PATH.")

    addendum_root = Path(__file__).resolve().parents[1]
    fonts_dir = addendum_root / "assets" / "fonts"
    if not fonts_dir.is_dir():
        _die(f"missing fonts dir: {fonts_dir}")

    fallback_root = addendum_root / "artifacts"
    out_root = _artifact_root(fallback_root)
    out_dir = out_root / "pdfs"
    out_dir.mkdir(parents=True, exist_ok=True)

    for md_path in args.inputs:
        md_path = md_path.resolve()
        if not md_path.is_file():
            print(f"skip: {md_path} (not found)", file=sys.stderr)
            continue

        md_text = md_path.read_text()
        slug = _slug_from_filename(md_path.name)
        date_str = _extract_date(md_path.name)
        title, body_md = _extract_title(md_text, slug)
        body_typst = _md_to_typst(body_md)
        typ_source = _build_typ_source(title, date_str, slug, body_typst)

        tmp_typ = addendum_root / f"_md2pdf_{slug}.typ"
        out_pdf = out_dir / f"{md_path.stem}.pdf"
        try:
            tmp_typ.write_text(typ_source)
            subprocess.run(
                [
                    shutil.which("typst"),
                    "compile",
                    "--root",
                    str(addendum_root),
                    str(tmp_typ),
                    str(out_pdf),
                    "--font-path",
                    str(fonts_dir),
                ],
                check=True,
            )
            print(out_pdf)
        finally:
            tmp_typ.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
