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
