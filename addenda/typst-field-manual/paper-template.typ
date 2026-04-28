#import "specter-paper.typ": author, paper
#import "tokens.typ": tokens

#paper(
  title: "__TITLE__",
  subtitle: none,
  note: "SPECTER LABS PREPRINT",
  authors: (
    author("__AUTHOR_NAME__", affiliation: "__AFFILIATION__"),
  ),
  date: none,
  keywords: ("keyword one", "keyword two"),
  abstract: [
    State the problem, the intervention, and the main result in concrete terms.
    Keep the abstract tight and falsifiable.
  ],
)[
  = Introduction

  Frame the problem, the minimal claim, and why the chosen measurement resolves a real ambiguity.

  = Method

  Specify the system, the key variables, and the exact semantics that matter for reproduction.

  = Results

  Report the main effect with the smallest amount of text needed to anchor the figure or table.

  #figure(
    rect(
      width: 100%,
      height: 42mm,
      fill: tokens.paper_colors.panel,
      stroke: tokens.paper_rules.thin + tokens.paper_colors.rule,
      radius: 2pt,
    ),
    caption: [Placeholder figure. Replace with a real plot whose typography matches the paper surface.],
  )

  = Discussion

  Separate mechanism, scope, and limitations. Do not let interpretation outrun the evidence.

  = Reproducibility

  Give the smallest runnable path to regenerate the main artifacts.
]
