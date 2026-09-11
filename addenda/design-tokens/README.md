# SPECTER design tokens

The web publication theme is defined in `web.toml`, layered over the shared
vocabulary in `base.toml`. Print and email have separate contexts; changing the
website must not silently change a paper or email template.

```sh
spctr tokens generate --target css
spctr tokens check
```

The generated `site/tokens.css` is not edited by hand. Web palette overrides are
parsed as CSS colors so inherited translucent rules and overlays use the same ink.

The [publication design audit](docs/publication-audit.md) describes the accepted
web roles, stylesheet ownership, verification, and remaining asset work.

### Palette comparison study

`site/style-study/index.html` previews five accent palettes with the same typography, measured chart, proof schematic, and report components. Serve the site and open `/style-study/`. The palette, tinted panels, and headline option are preserved in the URL. This is a design comparison; it does not alter the canonical tokens.

## Approved publication formats

The local website now uses ultramarine (`accent-2`) and vermilion (`accent`) with an apricot `surface` from `web.toml`. The homepage retains its existing paper and ink colors and its v4 layout.

`site/assets/publication-formats.css` applies the approved formats through `data-publication`: dossier covers, report plates, and journal notes. The live Morphospace comparison has its own shared CSS and JavaScript under `site/assets/`; the style study consumes those same assets.

Research notes opt into the journal layout with `publication: journal` and an optional `publication_pdf` URL in front matter. The existing Pandoc template handles the masthead and download link.

The review and style-study directories remain local design material and are excluded from the site publish plan and sitemap discovery. The before/after viewer compares the running frozen checkpoint on port 8899 with the current local site. Publishing requires a separate explicit instruction.
