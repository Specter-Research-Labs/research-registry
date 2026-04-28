# Benchmark Card

## Identity

- Addendum: `addenda/tinygrad-benchmarks`
- Phase: `0`
- Primary target: `tinygrad`
- Evaluation style: history-mined patch tasks against pinned commits
- Public artifact: deterministic benchmark index and split manifest
- Private artifact: maintainer-only gold ledger

## Core Question

Can a model take a tinygrad task mined from real project history, work only from the public index,
and produce a patch that both passes the acceptance check and matches the historical resolution
closely enough to matter?

## Benchmark Unit

Each row should represent one concrete task instance with:

- repository identity
- pinned starting commit
- target file or files
- task statement synthesized for benchmark use
- acceptance command
- runtime and hardware assumptions
- public-vs-private provenance classification

The public row should not include gold patch material, raw commit subjects, or issue and PR hooks
that make the historical answer easy to recover.

## Protocol

1. Mine candidate tasks from tinygrad history and issue threads.
2. Write the public index and the maintainer-only private ledger.
3. Render model-visible prompt packets from the public index.
4. Freeze deterministic splits from the public index.
5. Run candidate patches in a sealed working tree.
6. Strip `.git` from the evaluation workspace so the model cannot browse commit history locally.
7. Treat the model process as offline for clean-run claims.
8. Score attempts.
9. Compare results against the private gold ledger.

The miner should rank accepted candidates by quality score before any `max_candidates` truncation so
human review starts from the most plausible benchmark tasks.

## Lane Definition

### CPU Correctness Lane

The initial lane is CPU-only correctness:

- pass/fail is based on the pinned acceptance command
- accepted mined tests must come from benchmark-suitable local suites
- history mining should be path-scoped to `tinygrad/` plus small `test/` suites, with explicit
  exclusions for external, model-heavy, speed, web, and hardware-specific paths
- no throughput ranking
- no GPU dependency
- no live upstream fetches
- no hidden fallbacks to mutable task sources

### Deferred Lanes

The following are out of scope for phase-0:

- GPU correctness
- GPU perf
- host-specific tuning
- multi-machine orchestration
- cross-repo generalization before the tinygrad lane is solid

## Artifact Contract

The benchmark should produce reproducible artifacts for each run:

- frozen split manifest
- attempt records
- run summary
- host and runtime metadata
- gold comparison report when the private ledger is available

If two runs use the same public index, seed, manifest, and environment contract, they should
compare cleanly without manual reconciliation.

Prompt packets are a separate artifact surface. They exist so a model can receive the task,
validation command, and target paths without seeing repo remote URLs, commit ids, or miner
provenance metadata.

## Gold Comparison

`compare-gold` is not a second benchmark. It is the retrospective check that asks whether the patch
found by the model lines up with the historical solution in the private ledger.

The comparison should distinguish at least:

- exact or near-exact historical resolution
- functionally correct but different resolution
- correct pass without historical similarity
- failed or incomplete patch

The current scaffold reports both touched-path overlap and normalized changed-line overlap so
“historically close” patches are measurable instead of being collapsed into a single non-exact bin.

The current scaffold writes:

- `attempts.jsonl`
- `summary.json`
- `run_manifest.json`
- `host.json`
- `compare_report.jsonl`
- `compare_summary.json`

That lets the benchmark answer both “did it work?” and “did it find the real answer?”

## Success Criteria

Phase-0 is successful if the addendum can:

- mine a credible set of tinygrad tasks from history
- keep gold provenance private while exposing a clean public benchmark
- run in a sealed evaluation tree without `.git`
- reject any workflow that depends on live network access
- compare model patches against real historical resolutions
