# SPECTER Labs

Canonical research monorepo for SPECTER Labs.

## Development

This repository is Apple-first and clone-friendly by default.

- Use `nix develop` at the repo root for generic repo work.
- Use `cd dossiers/<name> && nix develop` or `cd addenda/<name> && nix develop` for project-specific environments.
- If you use `direnv`, run `direnv allow` once in the root or project directory. Project shells auto-bootstrap light setup on entry:
  - Python projects run `uv sync`
  - Rust projects run `cargo fetch --locked`
  - Swift projects run `swift package resolve`
  - Lean-only projects run `lake update`
- Keep personal homelab and `SPECTER_*` path overrides in local shell config or `.envrc.local`, not in tracked repo files.
- Private sibling repos are optional. If you have access, bootstrap them with `./ops/bootstrap_private_siblings.sh`.

## Structure

- `dossiers/` - main-line research projects
- `addenda/` - side-quest research projects
- `site/` - lab website
- `ops/` - tooling, deploy glue, and release/archive surfaces

Canonical paper and archive links live under `https://releases.specterlab.org/records/`.

## Release Workflow

Build and validate release metadata with `spctr`:

- `cargo build --manifest-path ops/spctr/Cargo.toml`
- `./ops/spctr/target/debug/spctr release validate`
- `./ops/spctr/target/debug/spctr release plan <slug>`
- `./ops/spctr/target/debug/spctr release bundle <slug> <surface> --release-id <id>`
- `./ops/spctr/target/debug/spctr release package <slug> <surface> --output tmp/packages`
- `./ops/spctr/target/debug/spctr site push-records --source ../records-bureau`
- `./ops/spctr/target/debug/spctr release audit`
