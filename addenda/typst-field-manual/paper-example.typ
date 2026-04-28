#import "specter-paper.typ": author, paper
#import "tokens.typ": tokens

#paper(
  title: "Mechanism-First Notes on a Minimal Sorting System",
  subtitle: "A restrained Specter preprint surface for papers and research reports",
  note: "SPECTER LABS PREPRINT",
  authors: (
    author("Ludwig Pouey", affiliation: "Specter Labs"),
    author("Philip Rhor", affiliation: "Specter Labs"),
  ),
  date: "March 2026",
  keywords: ("minimal models", "distributed systems", "reproducibility"),
  abstract: [
    This paper surface is designed for public-facing research documents that need to read like
    conventional papers while retaining a restrained Specter identity. The layout keeps the page
    calm, moves most of the visual character into headings and the title block, and leaves the body
    text close to a standard preprint. The intended use is for internal preprints, workshop papers,
    and article-style PDFs that should not inherit the field-manual chrome.
  ],
)[
  = Introduction

  The goal is to keep the paper recognizable without making the template itself the most visible
  object on the page. The body remains serif and publication-safe; the Specter signature lives in a
  quiet title treatment, sans section heads, and a restrained accent color.

  = Layout Principles

  == Publishability First

  Avoid running metadata, dossier identifiers, or decorative bars that read like internal tooling.
  A paper should survive venue review even if the accent color and title kicker are removed.

  == Personality In The Figure System

  The figure style should do more of the aesthetic work than the page chrome. Prefer direct labels,
  limited palettes, and captions that state the claim before giving the procedural details.

  #figure(
    rect(
      width: 100%,
      height: 46mm,
      fill: tokens.paper_colors.panel,
      stroke: tokens.paper_rules.thin + tokens.paper_colors.rule,
      radius: 2pt,
    ),
    caption: [Placeholder figure. In the real paper surface, the external plots should share the same restrained typography and palette.],
  )

  = Reporting Surface

  #table(
    columns: (1fr, 1fr),
    table.header([Surface], [Intent]),
    [Title block], [Carry the lab signature without looking like internal documentation.],
    [Headings], [Stay clear and compact so the text still reads like a normal paper.],
    [Abstract], [Create one strong entry point for the claim, scope, and framing.],
  )

  = Conclusion

  This template is the paper counterpart to the field manual. It should absorb the strongest parts
  of Specter's personality without importing the operational tone of internal PDFs.
]
