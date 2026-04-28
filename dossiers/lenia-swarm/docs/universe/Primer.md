# Primer

## Purpose

Gives the minimum conceptual frame needed to read lenia-swarm docs without jumping into implementation details.

## System Scope

`lenia-swarm` is a Flow Lenia experiment system for discovering and indexing persistent patterns across parameter space.

The system has three coupled concerns:

- physics: how states evolve each step,
- morphology: how we summarize form and behavior,
- ecology: how populations and niches are compared across runs.

## Core Objects

- state field `A`: the simulated multi-channel lattice state.
- genotype: parameter payload controlling kernels and global parameters.
- phenotype: observed behavior summarized into metrics.
- creature record: an indexed row tying genotype, phenotype, and provenance.

## Invariant View

The research loop is:

1. run deterministic simulations from explicit configs,
2. extract metrics and derived morphometrics,
3. index into a versioned compendium,
4. analyze structure (taxonomy/ecology) offline.

## Where to Go Next

- For model mechanics: `Physics.md`.
- For descriptive language: `Morphology.md` and `Glossary.md`.
- For grouping concepts: `Taxonomy.md` and `Ecology.md`.
- For executable details: move to `../contracts/`.
