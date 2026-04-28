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

## Links

- Site: <https://specterlab.org/>
- Records: <https://releases.specterlab.org/records/>

## License

This repository is source-available under the terms described in
[`LICENSING.md`](LICENSING.md). Individual projects may carry more specific
license notes in their own directories.
