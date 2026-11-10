# Agent Guidelines for Specter Labs
This public repository holds research experiments and supporting materials for studying platonic patterns in computational systems. We aim for clarity, reproducibility, and elegant minimalism, and we want to be SOTA down to the details.

# Scope
- Dossiers and addenda are the primary unit of research work, together with the experiments, analyses, diagnostics, visualization, and tooling that directly support their research questions.
- Repo-level shared surfaces such as `site/` are allowed when they clearly support the dossiers and addenda.
- No long-lived services or infrastructure unless explicitly requested. No large, generic frameworks that obscure the core idea.

# Repository Contract
- No internal-only paths, hostnames, IPs, or secrets in tracked files. Personal overrides belong in local shell config or `.envrc.local`.
- One clear path per use-case; no second stacks for the same job.
- One source of truth per artifact: no duplicate configs or schemas that can drift.
- Explicit over magical: no hidden background machinery, side effects, fallbacks, or default behavior. Fail fast and loud with actionable errors, with no silent downshifts. If something can be None, handle it explicitly.
- Determinism and provenance: experiments must be rerunnable months later with captured config and inputs.

# Code
- Small, sharp surfaces: tiny modules with crisp responsibilities and few public knobs. Express a change through existing config before adding a knob.
- Hot paths first: if it does not improve correctness, stability, or insight, it does not belong on the critical path. Leave the code visibly simpler.
- No orphans: delete any module, CLI, script, function, variable, or import that nothing invokes or references.
- Minimal footprint: every file has a purpose, every dependency is justified, and the standard library comes first.
- No "just in case" error handling, backwards compatibility shims, or abstractions for one-time operations.
- No emojis. No commented-out code, debug transcripts, or disabled branches in tracked files; if one is genuinely needed as documentation, move it to the project's `docs/`.
- A comment must capture non-obvious rationale, an invariant, an edge case, a performance constraint, or an external-system quirk, and should answer "why" (often with `because`, `so that`, `to avoid`, or `invariant:`). If it could be mechanically generated from the next line, delete it.

# Projects
- Each Python dossier or addendum uses `uv`, `ty`, and `ruff`, has a `pyproject.toml` and an obvious entry point, and runs independently.
- Projects with real setup burden carry a local flake: `cd <project> && nix develop` or `direnv allow`.
- Durable data goes under `SPECTER_LOG_ROOT` and `SPECTER_ARTIFACT_ROOT`, or dossier-local paths if unset. Transient scratch and cache go under `SPECTER_RUNTIME_ROOT`, or repo-local `tmp/` or tool-local `TMPDIR` if unset.

# Documentation
- Be precise and actionable, with no fluff.
- Markdown documentation lives in `dossiers/*/docs/` or `addenda/*/docs/`, which feed the public website Cabinet. Exceptions: root repo files such as `README.md` and `LICENSING.md`, per-project `README.md` entry points, public sources under `site/blog/*/index.md` and `site/research-notes/*/index.md`, and maintainer docs under `ops/docs/`.
- Internal maintenance guides and operational notes go in `ops/docs/`, linked from `ops/README.md`, never in published research docs or `site/`.

# Public Prose
- Avoid abstract institutional scaffolding: no default "types of things" lists, stacked tiny sections, symmetrical "what X can/cannot prove" framing, or taxonomy-first exposition.
- Avoid strategic-vision phrases such as "the central claim," "the disciplined claim," "the program needs," "best current interpretation," "formal interface theory," and similar abstract noun clusters.
- Prefer direct research narrative: what we tried, what changed, what result surprised us, what boundary remains, and what would count as evidence.
- Use lists for real contracts, receipts, metrics, release checklists, or tables; otherwise write examples and reasoning as prose.
