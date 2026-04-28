#import "tokens.typ": tokens

#let author(name, affiliation: none, email: none) = (
  name: name,
  affiliation: affiliation,
  email: email,
)

#let _author_columns(count) = if count <= 1 {
  (1fr,)
} else if count == 2 {
  (1fr, 1fr)
} else {
  (1fr, 1fr, 1fr)
}

#let _author_card(person) = align(left)[
  #text(
    font: tokens.fonts.display,
    size: tokens.paper_type_scale.author_name,
    weight: "bold",
  )[
    #person.name
  ]

  #if person.affiliation != none [
    #v(tokens.paper_layout.author_meta_gap)
    #text(
      size: tokens.paper_type_scale.author_meta,
      fill: tokens.paper_colors.muted,
    )[
      #person.affiliation
    ]
  ]

  #if person.email != none [
    #v(tokens.paper_layout.author_meta_gap)
    #text(
      size: tokens.paper_type_scale.author_meta,
      fill: tokens.paper_colors.muted,
    )[
      #person.email
    ]
  ]
]

#let _authors_block(authors, date) = [
  #if authors.len() > 0 [
    #grid(
      columns: _author_columns(authors.len()),
      column-gutter: tokens.paper_layout.author_columns_gap,
      row-gutter: tokens.paper_layout.author_rows_gap,
      ..authors.map(person => _author_card(person)),
    )
  ]

  #if date != none [
    #if authors.len() > 0 [
      #v(tokens.paper_layout.author_rows_gap)
    ]
    #text(
      font: tokens.fonts.display,
      size: tokens.paper_type_scale.author_meta,
      fill: tokens.paper_colors.muted,
    )[
      #date
    ]
  ]
]

#let _abstract_block(abstract, keywords) = block(
  inset: tokens.paper_layout.abstract_inset,
  fill: tokens.paper_colors.panel,
  stroke: (left: tokens.paper_rules.accent + tokens.paper_colors.accent),
  radius: tokens.paper_layout.abstract_radius,
)[
  #text(
    font: tokens.fonts.display,
    size: tokens.paper_type_scale.kicker,
    tracking: tokens.tracking.label,
    fill: tokens.paper_colors.accent,
  )[ABSTRACT]

  #v(tokens.paper_layout.abstract_label_gap)
  #abstract

  #if keywords.len() > 0 [
    #v(tokens.paper_layout.keywords_gap)
    #text(
      size: tokens.paper_type_scale.keyword,
      fill: tokens.paper_colors.muted,
    )[
      #text(weight: "bold", fill: tokens.paper_colors.ink)[Keywords.]
      #h(0.5em)
      #keywords.join(", ")
    ]
  ]
]

#let _title_block(meta) = [
  #line(length: 100%, stroke: tokens.paper_rules.accent + tokens.paper_colors.accent)
  #v(tokens.paper_layout.title_top_gap)

  #block(width: 100%)[
    #set par(justify: false)
    #set text(hyphenate: false)

    #if meta.note != none [
      #text(
        font: tokens.fonts.display,
        size: tokens.paper_type_scale.kicker,
        tracking: tokens.tracking.label,
        fill: tokens.paper_colors.accent,
      )[
        #meta.note
      ]
      #v(tokens.paper_layout.kicker_gap)
    ]

    #text(
      font: tokens.fonts.body,
      size: tokens.paper_type_scale.title,
      weight: "bold",
    )[
      #meta.title
    ]

    #if meta.subtitle != none [
      #v(tokens.paper_layout.subtitle_gap)
      #text(
        size: tokens.paper_type_scale.subtitle,
        style: "italic",
        fill: tokens.paper_colors.muted,
      )[
        #meta.subtitle
      ]
    ]
  ]

  #v(tokens.paper_layout.authors_gap)
  #_authors_block(meta.authors, meta.date)

  #if meta.abstract != none [
    #v(tokens.paper_layout.abstract_gap)
    #_abstract_block(meta.abstract, meta.keywords)
  ]
]

#let _footer() = context [
  #v(tokens.paper_layout.footer_gap)
  #align(center)[
    #text(
      font: tokens.fonts.display,
      size: tokens.paper_type_scale.running,
      fill: tokens.paper_colors.muted,
    )[
      #counter(page).display()
    ]
  ]
]

#let paper(
  body,
  title: none,
  authors: (),
  abstract: none,
  subtitle: none,
  note: none,
  keywords: (),
  date: none,
) = {
  let meta = (
    title: title,
    authors: authors,
    abstract: abstract,
    subtitle: subtitle,
    note: note,
    keywords: keywords,
    date: date,
  )

  set document(
    title: title,
    author: authors.map(person => person.name).join(", "),
  )

  set text(
    font: tokens.fonts.body,
    size: tokens.paper_type_scale.body,
    fill: tokens.paper_colors.ink,
  )
  set par(leading: tokens.paper_leading.body, justify: true)
  set page(
    margin: tokens.paper_layout.page_margin,
    header: none,
    footer: _footer(),
  )

  show link: set text(fill: tokens.paper_colors.accent)

  set heading(numbering: "1.")
  show heading.where(level: 1): it => [
    #v(tokens.paper_layout.heading_1_above)
    #set text(font: tokens.fonts.display, size: tokens.paper_type_scale.heading_1, weight: "bold")
    #it
    #v(tokens.paper_layout.heading_1_below)
  ]
  show heading.where(level: 2): it => [
    #v(tokens.paper_layout.heading_2_above)
    #set text(font: tokens.fonts.display, size: tokens.paper_type_scale.heading_2, weight: "bold")
    #it
    #v(tokens.paper_layout.heading_2_below)
  ]
  show heading.where(level: 3): it => [
    #v(tokens.paper_layout.heading_3_above)
    #set text(font: tokens.fonts.display, size: tokens.paper_type_scale.heading_3, weight: "bold")
    #it
    #v(tokens.paper_layout.heading_3_below)
  ]

  show raw: set text(font: tokens.fonts.mono, size: tokens.paper_type_scale.mono)
  set raw(tab-size: 2)
  show raw.where(block: true): it => block(
    inset: tokens.paper_layout.raw_block.inset,
    fill: tokens.paper_colors.panel,
    stroke: (left: tokens.paper_rules.accent + tokens.paper_colors.accent),
    radius: tokens.paper_layout.raw_block.radius,
  )[it]

  _title_block(meta)
  body
}
