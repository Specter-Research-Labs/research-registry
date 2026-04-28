# Studio Compendium Internals

## Scope

How LeniaStudio consumes compendium data surfaces and what assumptions matter for compatibility.

## Source Surfaces

- Studio views consume indexed creature rows and metadata exposed from compendium schema.
- CLI indexing remains the writer of record for compendium content.

## Contract Dependencies

Studio compendium behavior depends on:

- exact schema version matching current CLI expectation,
- presence of core tables (`compendium_meta`, `runs`, `campaigns`, `creatures`, `exports`, `results`),
- stable column names for taxonomy and morphometrics fields.

## Practical Implications

- Schema additions must be migration-backed and version-gated before Studio consumes them.
- New derived fields should carry method/version tags so UI logic can branch explicitly.
- Null taxonomy fields are valid current-state data and must not be treated as ingest corruption.

## Change Discipline

When changing compendium-facing columns:

1. update schema + migration path,
2. update CLI validations,
3. update Studio readers and views,
4. update docs in `contracts/CompendiumSchema.md` and this file.
