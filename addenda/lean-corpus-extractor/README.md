# lean-corpus-extractor
Lean-native corpus extraction for building deterministic `items.jsonl` inputs for `dossiers/wonton-soup` corpus artifacts.

Imports requested modules at runtime without depending on Mathlib at build time. Must run under a project environment providing the required `.olean` files (e.g., via `lake env ...`).

## Environment

Enter the local project shell from `addenda/lean-corpus-extractor/`:

```bash
nix develop
```

If you use direnv, `direnv allow` is equivalent. The shell auto-runs `lake update`.

## Output format
JSONL, one object per line:

- `item_id`: Lean identifier-safe stable id (no dots)
- `display_name`: original fully qualified name (with dots)
- `payload.statement`: a Lean declaration template containing `{name}`
  - `wonton-soup` replaces `{name}` with a unique name per run/seed
- `payload.source`: minimal provenance for the extracted decl

Example:

```json
{"item_id":"Nat_x2eadd_x5fcomm","display_name":"Nat.add_comm","payload":{"statement":"theorem {name} : forall (a b : Nat), a + b = b + a := by\n  sorry","source":{"kind":"lean_env","module":"Mathlib.Data.Nat.Basic","qualname":"Nat.add_comm"}}}
```

## Usage (Mathlib)
1) Build this tool:

```bash
cd addenda/lean-corpus-extractor
lake build
```

2) Run it under a Lean project that has Mathlib available (for `wonton-soup`, that’s the local
`lean_project/` created by `setup_lean.py`):

```bash
cd dossiers/wonton-soup/lean_project
lake env ../../addenda/lean-corpus-extractor/.lake/build/bin/lean_corpus_extract \
  --import Mathlib.Data.Nat.Basic \
  --module-prefix Mathlib.Data.Nat.Basic \
  --limit 100 \
  --out /tmp/mathlib_items.jsonl
```

If you omit `--import`, the extractor defaults to `Mathlib` (slow; loads all of mathlib).

## Targeted extraction by theorem name

Use repeatable `--name` flags to extract only specific declarations:

```bash
cd dossiers/wonton-soup/lean_project
lake env ../../addenda/lean-corpus-extractor/.lake/build/bin/lean_corpus_extract \
  --import Mathlib \
  --name ContinuousLinearMap.isOpenMap \
  --name QuotientGroup.quotientKerEquivRange \
  --out /tmp/named_items.jsonl
```

If a requested name is missing in the current Lean environment, the extractor keeps running and
prints one stderr line per missing name.
