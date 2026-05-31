# K Semantics Reference

Self-contained reference implementation of the
search-efficiency formalism from Chis-Ciure and Levin (2025), *Cognition All
the Way Down 2.0*:

```
K = log10(tau_blind / tau_agent)
```

Here `tau_blind` and `tau_agent` are expected cumulative costs measured in the
same problem space `P = <S, O, C, E, H>`, with operator cost function
`w: O -> R>=0`.

The goal is to make that semantics concrete, runnable, and easy to stress-test
on small domains before reusing the same structure in other research tracks.

## Docs

- `docs/k-equations.md`: paper-grounded explainer of the `P = <S, O, C, E, H>` formalism and the
  `K` equation, with short quotations and interpretation notes
- `docs/cli-and-reporting.md`: CLI schema, sweep/report formats, and the Python
  runtime surfaces for executable problem spaces

## Paper Terms

The paper extends the classical problem-space picture to a quintuple:

- `S`: state space. All task-relevant configurations the system can occupy.
- `O`: operator set. The admissible elementary moves between states.
- `C`: constraints. Forbidden or impossible state-operator combinations, plus
  any domain limits that shape the search.
- `E`: evaluation functional. What makes one state or trajectory better or worse
  for the task.
- `H`: horizon. The bounded search depth or budget over which policies are compared.
- `w`: operator cost function. The cost currency attached to each operator in `O`.

In this repo, agent and blind policies are compared inside one shared
`ProblemSpace`. The policy is allowed to change; the underlying problem
definition is not.

## Formalism Implemented

The core surfaces that paper structure directly:

- `OperatorCostSpec(default_cost, per_operator, description, state_dependent)`
- `ProblemSpace(S, operators, C, E, H, H_unit, w, w_unit, S_init, S_goal, executor)`
- `ProblemExecutor(...)`
- `ExecutablePolicy(spec, choose_operator, operator_distribution=None)`
- `PolicySpec(name, operator_semantics, description)`
- `paper_k_from_paired_trials(...)`
- `compare_policies_in_problem_space(...)`
- `exact_finite_horizon_metrics(...)`

`ProblemSpace.operators` is the local representation of the paper's `O`.
`H_unit` records what one unit of horizon means (`step`, `move`, `bit_flip`,
etc.), and `w_unit` records the cost currency when it differs from the horizon
unit. `w` can be a scalar or a structured `OperatorCostSpec`. `S_init` and
`S_goal` are optional descriptors for reporting the initial and target regions
of the space. When a `ProblemExecutor` is attached, the same object can be run
directly from Python.

When `PolicySpec` objects are supplied, `paper_k_from_paired_trials(...)`
enforces shared `operator_semantics` across agent and blind policies. That
makes the "same `P`" invariant explicit instead of leaving it as documented
convention.

## Design Rules

- Same `P` for both policies: same state space, operator family, constraints,
  evaluation functional, cost currency, and horizon.
- Same initial-state distribution (pair trials when possible).
- No silent tweaks: record horizon and cost units in outputs.

## Quickstart

```bash
cd addenda/k-semantics-reference
uv run python -m pytest
```

## Demos

### Sorting (Adjacent Swap Operators)

Compare an agentic sorting policy (insertion sort implemented as adjacent swaps)
against a blind policy (uniform random adjacent swaps until sorted, censored at `H`).

```bash
cd addenda/k-semantics-reference
uv run python -m paper_k demo sorting --n 8 --trials 200 --H 5000 --seed 0
```

### Grid Random Walk (4-Neighbor Moves)

Compare a shortest-path policy in an open grid against a blind random walk baseline.

```bash
cd addenda/k-semantics-reference
uv run python -m paper_k demo grid --size 15 --trials 200 --H 2000 --seed 0
```

### Bitstring Repair (Single-Bit Flip Operators)

Compare a greedy repair policy (flip wrong bits) against a blind policy (uniform random bit flips).

```bash
cd addenda/k-semantics-reference
uv run python -m paper_k demo bitstring --n-bits 32 --trials 200 --H 2000 --seed 0
```

### Tiny Program Synthesis (RPN Enumeration)

Search for a small arithmetic program matching I/O pairs. The "agent" tries linear forms first;
the blind baseline samples programs uniformly from the same bounded grammar.

```bash
cd addenda/k-semantics-reference
uv run python -m paper_k demo synthesis --max-len 5 --trials 200 --H 500 --seed 0
```

### Additional Toy Domains

```bash
cd addenda/k-semantics-reference
uv run python -m paper_k demo chemotaxis --size 10 --noise-sigma 0.1 --trials 200 --H 2000 --seed 0
uv run python -m paper_k demo hanoi --n-disks 4 --trials 200 --H 5000 --seed 0
uv run python -m paper_k demo grn --n-genes 8 --trials 200 --H 500 --seed 0
uv run python -m paper_k demo compositional --trials 400 --seed 0
```

### Paper Reproduction Demos (009-2025)

Section 5.2 (amoeboid chemotaxis MFPT model):

```bash
cd addenda/k-semantics-reference
uv run python -m paper_k demo paper-amoeba --distance-um 100 --dcell-min 30 --dcell-max 40 --tau-agent-s 100
```

Section 6.2 (planarian BaCl2 combinatoric model):

```bash
cd addenda/k-semantics-reference
uv run python -m paper_k demo paper-planarian --n-responsive-genes 2700 --n-required-genes 10 --neoblast-count 100000 --neoblast-cycle-hours 30 --tau-agent-days 37
```

## Using In Other Experiments

- The core API is in `core.py`.
- Treat this addendum as the "reference semantics": if you build a new K metric elsewhere,
  keep the same invariants and output schema, or explicitly bump schema/versioning.

### JSON Compute Mode

`k-semantics-reference compute --input <file.json>` accepts:

- `trials`: list of paired costs/solved flags (required)
- either:
  - legacy fields: `H`, `H_unit`, optional `w`, `w_unit`
  - or explicit `problem_space`:
    - `S`, `O`, `C`, `E`, `H`, `H_unit`, optional `w`, `w_unit`, `S_init`, `S_goal`
    - `w` may be a scalar or an object with `default`, `by_operator`,
      `description`, `state_dependent`, and `unit`
- optional `agent_policy_spec` / `blind_policy_spec` with
  `name`, `operator_semantics`, `description`

### Batch Sweep And Report

The batch tools live on the same CLI:

```bash
cd addenda/k-semantics-reference
uv run python -m paper_k sweep --input cases.jsonl --format markdown
uv run python -m paper_k report --input sweep-output.jsonl --format csv
```

`sweep` validates each case, computes the result, and renders summary rows.
`report` reads those rows, or raw compute results, and renders the same
summary table with an aggregate block for Markdown output.

### Reference Benchmark

Use the fixed benchmark suite to track runtime and output drift on the common
small domains:

```bash
cd addenda/k-semantics-reference
uv run python -m paper_k benchmark --format markdown
```

The benchmark reuses deterministic demo presets and emits the same summary
metrics as `sweep`/`report`, plus wall-clock timings per case. The test suite
also pins a golden Markdown report in
`tests/fixtures/report_markdown_golden.md` so CLI formatting changes show up as
explicit diffs.
