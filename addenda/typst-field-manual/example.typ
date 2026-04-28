#import "specter-fm.typ": dossier, callout, redact

#dossier(
  "SL-FM-2026-000",
  "A Field Manual Style Note",
  "2026-02-09",
  subtitle: "Design study for Specter Labs PDFs",
  authors: ("Specter Labs",),
  rev: "r0",
)[
  = Intent

  This template borrows the layout grammar of field manuals: hard rules, tight rhythm,
  strong sectioning, and a calm page.

  = Inline Redaction

  Inline redaction preserves layout: the phrase is #redact[blacked out] but spacing remains.

  = Sections

  == A Second-Level Heading

  Prefer short paragraphs and explicit claims. Use the outside margin for small notes.

  === A Third-Level Heading

  If you need code, it gets a restrained treatment:

  ```text
  doc_id := SL-FM-YYYY-NNN
  rev    := r0, r1, r2...
  ```
]
