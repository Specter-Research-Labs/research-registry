# Lean Tactic Representation

Research experiment for representing tactics as typed objects rather than tactic
strings.

The executable slice has two independent parts:

- a pure Lean compiler lowers a sequential `exact` / `apply` / `constructor`
  source program into a nested program and predicts its goal transitions;
- a `MetaM` interpreter executes that program, records its obligation tree and
  residual builders, and asks `Lean.Kernel.check` to verify the completed proof.

The Python boundary runs both sides and requires their shared execution
projection to agree. It deliberately does not define downstream graph schemas or
artifact bundles; those contracts remain owned by their consuming projects.

## Run

```bash
cd addenda/lean-tactic-representation
nix develop
lake build

uv run python cli.py compile scenarios/source/constructor.json
uv run python cli.py compile-run scenarios/source/constructor.json
uv run python cli.py compile-run scenarios/source/apply.json
```

`compile-run` succeeds only when source validation, compiler prediction,
independent Lean execution, and kernel checking all pass.

## Verify

```bash
lake build
uv run ruff check .
uv run ty check .
uv run python -m pytest
```

The broader research target remains in
[the calculus specification](docs/general-algebraic-tactic-calculus-spec.md).
