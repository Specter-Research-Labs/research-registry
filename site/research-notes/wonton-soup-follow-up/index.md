---
title: "How proof search responds to blocked tactics"
release: "draft"
provenance: "assistant-drafted"
source_id: "D-002"
toc: true
---

# How proof search responds to blocked tactics

*Historical April analysis draft. Its cohorts and controls differ from the later [controlled tactic-blocking study](/research-notes/2026-06-10-taking-away-one-move-revealed-proof-alternatives/). Preserve these numbers as an earlier analysis, not as an additional estimate of the June result. The [inert-control investigation](/research-notes/2026-04-02-wonton-controls-exposed-a-reproducibility-problem/) limits causal interpretation of the DeepSeek comparisons.*

This draft separates provider differences, blocked-tactic outcomes and scheduling interventions. A changed search trace can arise from the intended intervention or from variation between inference calls; both must be measured.

Three figures anchor the result:

![Paired-panel intervention taxonomy](../../assets/blog/wonton-soup-follow-up/fig16-followup-taxonomy.png)

![Provider-specific intervention outcomes on the paired panel](../../assets/blog/wonton-soup-follow-up/fig17-followup-provider-splits.png)

![Basin multistability versus blind-relative gain](../../assets/blog/wonton-soup-follow-up/fig18-followup-basins.png)

## What the April run database records

The April database snapshot records **17,400 wild-type runs** and **19,700 intervention comparisons** with valid GED scores as of April 2026.

### Provider-level comparison

| Provider | Wild runs | Solve rate | Mean K | Intervention GED norm | Multimodal fraction |
|---|---:|---:|---:|---:|
| reprover | 9,296 | 0.32 | -0.10 | 0.224 | 0.01 |
| deepseek | 3,874 | 0.30 | -0.08 | 0.442 | 0.06 |

reprover and deepseek have similar solve rates (32% vs 30%) and similar negative mean K—neither beats the blind baseline on average. But intervention GED norm is 2x higher for deepseek (0.442 vs 0.224): DeepSeek runs differ more in this structural measurement. Without successful paired inert controls, that difference cannot be attributed entirely to the intervention. The reported hash mismatch rate is low for both (4–5%). Hash identity and search-graph distance describe different objects and should not be treated as interchangeable evidence of preserved structure.

Multiple recorded proof-structure clusters are rare in this analysis. reprover has >1 structure on 1% of theorems, deepseek on 6%. The dominant structure captures 43% of seeds for reprover, 32% for deepseek.

### Tactic-role visibility (distributed MCTS sweep)

1,354 intervention runs across 771 wild-type solves record which tactic blocks the sampled prover could survive within its budget:

| Blocked tactic | Runs | Solve rate |
|---|---:|---:|
| `left` | 43 | 1.00 |
| `push_neg` | 40 | 1.00 |
| `contrapose!` | 20 | 1.00 |
| `positivity` | 20 | 1.00 |
| `intro` | 20 | 1.00 |
| `tauto` | 60 | 0.67 |
| `constructor` | 40 | 0.50 |
| `exact` | 349 | 0.11 |
| `cases'` | 116 | 0.17 |
| `simpa` | 82 | 0.24 |
| `simp` | 201 | 0.00 |
| `rw` | 96 | 0.00 |
| `ext` | 90 | 0.00 |
| `cases` | 77 | 0.00 |
| `induction` | 25 | 0.00 |

Blocking `simp` or `rw` left no successful runs in this April sample. This result depends on the sampled theorems, providers, and search budgets; it does not establish that either tactic is mathematically necessary. Every recorded run with `left`, `push_neg`, or `contrapose!` blocked still solved. Blocking `exact` stopped most searches, but 11% succeeded through `assumption` or direct term discharge.

The paired intervention panel is not simply "damage search" versus "help search." Some perturbations expose an alternate successful route, some block the obvious route and collapse, and some shift tactic usage without changing terminal success. If two perturbations solve the same theorem through different tactic roles, do not collapse them into the same outcome class too early.

## Provider Differences

The cross-provider notes mostly keep us honest. Early comparison runs looked like high structural convergence, but much of that came from trivial one-step proofs—the convergence was expected and uninformative.

The divergent multi-step examples are the ones worth keeping. One provider leans on library lemmas where another performs explicit construction; tactic overlap can be low even when both systems reach the theorem. Differences between providers become visible when we record the tactics and intermediate goals as well as the solved/failed outcome.

## Sampling Broke One Failure Mode

The tactic-generation experiments exposed a simple failure mode in beam search. Repetitive beams often generated many text variants of the same broken tactic family.

Temperature sampling changed the candidate set:

| Metric | Beam Search | Sampling 1x | Sampling 3x |
|---|---:|---:|---:|
| Correct base tactic found | 4/6 | 5/6 | 5/6 |
| Average unique base tactics | 2.7 | 4.2 | 4.7 |

Diversity itself is an intervention variable. When a prover is trapped in repeated malformed tactic families, sampling can expose alternate base tactics that beam search misses.

DeepSeek-style generation gave a different tradeoff. It had better tactic quality on a small panel, much slower inference, and a larger runtime footprint. That makes it attractive as a fallback or diagnostic provider, not obviously as the main MCTS provider.

## Distributed MCTS Sweep

The distributed MCTS sweep adds a wrinkle. Wild-type solves stayed stable across scenarios, while intervention counts changed under block and delay settings.

Seed0 summary:

| Scenario | Wild solved | Interventions solved | Total interventions |
|---|---:|---:|---:|
| baseline | 24/40 | 29/85 | 85 |
| damage-block-f0.1 | 24/40 | 29/85 | 85 |
| damage-block-f0.3 | 24/40 | 30/88 | 88 |
| damage-block-f0.5 | 24/40 | 32/93 | 93 |
| adapt-block-f0.1 | 24/40 | 29/85 | 85 |
| adapt-block-f0.3 | 24/40 | 29/85 | 85 |
| adapt-block-f0.5 | 24/40 | 29/83 | 83 |
| damage-delay-p0.1 | 24/40 | 29/85 | 85 |
| damage-delay-p0.3 | 24/40 | 29/83 | 83 |

The damage-block-f0.5 condition added eight interventions relative to baseline. The extra interventions concentrated in four theorems, and three of the extras solved, which looks like a search-path shift rather than a broad improvement.

## Where The Signal Is

Blocking tactics matters when the prover reroutes. Separate terminal outcome from tactic-role structure: which tactic families become necessary or brittle, where one provider reroutes while another collapses, and whether extra interventions produce solved routes or only churn.

The later controlled study is the preferred account of this question. Its null result for proof diversity versus recovery is important: many observed proof variants need not supply an alternative when their shared tactic is blocked.

For the broader framing on cognition across heterogeneous systems, see Robert Chis-Ciure and Michael Levin, "Cognition all the way down 2.0: neuroscience beyond neurons in the diverse intelligence era," *Synthese* 206, 257 (2025), [doi:10.1007/s11229-025-05319-6](https://doi.org/10.1007/s11229-025-05319-6).
