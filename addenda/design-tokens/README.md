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
