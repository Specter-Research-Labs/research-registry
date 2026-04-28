# ADR-001: Taxonomy Columns Exist, Assignment Deferred

## Status

Accepted

## Context

Compendium schema includes taxonomy columns, but production indexing currently has no deterministic taxonomy assignment pass.

## Decision

Keep taxonomy storage fields in schema now, while writing null taxonomy values during indexing until a deterministic assignment method is implemented and validated.

## Rationale

- Preserves forward-compatible schema for downstream consumers.
- Avoids shipping unstable taxonomy heuristics as if they were canonical.
- Allows ecology/studio surfaces to consume taxonomy fields when available without schema churn.

## Consequences

- Consumers must treat taxonomy fields as optional.
- Documentation must clearly separate current implementation from planned taxonomy pipeline.
- Future taxonomy rollout requires method/version provenance fields and reproducible assignment protocol.
