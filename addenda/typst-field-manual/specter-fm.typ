#import "tokens.typ": tokens

#let redact(body) = box(
  fill: tokens.colors.redaction,
  inset: (
    x: tokens.layout.redaction_inline.inset_x,
    y: tokens.layout.redaction_inline.inset_y,
  ),
  radius: tokens.layout.redaction_inline.radius,
)[#hide(body)]

#let redact_block(height: 10pt) = rect(
  width: 100%,
  height: height,
  fill: tokens.colors.redaction,
  radius: tokens.layout.redaction_block_radius,
)

#let callout(title: none, body) = [
  #align(right)[
    #move(dx: tokens.layout.callout.offset_dx)[
      #block(
        width: tokens.layout.callout.width,
        inset: tokens.layout.callout.inset,
        fill: tokens.colors.panel,
        stroke: (left: tokens.rules.thick + tokens.colors.rule_strong),
        radius: tokens.layout.callout.radius,
      )[
        #set text(
          font: tokens.fonts.heading,
          size: tokens.type_scale.callout,
          fill: tokens.colors.ink,
        )
        #set par(leading: tokens.leading.callout)
        #if title != none [
          #text(weight: "bold")[#title]
          #v(tokens.layout.callout.title_gap)
        ]
        #body
      ]
    ]
  ]
]

#let _title_page(meta) = [
  #set text(font: tokens.fonts.heading)
  #rect(width: 100%, height: tokens.rules.top_bar, fill: tokens.colors.ink)
  #v(10mm)

  #text(size: tokens.type_scale.label, tracking: tokens.tracking.label)[SPECTER LABS]
  #v(8mm)

  #set text(font: tokens.fonts.body)
  #set par(justify: false)
  #text(size: tokens.type_scale.title, weight: "bold")[#meta.title]

  #if meta.subtitle != none [
    #v(4mm)
    #text(size: tokens.type_scale.subtitle, weight: "regular", fill: tokens.colors.muted)[#meta.subtitle]
  ]

  #v(10mm)
  #rect(width: 100%, height: tokens.rules.thick, fill: tokens.colors.rule_strong)
  #v(6mm)

  #set text(size: tokens.type_scale.meta)
  #grid(
    columns: (tokens.layout.meta_grid.label_col, 1fr),
    gutter: tokens.layout.meta_grid.gutter,
    [
      #text(weight: "bold", fill: tokens.colors.muted)[DOC ID]
    ],
    [
      #text(weight: "bold")[#meta.doc_id]
    ],
    [
      #text(weight: "bold", fill: tokens.colors.muted)[REV]
    ],
    [
      #meta.rev
    ],
    [
      #text(weight: "bold", fill: tokens.colors.muted)[DATE]
    ],
    [
      #meta.date
    ],
    [
      #text(weight: "bold", fill: tokens.colors.muted)[AUTHORS]
    ],
    [
      #if meta.authors.len() == 0 [none] else [#meta.authors.join(", ")]
    ],
  )

]

#let _header(meta) = context [
  #set text(font: tokens.fonts.heading, size: tokens.type_scale.running)
  #grid(
    columns: (1fr, auto),
    gutter: tokens.layout.header_grid_gutter,
    [#text(weight: "bold")[SPECTER LABS]],
    [#(meta.doc_id + " · " + meta.rev + " · " + meta.date)],
  )
  #line(length: 100%, stroke: tokens.rules.thin + tokens.colors.rule)
]

#let _footer(meta) = context [
  #line(length: 100%, stroke: tokens.rules.thin + tokens.colors.rule)
  #set text(font: tokens.fonts.heading, size: tokens.type_scale.running)
  #grid(
    columns: (1fr, auto),
    gutter: tokens.layout.footer_grid_gutter,
    [#meta.doc_id],
    [
      #counter(page).display() / #counter(page).final().at(0)
    ],
  )
]

#let dossier(
  doc_id,
  title,
  date,
  subtitle: none,
  authors: (),
  rev: "r0",
  body,
) = {
  let meta = (
    doc_id: doc_id,
    title: title,
    subtitle: subtitle,
    authors: authors,
    rev: rev,
    date: date,
  )

  set document(title: title, author: authors.join(", "))

  set text(
    font: tokens.fonts.body,
    size: tokens.type_scale.body,
    fill: tokens.colors.ink,
  )
  set par(leading: tokens.leading.body, justify: true)
  set page(margin: tokens.layout.page_margin, header: none, footer: none)

  set heading(numbering: "1.")
  show heading.where(level: 1): it => [
    #v(1.1em)
    #line(length: 100%, stroke: tokens.rules.thick + tokens.colors.rule_strong)
    #v(0.35em)
    #set text(font: tokens.fonts.heading, size: tokens.type_scale.heading_1, weight: "bold")
    #it
    #v(0.35em)
    #line(length: 100%, stroke: tokens.rules.thin + tokens.colors.rule)
    #v(0.4em)
  ]
  show heading.where(level: 2): it => [
    #v(0.9em)
    #set text(font: tokens.fonts.heading, size: tokens.type_scale.heading_2, weight: "bold")
    #it
    #v(0.25em)
    #line(length: 100%, stroke: tokens.rules.thin + tokens.colors.rule)
    #v(0.3em)
  ]
  show heading.where(level: 3): it => [
    #v(0.6em)
    #set text(font: tokens.fonts.heading, size: tokens.type_scale.heading_3, weight: "bold")
    #it
    #v(0.2em)
  ]

  show raw: set text(font: tokens.fonts.mono, size: tokens.type_scale.mono)
  set raw(tab-size: 2)
  show raw.where(block: true): it => block(
    inset: tokens.layout.raw_block.inset,
    radius: tokens.layout.raw_block.radius,
    fill: tokens.colors.paper,
    stroke: (left: tokens.rules.thick + tokens.colors.rule_strong),
  )[#it]

  show link: set text(fill: tokens.colors.muted)

  show quote.where(block: true): it => block(
    inset: (left: 12pt, y: 4pt),
    stroke: (left: tokens.rules.thick + tokens.colors.rule),
  )[
    #set text(style: "italic", fill: tokens.colors.muted)
    #it.body
  ]

  _title_page(meta)
  pagebreak()

  set page(header: _header(meta), footer: _footer(meta))

  body
}
