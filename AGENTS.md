# Agent Guidelines for Specter Labs
Keep this repository clean; it contains internal research experiments and supporting materials for studying platonic patterns in computational systems.

# Vision and Scope
We build research-grade systems and experiments that expose, measure, and explain platonic patterns in computational systems. We aim for clarity, reproducibility, and elegant minimalism. We want to be SOTA down to the details.

## Supported Scope
- Dossiers and addenda are the primary unit of research work.
- Experiments, analyses, and tooling that directly support the research questions.
- Diagnostics, visualization, and analysis when they improve understanding or reproducibility.
- Repo-level shared surfaces (for example, `site/`, shared assets) are allowed when they clearly support the dossiers/addenda and do not create a second stack.

## Non-Goals
- No second stacks for the same use-case.
- No long-lived services or infrastructure unless explicitly requested.
- No large, generic frameworks that obscure the core idea.

# Repository Contract
- No internal-only paths, hostnames, IPs, or secrets in tracked files.
- One clear path per use-case; avoid parallel stacks for the same job.
- Explicit over magical: no hidden background machinery or side effects.
- Fail fast, fail loud: guardrails with actionable errors, no silent downshifts.
- One source of truth per artifact: no duplicate configs or schemas that can drift.

# Principles
- Small, sharp surfaces: tiny modules with crisp responsibilities and few public knobs.
- Hot paths first: if it does not improve correctness, stability, or insight, it does not belong on the critical path.
- Determinism and provenance: experiments must be rerunnable months later with captured config and inputs.
- Documentation that guides: precise and actionable, no fluff.
- No orphans (code + scripts): if a module/CLI/script is not imported, invoked, or referenced by an entry point, delete it; if a function is not called, delete it; if a variable is not used, delete it.
- Minimal footprint: every file must have a purpose; every dependency must be justified; prefer the standard library; remove unused imports, functions, and variables.
- Explicit over implicit: no hidden fallbacks, no magic default behavior; fail loudly on errors; if something can be None, handle it explicitly.

# Change Rubric
- Intent: Does this improve correctness, reproducibility, or insight?
- Uniqueness: Are we creating a second way to do something? If yes, why?
- Surface: Did we add a new public knob? Could it be expressed via existing config?
- Invariants: Are determinism and key invariants enforced or clarified?
- Repro: Is configuration and provenance captured to rerun months later?
- Elegance: Is the code visibly simpler afterward?

# Ops & Workflow
- Operational workflow (JJ workspaces, logs/artifacts routing, vault/docs/Obsidian handling) lives in the $specter-ops skill. Invoke it when needed.
- Keep the tracked root bootstrap generic. Personal homelab overrides belong in local shell config or `.envrc.local`, not in tracked repo files.
- Prefer the project-local flake in each dossier/addendum that has real setup burden: `cd <project> && nix develop` or `direnv allow`.
- Use SPECTER_LOG_ROOT and SPECTER_ARTIFACT_ROOT for durable data on remote volumes; if unset, fall back to dossier-local paths.
- Use SPECTER_RUNTIME_ROOT for transient dossier/addendum scratch and cache paths on external volumes; if unset, fall back to repo-local `tmp/` paths or tool-local `TMPDIR`.
- `synthetic-bureau` lives as a private sibling repo, usually `../synthetic-bureau/`, or at `SPECTER_SYNTHETIC_BUREAU_ROOT` if set.
  - It is for assistant-generated reports, research notes, and analysis written to disk only when explicitly requested by a human.
  - Treat it as ephemeral, local-only output.
  - `synthetic-bureau/` is exempt from the "no orphans" rule.
- `records-bureau` lives as a private sibling repo, usually `../records-bureau/`, or at `SPECTER_RECORDS_BUREAU_ROOT` if set.

## Clean Experiments
Each Python dossier or addenda directory should have:
- Use `uv`, `ty`, and `ruff`
- A `pyproject.toml` for dependencies
- A clear entry point (how to run is obvious)
- Self-contained (runs independently)
- Optional `docs/` for experiment-specific technical documentation

# What NOT to Do
- Do not create documentation markdown files outside `dossiers/*/docs/` or `addenda/*/docs/`.
  - Exceptions: repo root `README.md`, per-dossier/per-addendum `README.md` entry points, and public research-note sources under `site/research-notes/*/index.md`.
- For public prose and research notes, avoid abstract institutional scaffolding.
  - Do not default to "types of things" lists, stacked tiny sections, symmetrical
    "what X can/cannot prove" framing, or taxonomy-first exposition.
  - Avoid strategic-vision phrases such as "the central claim," "the disciplined
    claim," "the program needs," "best current interpretation," "formal interface
    theory," and similar abstract noun clusters.
  - Prefer direct research narrative: what we tried, what changed, what result
    surprised us, what boundary remains, and what would count as evidence.
  - Use lists for real contracts, receipts, metrics, release checklists, or tables;
    otherwise write examples and reasoning as prose.
- Do not add "just in case" error handling
- Do not add backwards compatibility shims
- Do not create abstractions for one-time operations
- Do not write useless comments or use emojis anywhere in the code
- Do not add comments that narrate the code. If the comment could be mechanically generated from the next line, delete it.
- Do not leave commented-out code, debug transcripts, or disabled branches in tracked files. Delete them; if they are genuinely needed as documentation, move them into the dossier/addendum `docs/` instead.
- Any new comment must justify itself by capturing at least one: non-obvious rationale, invariant, edge case, performance constraint, or an external-system quirk. Prefer wording that answers "why" (often using `because`, `so that`, `to avoid`, or `invariant:`).
