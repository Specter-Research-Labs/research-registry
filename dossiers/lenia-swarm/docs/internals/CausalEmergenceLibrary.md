---
publish: false
---

# Causal-emergence library

The causal-emergence reading library is kept in the repository under
`site/dossiers/lenia-swarm/causal-emergence/reports/<report-id>/` and is not
published to the website. Each directory contains the report, `about.html`, and
its publication receipt; migrated pages also retain the upstream receipt. Source
release identifiers and hashes remain in the catalog and receipts.

To rebuild from the frozen sources or migrate an authenticated release bundle,
run `spctr site stage-lenia-causal-reports --input-root INPUT --output OUTPUT`.
Install `OUTPUT/reports/` in `site/dossiers/lenia-swarm/causal-emergence/reports/`
and place `OUTPUT/manifest.json` inside that directory. The site build checks
every report, context page, and receipt against the manifest.
Shared report geometry is in `site/assets/publication-layout.css`; the report
exporter reads `site/templates/publication-header.html` for the navigation.
The library's assets in `site/assets/causal-emergence/`,
`site/assets/causal-emergence.css`, and `site/assets/writing-causal-response.svg`
are excluded from publishing with the library.

`python3 dossiers/lenia-swarm/ops/build_publication_covers.py` draws the causal
cover from the report's stored age-response values.

The editorial selection and per-record disposition are recorded in
`site/dossiers/lenia-swarm/causal-emergence/editorial-review.json`; selection does
not delete experimental evidence or imply every supporting page is publication-ready.
