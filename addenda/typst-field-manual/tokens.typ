#let tokens = (
  fonts: (
    body: "IBM Plex Serif",
    display: "IBM Plex Sans",
    heading: "IBM Plex Sans",
    mono: "IBM Plex Mono",
  ),

  colors: (
    ink: luma(8%),
    muted: luma(35%),
    panel: luma(96%),
    paper: luma(97%),
    redaction: black,
    rule: luma(74%),
    rule_strong: luma(56%),
  ),

  rules: (
    thick: 1.4pt,
    thin: 0.6pt,
    top_bar: 2.4pt,
  ),

  type_scale: (
    body: 10pt,
    callout: 8.5pt,
    heading_1: 16pt,
    heading_2: 12pt,
    heading_3: 11pt,
    label: 11pt,
    meta: 10pt,
    mono: 9pt,
    running: 9pt,
    subtitle: 14pt,
    title: 26pt,
  ),

  tracking: (
    label: 0.18em,
  ),

  leading: (
    body: 1.32em,
    callout: 1.25em,
  ),

  layout: (
    callout: (
      inset: 7pt,
      offset_dx: 18mm,
      radius: 1.5pt,
      title_gap: 4pt,
      width: 60mm,
    ),

    footer_grid_gutter: 10pt,
    header_grid_gutter: 10pt,
    meta_grid: (
      gutter: 10pt,
      label_col: 22mm,
    ),

    page_margin: (
      bottom: 18mm,
      left: 18mm,
      right: 34mm,
      top: 16mm,
    ),

    raw_block: (
      inset: 8pt,
      radius: 1.5pt,
    ),

    redaction_block_radius: 1pt,
    redaction_inline: (
      inset_x: 1.5pt,
      inset_y: 1pt,
      radius: 1pt,
    ),
  ),

  paper_colors: (
    accent: rgb("#1f4555"),
    ink: luma(10%),
    muted: luma(38%),
    panel: luma(97.5%),
    rule: luma(78%),
  ),

  paper_rules: (
    accent: 1.2pt,
    thin: 0.6pt,
  ),

  paper_type_scale: (
    author_meta: 8.8pt,
    author_name: 10.5pt,
    body: 10.5pt,
    caption: 9pt,
    heading_1: 14pt,
    heading_2: 11.5pt,
    heading_3: 10.5pt,
    keyword: 8.8pt,
    kicker: 8.5pt,
    mono: 9pt,
    running: 8.5pt,
    subtitle: 11.5pt,
    title: 22pt,
  ),

  paper_leading: (
    body: 1.34em,
  ),

  paper_layout: (
    abstract_gap: 7mm,
    abstract_inset: 10pt,
    abstract_label_gap: 4pt,
    abstract_radius: 1.5pt,
    author_columns_gap: 12pt,
    author_meta_gap: 2pt,
    author_rows_gap: 10pt,
    authors_gap: 7mm,
    footer_gap: 8pt,
    heading_1_above: 1.7em,
    heading_1_below: 0.45em,
    heading_2_above: 1.15em,
    heading_2_below: 0.3em,
    heading_3_above: 0.9em,
    heading_3_below: 0.2em,
    keywords_gap: 5pt,
    kicker_gap: 3.5mm,
    page_margin: (
      bottom: 20mm,
      left: 23mm,
      right: 23mm,
      top: 20mm,
    ),

    raw_block: (
      inset: 8pt,
      radius: 1.5pt,
    ),

    subtitle_gap: 3mm,
    title_top_gap: 6mm,
  ),
)
