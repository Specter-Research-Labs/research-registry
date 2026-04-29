# Typst Field Manual

Typst files for Specter field manuals and papers.

The web site remains the design reference. This addendum keeps Typst documents
on the same fonts, colors, rules, and scale without editing `site/`.

## Rules

- `tokens.typ` is the only core style source for Typst.
- `specter-fm.typ` and `specter-paper.typ` must consume `tokens.typ`.
- Do not reintroduce hardcoded core fonts, colors, rules, or scale literals.
- Plots for papers use `paper-plot.mplstyle`.

## Field Manual

```typst
#import "specter-fm.typ": dossier, callout, redact, redact_block
```

- `dossier(doc_id, title, date, subtitle: none, authors: (), rev: "r0")[body]`
- `callout(title: none)[body]`
- `redact[body]`
- `redact_block(height: 10pt)`

Use `template.typ` and `example.typ` as starting points.

## Paper

```typst
#import "specter-paper.typ": author, paper
```

- `author(name, affiliation: none, email: none)`
- `paper(title, authors: (), abstract: none, subtitle: none, note: none, keywords: (), date: none)[body]`

Keep paper bodies conventional. Put personality in headings, figures, and
captions. Prefer claim-forward captions over oversized in-plot titles.

Use `paper-template.typ` and `paper-example.typ` as starting points. Use
`paper-plot.mplstyle` for external figures.

## New Draft

```bash
python3 addenda/typst-field-manual/tools/new_doc.py --title "My Note" --slug my-note
```

Common flags:

- `--authors "A. Name; B. Name"`
- `--rev r1`

Drafts are written under `addenda/typst-field-manual/drafts/`, which is
gitignored.

## Check

```bash
python3 addenda/typst-field-manual/tools/check_style_tokens.py
```

## Build

Build output goes to `$SPECTER_ARTIFACT_ROOT/typst-field-manual/pdfs/` when
that variable is set. Otherwise it goes to
`addenda/typst-field-manual/artifacts/pdfs/`.

```bash
python3 addenda/typst-field-manual/tools/build.py addenda/typst-field-manual/drafts/SL-FM-2026-001_my-note.typ
python3 addenda/typst-field-manual/tools/build.py addenda/typst-field-manual/paper-example.typ
```

Manual compile:

```bash
typst compile \
  --root addenda/typst-field-manual \
  addenda/typst-field-manual/paper-example.typ \
  addenda/typst-field-manual/artifacts/pdfs/paper-example.pdf \
  --font-path addenda/typst-field-manual/assets/fonts
```
