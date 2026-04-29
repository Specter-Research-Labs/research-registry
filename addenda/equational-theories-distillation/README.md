# Equational Theories Distillation

Builds a sub-10 KB plain-text cheatsheet for SAIR Stage 1.

The Stage 1 task is fixed: decide whether Equation 1 implies Equation 2 over
all magmas, offline, with no tools. This addendum uses the 4694-law implication
graph to find compact rules, then writes the small evaluator text that actually
ships.

For the method, read `docs/approach.md`. For the detailed counts and residual
cases, read `docs/public-benchmark-notes.md`. The frozen submission text is
`docs/cheatsheet-v0.txt`.

## Check

Runtime data goes under `../../tmp/equational-theories-distillation/`, unless
`SPECTER_RUNTIME_ROOT` is set.

```bash
cd addenda/equational-theories-distillation
nix develop
uv run ruff check .
uv run ty check .
uv run python -m pytest
```

`direnv allow` enters the same shell and runs `uv sync`.

## Fetch

```bash
uv run python -m equational_theories_distillation fetch
```

This writes `normal.jsonl`, `hard.jsonl`, `equations.txt`, `graph.json`, and a
source manifest under `sources/`.

## Analyze

```bash
uv run python -m equational_theories_distillation analyze
```

The command writes `analysis/public-analysis.json` and prints a short summary.

Current headline:

- public labels match `graph.json`: `1200/1200`
- theorem-backed TRUE coverage: `433/574`
- fixed 10-table 2-element FALSE battery: `467/626`
- exact 2-element source-row semantics: `669/1200` public decisions
- explicit false witnesses after 3-element and optional SAT passes: `605/626`
- shipped constructive candidate: `1179/1200`
- size-5 SAT still leaves `6` unknown pairs at the current solver depth

Optional residual SAT passes:

```bash
uv run python -m equational_theories_distillation analyze \
  --size4-sat-timeout-ms 1000 \
  --size5-sat-timeout-ms 1000
```

## Draft The Sheet

```bash
uv run python -m equational_theories_distillation draft-cheatsheet
```

The draft command writes `analysis/cheatsheet-v0.txt`. If
`analysis/public-analysis.json` exists, it reuses that analysis so the sheet and
metrics stay aligned.
