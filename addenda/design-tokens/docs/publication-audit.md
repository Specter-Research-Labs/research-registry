# Publication design audit

September 2026. The v4 homepage remains the visual reference. This pass consolidates
its typography, warm ground, and page geometry without making every research figure
use the same palette or flattening interactive reports into ordinary articles.

## Shared decisions

| Role | Web value | Purpose |
| --- | --- | --- |
| Ground | `#f4f1e8` | Warm paper across publication chrome |
| Ink | `#172021` | Headings, prose, and primary navigation |
| Muted ink | `#5f645e` | Captions and secondary information |
| Accents | `#a44733`, `#365b4e` | Restrained editorial emphasis and controls |
| Display and headings | Arial, Helvetica, sans-serif | Clear, large headings |
| Prose | IBM Plex Serif, Georgia, serif | Sustained reading |
| Labels and navigation | Berkeley Mono | Short identifiers, measurements, and controls |
| Outer shell | 1320px maximum, border-box | Shared page edges |
| Desktop / mobile gutters | 52px / 22px | Consistent alignment across templates |
| Emblem | 51px | Preserve the existing logo at a common size |
| Reading measure | 75ch maximum | Keep long paragraphs readable inside wide figures |

The homepage and reports retain their larger, individually composed titles. The
canonical page-title scale is for directory and document surfaces. Scientific color
encodings, simulation renders, report grids, and explicit result semantics remain
owned by their respective figures or report themes.

## Stylesheet ownership

- `site/tokens.css`: generated values from the design-token sources.
- `site/style.css`: basic site structure, utilities, and shared document plumbing.
- `site/assets/editorial.css`: directory cards and article reading styles. It no
  longer declares a competing palette, shell width, or header geometry.
- `site/assets/publication-layout.css`: common page width, gutters, emblem,
  navigation, and adapters for the existing standalone report templates. Its
  publication variables refer to canonical tokens.
- `site/assets/home.css`: homepage composition, extracted from the template so it
  can be edited without mixing layout rules with prose and diagrams. The v4
  prototype remains available as the historical design reference.
- Report and figure stylesheets: experiment-specific layouts and interactions.

Do not remove a report selector merely because it is absent from the homepage.
Archived reports and dynamically revealed controls also consume shared styles.
Use rendered checks before replacing high-specificity report adapters.

## Corrections from this pass

Cabinet prose now wraps long inline identifiers. Code blocks and wide tables scroll
within the document instead of widening the entire page. On phones, the article
comes before the long metadata and contents sidebar. Cabinet images are copied
from their source document collection and linked to stable site asset paths. Missing
source images fail the Cabinet build with the document path rather than silently
publishing broken image references.

Links to source files resolve to the repository. Inline-code labels no longer stop
Markdown links from being rewritten. Renamed Flow Lenia source references were
updated to the current paths. Cabinet landing links follow the declared landing
rather than assuming every collection has a published README.

The archived synthesis montage uses shrinkable grid columns. The standalone
interface-retuning figure stacks its columns at phone width. Homepage and document
pages reserve the same scrollbar gutter, eliminating an otherwise visible difference
in their header alignment.

## Verification and remaining work

The browser audit visits every generated or standalone HTML page in the local site
(excluding template and application source directories) at 1049px and 390px widths.
The final sweep covered 284 pages at both widths (568 checks), with no page-level
horizontal overflow. All 110 Rust library tests passed, including regressions for
web palette overrides, Cabinet image copying, and source links with code labels.
This is a layout and asset audit, not a scientific or sentence-by-sentence review of
all archived documents. Representative homepage, Writing, Addenda, research,
Cabinet, morphospace, and causal-report screenshots receive visual inspection.

The local link audit has one unresolved group: ten missing PNG figures referenced by
the draft `site/research-notes/material-memory-without-a-controller/index.md`.
The existing renderer is `dossiers/jolt-material-memory/scripts/build_article_assets.py`;
its campaign and viewer inputs are not present in this checkout. Restore those
inputs and regenerate the figures before promoting that draft. Existing videos are
not substitutes for the missing quantitative charts. No replacement data or figures
were fabricated during this design pass.
