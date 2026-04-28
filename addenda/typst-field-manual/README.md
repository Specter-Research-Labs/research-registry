# Typst PDF Templates (Addendum)
Typst library and template workflow for Specter PDFs.

Exposes two surfaces from a shared token source: a field-manual surface for internal documentation, and a paper surface for public-facing preprints and article-style PDFs.

## Style Alignment Policy
- `site/` is the canonical design reference for Specter Labs web styling.
- This addendum harmonizes PDF semantics against that reference without editing `site/`.
- `tokens.typ` is the single style source for Typst internals in this addendum.
- `specter-fm.typ` and `specter-paper.typ` must consume `tokens.typ` and should not reintroduce hardcoded core style literals.

## What Lives Here
- `specter-fm.typ`: reusable field-manual components and document styling surface.
- `specter-paper.typ`: reusable paper/preprint styling surface.
- `paper-plot.mplstyle`: shared Matplotlib style for external figures that should match the paper surface.
- `tokens.typ`: shared style tokens for fonts, colors, rules, scale, and layout constants.
- `template.typ`: field-manual scaffold.
- `paper-template.typ`: paper/preprint scaffold.
- `example.typ`: field-manual example document.
- `paper-example.typ`: paper/preprint example document.
- `tools/new_doc.py`: reserves doc IDs and writes new draft files.
- `tools/build.py`: compiles `.typ` to PDF with vendored fonts and artifact routing.
- `tools/check_style_tokens.py`: checks that both style surfaces use tokenized styling.
- `index.json`: doc-ID allocation state (`prefix`, `width`, per-year counters).

## Field-Manual Surface (`specter-fm.typ`)
Import the library:

```typst
#import "specter-fm.typ": dossier, callout, redact, redact_block
```

Available components:
- `dossier(doc_id, title, date, subtitle: none, authors: (), rev: "r0")[body]`
  - Primary document wrapper.
  - Applies page geometry, typography, heading hierarchy, code-block styling, title page, and running header/footer.
- `callout(title: none)[body]`
  - Right-margin callout block for short notes or warnings.
- `redact[body]`
  - Inline visual redaction that preserves layout.
- `redact_block(height: 10pt)`
  - Block-level visual redaction bar.

## Paper Surface (`specter-paper.typ`)
Import the library:

```typst
#import "specter-paper.typ": author, paper
```

Available components:
- `author(name, affiliation: none, email: none)`
  - Small metadata helper for the paper surface.
- `paper(title, authors: (), abstract: none, subtitle: none, note: none, keywords: (), date: none)[body]`
  - Paper/preprint wrapper with a restrained title block, author grid, abstract panel, and calm section styling.
  - Intended for public-facing PDFs that should read like normal papers rather than internal manuals.

Paper style guidance:
- Keep the body conventional and put most of the personality in the title block, headings, and figure system.
- External plots should match the paper typography and use a restrained, consistent palette.
- The shared Matplotlib surface lives in `paper-plot.mplstyle`.
- Prefer claim-forward captions over oversized in-plot titles.

## Create A New Document (Reserves A Doc ID)
This updates `addenda/typst-field-manual/index.json` and creates a new draft in `addenda/typst-field-manual/drafts/` (gitignored).

```bash
python3 addenda/typst-field-manual/tools/new_doc.py --title "My Note" --slug my-note
```

Common optional flags:
- `--authors "A. Name; B. Name"`
- `--rev r1`

## Check Style Token Consistency
Run this check before committing style changes in this addendum:

```bash
python3 addenda/typst-field-manual/tools/check_style_tokens.py
```

## Build A PDF
Build output:
- If `SPECTER_ARTIFACT_ROOT` is set: `$SPECTER_ARTIFACT_ROOT/typst-field-manual/pdfs/`
- Else: `addenda/typst-field-manual/artifacts/pdfs/` (gitignored)

```bash
python3 addenda/typst-field-manual/tools/build.py addenda/typst-field-manual/drafts/SL-FM-2026-001_my-note.typ
```

Example paper build:

```bash
python3 addenda/typst-field-manual/tools/build.py addenda/typst-field-manual/paper-example.typ
```

## Manual Compile
```bash
typst compile \
  --root addenda/typst-field-manual \
  addenda/typst-field-manual/paper-example.typ \
  addenda/typst-field-manual/artifacts/pdfs/paper-example.pdf \
  --font-path addenda/typst-field-manual/assets/fonts
```
