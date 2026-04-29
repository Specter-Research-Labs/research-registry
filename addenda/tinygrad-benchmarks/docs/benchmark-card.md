# Benchmark Card

## Identity

- Addendum: `addenda/tinygrad-benchmarks`
- Phase: `0`
- Target repo: `tinygrad`
- Task type: history-mined patch tasks against pinned commits
- Public artifact: benchmark index plus split manifest
- Private artifact: maintainer-only gold ledger

## Question

Can a model solve small real tinygrad tasks from the public index, using only
the task statement, target paths, and pinned acceptance command?

## Row

Each row records:

- repo identity,
- pinned starting commit,
- target files,
- benchmark task statement,
- acceptance command,
- runtime and hardware assumptions,
- public/private provenance class.

Public rows omit gold patches, raw commit subjects, issue hooks, PR hooks, and
anything that makes the historical answer easy to recover.

## Protocol

1. Mine candidate tasks from tinygrad history and issue threads.
2. Write the public index and private gold ledger.
3. Render model prompt packets from the public index.
4. Freeze deterministic splits.
5. Run candidate patches in a sealed working tree.
6. Strip `.git` from the evaluation tree.
7. Treat the model process as offline.
8. Score attempts.
9. Compare attempts against the private gold ledger when available.

The miner ranks accepted candidates by quality before truncation, so manual
review starts with the strongest tasks.

## Phase 0

The first lane is CPU correctness:

- pass/fail comes from the pinned acceptance command,
- mined tests come from local benchmark-suitable suites,
- history mining is scoped to `tinygrad/` and small `test/` suites,
- external, model-heavy, speed, web, GPU, and hardware-specific paths are
  excluded,
- no throughput ranking,
- no live upstream fetches,
- no hidden fallback to mutable task sources.

Deferred:

- GPU correctness,
- GPU performance,
- host tuning,
- multi-machine orchestration,
- cross-repo generalization.

## Run Artifacts

Each run writes:

- frozen split manifest,
- attempt records,
- run summary,
- host and runtime metadata,
- gold comparison report when the private ledger is available.

Runs with the same public index, seed, manifest, and environment contract are
meant to compare without manual repair.

Prompt packets are separate from the evaluator index. They carry the task,
validation command, and target paths, but not repo URLs, commit ids, or miner
metadata.

## Gold Comparison

`compare-gold` is a retrospective check, not a second benchmark. It asks whether
the model patch resembles the historical solution.

It distinguishes:

- exact or near-exact historical resolution,
- functionally correct but different resolution,
- passing patch with little historical overlap,
- failed or incomplete patch.

The comparison reports touched-path overlap and normalized changed-line overlap.

## Success

Phase 0 succeeds if this addendum can:

- mine credible tinygrad tasks from history,
- keep gold provenance private,
- expose a clean public benchmark,
- run without `.git` in the evaluation tree,
- reject live-network evaluation paths,
- compare model patches against real historical fixes.
