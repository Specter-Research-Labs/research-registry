# ADR-002: Exact Compendium Schema Version Enforcement

## Status

Accepted

## Context

Read commands and UI surfaces depend on fixed table/column layouts. Silent compatibility fallback risks incorrect analysis.

## Decision

Use explicit compendium schema versioning with exact-match enforcement for commands that read structured compendium data.

## Rationale

- Fail-loud behavior prevents silent misreads.
- Migration steps make evolution explicit and reviewable.
- Deterministic reproducibility is easier when schema shape is version-locked.

## Consequences

- Schema bumps require migration code and doc updates.
- Older DBs must be migrated before some commands run.
- Newer DBs are rejected by older binaries instead of partial reads.
