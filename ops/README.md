# Specter Operations and Infrastructure

`ops/` holds the production control plane and the site publish/archive entrypoints for Specter Labs.
The intent is one obvious operational path, not a grab bag of parallel wrappers.

## Production Topology

- `Cloudflare`
  - DNS, TLS, proxying, cache, and cache purge.
  - Production hostnames:
    - `specterlab.org`
    - `www.specterlab.org`
    - `dispatch.specterlab.org`
    - `releases.specterlab.org`
- `Hetzner VM`
  - public origin and stable control plane
  - runs Caddy, Postgres, and `specter-dispatch`
- `Zulip Cloud`
  - command/chat surface
  - one outgoing-webhook bot points at `https://dispatch.specterlab.org/zulip/outgoing`
- `GitHub`
  - webhooks point at `https://dispatch.specterlab.org/webhooks/github`
- compute workers
  - outbound-only execution
  - poll `dispatch.specterlab.org`
  - execute canonical site publishes
- `Hetzner Storage Box`
  - backup/archive target only
  - not part of the request path

## Public Surfaces

- `specterlab.org`
  - canonical current site
  - served from `/srv/www/site/current`
- `dispatch.specterlab.org`
  - control-plane app
  - reverse-proxied to `127.0.0.1:3001`
- `releases.specterlab.org`
  - immutable public release archive
  - served from `/srv/www/releases`

Current Caddy wiring lives in `ops/spctr/dispatch/deploy/Caddyfile`.

## Request Path

- Cloudflare terminates TLS, proxies the request, and applies cache rules.
- Caddy routes by hostname:
  - `specterlab.org` and `www.specterlab.org` -> static site root
  - `dispatch.specterlab.org` -> local reverse proxy to dispatch
  - `releases.specterlab.org` -> static release archive root
- dispatch handles only control-plane traffic; public content is file-served directly by Caddy.

## Dispatch

`specter-dispatch` is the stable control plane.

It owns:

- Zulip command ingress
- GitHub webhook ingress
- runner registration, claim, heartbeat, complete, and fail
- Postgres-backed job state
- Zulip follow-up posts and GitHub webhook notifications

Current Zulip stream model:

- `dispatch` is the live operations stream for command traffic, PR events, CI notifications, and other action-oriented bot output.
- `ledger` is reserved for durable summaries such as rollups, release notes, and other record-style updates.
- GitHub webhook topics are repo-scoped so they group cleanly:
  - `github / pr / <repo> / #<number>`
  - `github / issue / <repo> / #<number>`
  - `github / ci / <repo> / <workflow>`
  - `github / release / <repo> / <tag>`

Primary runtime routes:

- `GET /health`
- `POST /zulip/outgoing`
- `POST /webhooks/github`
- `POST /runner/register`
- `POST /runner/claim`
- `POST /runner/heartbeat`
- `POST /runner/complete`
- `POST /runner/fail`

The dispatch runtime and deploy assets live under `ops/spctr/dispatch/`.
The canonical site publish and release portal logic live under `ops/spctr/`.

## Compute Workers

They:
- poll dispatch over HTTPS
- run only validated `publish site` jobs
- have no inbound access
- can go offline without taking the site or bot offline

The current runner env surface is documented in `ops/spctr/dispatch/runner/runner.env.template`.

## Site and Release Publishing

There are two public publishing surfaces:

- canonical current site at `specterlab.org`
- immutable archives at `releases.specterlab.org`

The publish path preserves that split:

- current/canonical surface stays on the main site or active origin
- immutable archived bundle is copied into the releases host

The site publish entrypoint is `spctr site publish`.
The release portal renderer is `spctr site portal`.
The stable direct-tree sync for the records corpus is `spctr site push-records --source <records-bureau>`.
Project-specific archive publishes are also first-class `spctr` commands:

- `spctr site publish-lenia-compendium --release-id <id> [--output <dir>] -- ...`
- `spctr site publish-wonton-dashboard [--release-id <id>] [--site-data-root <dir>]`
- `spctr release publish-typst-pdf --input <file.typ> --release-id <id> [--overwrite-release]`

The release host is intentionally archive-first:

- the main site is the canonical "current" surface
- `releases.specterlab.org` stores immutable published bundles
- `spctr site publish` refreshes the release portal after each archive update

Current release host namespaces:

- `records/`
- `site/`
- `typst-field-manual/`
- `lenia-swarm/compendium/`
- `wonton-soup/site-dashboard/`

## Project Proof Paths

For dossier/addendum work, the default operational path is the project contract in `spctr.toml`.

Use:

- `spctr exec run --project <slug> <check|smoke|build|publish>`
- `spctr release gate <slug>`
- `spctr ci sync --project <slug> --write`

If a project does not declare a lane, treat that as intentional. Add the narrowest honest lane to
`spctr.toml` first.

## CI and Deploys

- `.github/workflows/repo-mirror.yml`
  - syncs the tracked repo to the Hetzner mirror on every push to `main`
  - keeps the latest dossier/addenda/site/ops code available on the VM
  - does not activate any public surface by itself
- `.github/workflows/dispatch.yml`
  - validates and deploys the dispatch app to the Hetzner repo mirror
- `.github/workflows/pages.yml`
  - builds the static site
  - publishes `/srv/www/site/releases/<git-sha>`
  - switches `/srv/www/site/current`
  - archives the exact built snapshot under the releases host
  - purges Cloudflare cache

Manual and chat-driven publishes use the same repo-owned CLI entrypoints as CI so there is one deploy path per surface.
The full repo mirror is broader than any one surface, but it is intentionally passive: syncing code to the VM does not imply build, publish, or execution.

## Backups

Hot state stays on the VM local SSD:

- Postgres primary data
- dispatch app
- current site
- current releases tree

The Storage Box is for off-VM backups only:

- Postgres dumps
- release snapshots
- selected site snapshots

The current sync entrypoint is `ops/spctr/dispatch/deploy/sync_storage_box.sh`.
