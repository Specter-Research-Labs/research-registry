#import "specter-fm.typ": dossier, callout, redact

#dossier(
  "__DOC_ID__",
  "__TITLE__",
  "__DATE__",
  subtitle: none,
  authors: __AUTHORS_TUPLE__,
  rev: "__REV__",
)[
  = Summary

  One paragraph that states the claim and the punchline. If you need inline masking:
  #redact[like this].

  #callout(title: "Style")[
    Keep the surface sharp. Prefer explicit sections and short invariants.
  ]

  = Notes

  == A Code Snippet

  ```python
  def invariant(x: int) -> int:
      return x + 1
  ```
]
