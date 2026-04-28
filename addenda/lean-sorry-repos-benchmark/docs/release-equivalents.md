# Release Equivalents (External Benchmarks)

Maps our current release protocol to practices used by established public benchmarks.

## Observed External Patterns
- `lm-evaluation-harness` exposes bootstrap-based stderr reporting (`bootstrap_iters`) in evaluator code, so public claims can report uncertainty, not only point estimates.
  - Source: https://raw.githubusercontent.com/EleutherAI/lm-evaluation-harness/main/lm_eval/evaluator.py
- SWE-bench moved to a containerized harness for reproducible evaluations and documents Docker as the standard evaluation environment.
  - Source: https://raw.githubusercontent.com/SWE-bench/SWE-bench/main/README.md
- SWE-bench keeps some test evaluation private (for leaderboard submission) and uses a curated verified subset for reliable comparisons.
  - Source: https://raw.githubusercontent.com/SWE-bench/SWE-bench/main/README.md
  - Source: https://www.swebench.com/verified.html
- SWE-bench-Live states monthly updates while preserving frozen `lite`/`verified` splits for stable leaderboard comparisons.
  - Source: https://swe-bench-live.github.io/

## Current Mapping In This Addendum
- Deterministic split + contamination controls: implemented.
- Public-vs-full release visibility and heldout commitments: implemented.
- Run bundle checksums and explicit release checklist/failure policy: implemented.
- Pass@k protocol and multi-model suite runner: implemented.
- Infra-vs-model failure accounting and retry policy: implemented.
- Bootstrap confidence intervals on primary verification metrics: implemented.
- Per-repo replay profiles (policy overrides by repo/Lean version with strict matching mode): implemented.

## Remaining Gap To Match Top Public Leaderboards
- Repository-context replay is first-pass (not yet full-project CI replay at leaderboard scale).
- No fully pinned container image including Lean toolchain and per-repo replay runtime matrix yet.
- Large-scale distributed execution and governance workflow for public submissions is not yet implemented.

## Recommendation
- Keep current release mode as `beta` for strict executable filtering and protocol validation.
- Promote to public leaderboard mode only after adding:
  - pinned replay runtime image (including Lean/toolchain expectations),
  - larger heldout suite runs with stable model/runtime pinning,
  - distributed replay execution + submission governance policy.
