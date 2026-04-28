# Task Selection

This document defines which history-mined tasks belong in phase-0 and which do not.

## Selection Goals

- keep the corpus small enough to inspect by hand
- prefer tasks with a strong history trail
- prefer tasks that can be pinned to one commit
- prefer tasks with a single explicit acceptance command
- prefer tasks whose runtime assumptions can be recorded plainly
- prefer tasks where a maintainer-only gold resolution can be captured

## Inclusion Criteria

A task is eligible when all of the following are true:

- it comes from tinygrad git history, an issue thread, or a PR thread
- the starting repository state can be described as `repo_remote` plus `repo_commit`
- the intended change can be summarized as a bounded patch
- the success condition can be checked by one deterministic command or a tightly defined command set
- the required hardware and runtime assumptions can be recorded
- the gold resolution can be kept in the private ledger without leaking into the public row

## Exclusion Criteria

Exclude tasks that:

- depend on moving upstream branches
- require manual intervention during evaluation
- have no stable acceptance command
- are only meaningful under undocumented local machine state
- depend on GPU hardware before the CPU lane is stable
- cannot be made reproducible inside a fixed time window
- cannot be evaluated without network access

## Curation Procedure

1. Start from git history and issue or PR threads.
2. Identify isolated, legible fixes or feature changes.
3. Record the public task row without gold solution material.
4. Rewrite the task statement so it describes the file and test intent without copying the raw
   commit subject.
5. Record the maintainer-only ledger entry with gold commit, optional gold patch, stripped commit
   metadata, and leakage notes.
6. Verify the task can be exported as a model-visible prompt packet without repo provenance.
7. Verify the task can be frozen with a deterministic identifier and manifest.
8. Reject tasks that need live discovery or ambiguous success criteria.
9. Freeze the resulting corpus into the benchmark manifest.

## Preferred Task Shapes

The first corpus should favor small, technical, self-contained work:

- bug fixes with a targeted regression test
- narrow API or runtime adjustments
- small refactors that preserve behavior and are checkable by tests
- setup or packaging fixes that unblock a known command path
- tasks whose changed tests live in stable local suites such as `test/unit`, `test/null`,
  `test/backend`, or similarly small `tests/` layouts

## Mining Heuristics

When mining from git history, prefer commits that satisfy most of the following:

- non-merge commit with exactly one parent
- small patch footprint
- source files changed alongside localized tests
- one clear behavioral intent
- deterministic local acceptance command
- no vendored, generated, or formatting-dominated noise

The mined candidate set should also carry an explicit quality score and review priority so manual
curation can start from the strongest fixes first.

For the initial tinygrad corpus, prefer miner configurations that include `tinygrad/` sources and
`test/` suites while explicitly excluding `extra/`, `examples/`, `docs/`, and unsuitable test
prefixes such as `test/external/`, `test/models/`, `test/speed/`, `test/web/`, `test/amd/`,
`test/device/`, and `test/mockgpu/`.

Reject or down-rank commits that are mostly:

- merges or reverts
- docs-only or rename-only changes
- broad refactors
- flaky or network-dependent integration work
- GPU-only validation without pinned hardware
- tests under external, model-heavy, speed, web, or hardware-specific suites

## Avoid For Phase-0

- large architectural rewrites
- tasks that require multiple subsystems to change at once
- performance-only claims
- subjective-review tasks
- bespoke GPU setup or host tuning
- tasks whose evaluation requires browsing git history from inside the model workspace

## Provenance Record

Each selected task should retain enough evidence to explain why it was chosen:

- source thread or commit reference
- why the task is reproducible
- why the acceptance command is stable
- why the task belongs in the CPU correctness lane
- what gold resolution was used for comparison
- any known caveats or environment assumptions

The public benchmark should stay clean. Leakage-sensitive material belongs in the maintainer-only
ledger, keyed by `item_id`. Model-visible prompt packets should be cleaner still: no repo remote,
no commit id, no source refs, and no miner provenance metadata.
