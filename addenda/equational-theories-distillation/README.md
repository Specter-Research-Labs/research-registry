# Equational Theories Distillation

Workbench for distilling a Stage 1 cheatsheet for the SAIR Equational
Theories benchmark.

Features:
- fetches pinned public assets and the full implication graph
- maps public problems into the fixed 4694-law universe
- turns graph statuses into an offline teacher surface
- measures compact decision procedures against that surface
- freezes a plain-text no-tools submission artifact

## Scope

- No Lean dependency.
- No notebooks or hidden caches.
- Minimal Python stack; `z3-solver` is used only for the optional size-4 / size-5 residual search.
- Default runtime data goes to `../../tmp/equational-theories-distillation/` unless
  `SPECTER_RUNTIME_ROOT` is set.

## Docs

The durable docs are:

- `docs/approach.md`: how the method works, what ships, and what stays analysis-only
- `docs/public-benchmark-notes.md`: detailed metrics, residual structure, and benchmark notes
- `docs/cheatsheet-v0.txt`: the frozen plain-text submission artifact

## Install / Check

```bash
cd addenda/equational-theories-distillation
nix develop
uv run ruff check .
uv run ty check
uv run python -m pytest
```

If you use direnv, `direnv allow` from `addenda/equational-theories-distillation/` is equivalent.
The shell auto-runs `uv sync`.

## Fetch Sources

```bash
cd addenda/equational-theories-distillation
uv run python -m equational_theories_distillation fetch
```

This writes:

- `sources/normal.jsonl`
- `sources/hard.jsonl`
- `sources/equations.txt`
- `sources/graph.json`
- `sources/sources.manifest.json`

## Run Analysis

```bash
cd addenda/equational-theories-distillation
uv run python -m equational_theories_distillation analyze
```

The analysis command writes `analysis/public-analysis.json` and prints a short summary.

Current headline results:

- public labels match `graph.json` exactly: `1200/1200`
- theorem-backed TRUE coverage: collapse `243/574`, mixed-self-reference-with-singleton `188/574`,
  one-hole context `6/574`
- combined theorem-backed TRUE coverage: `433/574`
- 10-table 2-element pair evaluator: `467/626` false problems, `13` more than the old 6-table
  battery
- exact 2-element source-row semantics: `2407/4694` source laws are exact, giving `669/1200`
  exact public decisions and explaining `126` of the remaining `141` theorem-uncovered public
  true cases
- FALSE coverage: `454/626` from a `2`-element battery, `589/626` after the `3`-element and
  optional `4`-element SAT passes, `605/626` with the optional size-`5` SAT pass
- combined public decision surface from theorem-backed TRUE + exact source rows + explicit false
  witnesses: `1164/1200`, leaving `15` public true and `21` public false cases unresolved
- an explicit source-triggered kernel catalog explains `13/15` of that true residual, giving a
  constructive candidate surface of `1177/1200`
- two explicit commutativity repairs close the last `2/2` true residual cases, pushing the
  constructive candidate surface to `1179/1200`
- size-`4` residual SAT currently reports `20 sat / 17 unsat` at `1000 ms`
- size-`5` residual SAT reports `7 sat / 3 unsat / 7 unknown`
- canonicalizing those `7` size-`5` unknown pairs to the smallest mutually implied laws turns
  `1` of them into `unsat`, leaving `6` still unknown at the current solver depth

Optional explicit size-4 SAT search on residual false cases:

```bash
cd addenda/equational-theories-distillation
uv run python -m equational_theories_distillation analyze --size4-sat-timeout-ms 1000
```

This is intentionally opt-in because it is much slower than the default analysis pass.

Optional size-5 pass on the size-4 residual:

```bash
cd addenda/equational-theories-distillation
uv run python -m equational_theories_distillation analyze \
  --size4-sat-timeout-ms 1000 \
  --size5-sat-timeout-ms 1000
```

## Draft A Cheatsheet

```bash
cd addenda/equational-theories-distillation
uv run python -m equational_theories_distillation draft-cheatsheet
```

The draft command writes `analysis/cheatsheet-v0.txt`. If
`analysis/public-analysis.json` already exists, the draft reuses it so the sheet stays aligned
with the latest size-`4` / size-`5` residual search.
