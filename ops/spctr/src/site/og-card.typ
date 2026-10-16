#let title = sys.inputs.title
#let kicker = sys.inputs.kicker
#let ink = luma(8%)
#let muted = luma(35%)
#let rule = luma(74%)
#let size = if title.len() > 90 { 22pt } else if title.len() > 60 { 26pt } else { 31pt }

#set page(width: 600pt, height: 315pt, margin: (x: 36pt, top: 34pt, bottom: 26pt), fill: luma(97%))
#set text(font: "IBM Plex Sans", fill: ink)

#place(top + left, dx: -36pt, dy: -34pt, rect(width: 600pt, height: 3pt, fill: ink, stroke: none))

#grid(
  rows: (auto, 1fr, auto),
  [
    #text(size: 9pt, weight: "bold", tracking: 0.18em, fill: muted, upper(kicker))
    #v(-4pt)
    #line(length: 100%, stroke: 0.6pt + rule)
  ],
  align(horizon, par(leading: 0.42em, text(size: size, weight: "bold", title))),
  [
    #line(length: 100%, stroke: 1.4pt + ink)
    #v(-2pt)
    #grid(
      columns: (auto, 1fr, auto),
      column-gutter: 8pt,
      align: horizon,
      image("/assets/logo-black.svg", height: 18pt),
      text(size: 9.5pt, weight: "bold", tracking: 0.18em, "SPECTER LABS"),
      text(font: "IBM Plex Mono", size: 9pt, fill: muted, "specterlab.org"),
    )
  ],
)
