<img src="site/assets/logo.svg" alt="SPECTER Labs" width="84" align="right">

# SPECTER Labs

Canonical research monorepo for SPECTER Labs.

## Structure

- `dossiers/` holds primary research programs.
- `addenda/` holds focused side programs, tools and various side quests.
- `site/` holds source for public web surfaces.
- `ops/` holds the `spctr` tooling for registry, release, and site work.

## Development

Use the root shell for registry and site work:

```bash
nix develop
```

Use project shells for dossier or addendum work:

```bash
cd dossiers/<name> && nix develop
cd addenda/<name> && nix develop
```

With `direnv`, run `direnv allow` once in the root or project directory. Tracked `.envrc` files only enter the flake and optionally source `.envrc.local`.

### Visual site editing

Build and browse the public site with its local editing overlay:

```bash
cargo run --manifest-path ops/spctr/Cargo.toml -- site edit
```

Open <http://127.0.0.1:4173/>, choose **Edit page**, then select or click authored text. Saving updates its canonical HTML, Markdown, TOML, or JSON source, validates the affected projection, and creates a local Jujutsu checkpoint. Derived values such as health metrics and artifact counts remain read-only. The checkpointed mode requires a clean, conflict-free working copy; use `--no-checkpoint` only when intentionally testing edits without history.

## Links

- Site: <https://specterlab.org/>
- Records: <https://releases.specterlab.org/records/>

## License

This repository is source-available under the terms described in
[`LICENSING.md`](LICENSING.md). Individual projects may carry more specific
license notes in their own directories.
