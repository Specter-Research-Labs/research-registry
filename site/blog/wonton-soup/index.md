---
title: "Proof search with a missing tactic"
release: "published"
summary: We block one tactic from a successful Lean proof search and rerun it to see which proofs survive.
series: B-001
pdf: wonton-soup.pdf
cover: /assets/blog/wonton-soup/fig1-mcts-tree.png
cover_alt: A proof search tree in which two rewrites of a * (b + c) lead to proofs by ring.
---

# Proof search with a missing tactic

In one Wonton search, the prover found a proof using `contrapose!`, and when we blocked that tactic it still reached the theorem, this time through `intro` and `exact`. It is a small detour, but it gets at something we wanted to understand about proof search: if a theorem admits several proofs, how many of them can a particular prover actually reach when the route it normally takes becomes unavailable?

The difficulty is that even visibly different proofs can depend on the same tactic, so collecting more of them need not give the prover another way through. We record the attempted tactics and intermediate goals, remove a tactic from a successful search, and give the prover the same budget to try again, which lets us follow where the alternatives come from and where they run out. Some searches recover, some fail, and occasionally removing a move helps by taking an unproductive possibility out of the search.

## Following the detour

At each unfinished goal, the prover proposes tactics and explores the proof states they produce, with each attempt either failing, opening further goals, or completing the proof. The examples below follow three successful searches through tactic removal so that we can see what changed along the way, including cases where the final success would otherwise make the intervention look inconsequential.

In the first example, blocking contraposition sends the prover through a direct argument in which it assumes the premise and derives the conclusion. The other two are more local substitutions: the sequence of goals stays similar, but a different final step closes the proof, so even a comparison of graph shapes would miss part of what happened.

<div class="ws-stepper ws-vignette-stepper" data-title="Log-derived vignette gallery" data-slides='[
  {
    "label":"contrapositive / block contrapose!",
    "metrics":"Solved | normalized GED_search 0.67 | structural reroute",
    "ged":0.6666666666666666,
    "attempts":{"blocked":1,"failure":1,"success":1},
    "attempt_graph":{
      "wild":{
        "root":"¬P",
        "attempts":[
          {"tactic":"exact hnq","outcome":"failure"},
          {"tactic":"contrapose! hnq","outcome":"success"}
        ],
        "continuation":"exact h hnq"
      },
      "intervention":{
        "root":"¬P",
        "attempts":[
          {"tactic":"contrapose! hnq","outcome":"blocked"},
          {"tactic":"exact hnq","outcome":"failure"},
          {"tactic":"intro hP","outcome":"success"}
        ],
        "continuation":"exact hnq (h hP)"
      }
    },
    "wild_path":["contrapose! hnq","exact h hnq"],
    "intervention_path":["intro hP","exact hnq (h hP)"],
    "caption":"Blocking contrapose! forces a forward route (intro + exact), producing a clear structural shift.",
    "lightbox":false
  },
  {
    "label":"nat_succ_pred / block positivity",
    "metrics":"Solved | normalized GED_search 0.00 | local tactic swap",
    "ged":0.0,
    "attempts":{"blocked":0,"failure":0,"success":1},
    "attempt_graph":{
      "wild":{
        "root":"n.pred.succ = n",
        "attempts":[
          {"tactic":"simp [Nat.succ_pred_eq_of_pos h]","outcome":"blocked"},
          {"tactic":"simp [Nat.succ_eq_add_one]","outcome":"blocked"},
          {"tactic":"rw [succ_pred]","outcome":"success"}
        ],
        "continuation":"positivity"
      },
      "intervention":{
        "root":"n.pred.succ = n",
        "attempts":[
          {"tactic":"rw [succ_pred]","outcome":"success"}
        ],
        "continuation":"exact Nat.ne_of_gt h"
      }
    },
    "wild_path":["rw [succ_pred]","positivity"],
    "intervention_path":["rw [succ_pred]","exact Nat.ne_of_gt h"],
    "caption":"Blocking positivity preserves structure and swaps in an explicit Nat.ne_of_gt proof step.",
    "lightbox":false
  },
  {
    "label":"iff_intro / block exact",
    "metrics":"Solved | normalized GED_search 0.00 | terminal discharge swap",
    "ged":0.0,
    "attempts":{"blocked":3,"failure":0,"success":1},
    "attempt_graph":{
      "wild":{
        "root":"P ↔ Q",
        "attempts":[
          {"tactic":"constructor","outcome":"success"}
        ],
        "continuation":"exact hpq"
      },
      "intervention":{
        "root":"P ↔ Q",
        "attempts":[
          {"tactic":"exact ⟨hpq, hqp⟩","outcome":"blocked"},
          {"tactic":"exact ⟨fun hp => hqp hp, ...⟩","outcome":"blocked"},
          {"tactic":"exact ⟨fun hp => hqp hp, fun hp => hqp hp⟩","outcome":"blocked"},
          {"tactic":"constructor","outcome":"success"}
        ],
        "continuation":"assumption"
      }
    },
    "wild_path":["constructor","exact hpq"],
    "intervention_path":["constructor","assumption"],
    "caption":"The terminal tactic changes from exact to assumption while the trajectory remains in-family.",
    "lightbox":false
  }
]'>
<div class="ws-stepper-fallback">
<p>Interactive graph gallery requires JavaScript.</p>
</div>
</div>


The gallery records early examples from February 2026. Its graph distances describe changes in the recorded searches; repeated structures do not by themselves establish dynamical attractors.

## The control changed too

Before attributing a changed proof to the tactic block, we needed to know how much the search could change when its available choices stayed the same. We repeated it with a tactic disabled that was already unavailable to the original run (an inert intervention), and although ReProver repeated consistently, some DeepSeek results changed under this control too.

We had fixed the search seed, but the model server was still sampling new tactic suggestions, and difficult theorems made more calls to that server, giving small differences more opportunities to redirect the search. Without the inert rerun, we could have mistaken those differences for an effect of the tactic we intended to study. The [control investigation](/research-notes/2026-04-02-wonton-controls-exposed-a-reproducibility-problem/) follows how we found the problem.

The controlled comparison therefore requires both the original search and its inert rerun to solve the theorem before we ask what happens when a tactic used by the successful search is actually blocked.

## When removing a move helps

Removing a tactic can help when it cuts off a branch on which the prover would otherwise spend its budget, leaving more attempts for a route that succeeds. In those cases the restricted search may reach a theorem the original search missed, or reach it sooner, and the trace lets us investigate that improvement by following where the attempts went. A restriction changes the allocation of a finite search as well as the set of moves available to it.

To compare that cost with a specified blind policy, we use $K = \log_{10}(\tau_{blind}/\tau_{agent})$, which expresses the saving in orders of magnitude when both policies face the same moves, constraints, goal, horizon, and cost units. These choices define the comparison, so changing them changes what the number tells us; the [K reference](/cabinet/k-semantics-reference/k-equations/) works through them, while the [analysis reference](/cabinet/wonton-soup/concepts/analysis-metrics/) distinguishes the measurements stored by Wonton.

## What can travel between systems?

One reason we became interested in this experiment is Levin's [TAME framework](https://arxiv.org/abs/2201.10346), and the question running through it of how a system reaches the same outcome when it has to find another way. Proof search gives us an unusually explicit version of that problem, because the goal is supplied in advance, a checker determines whether it has been reached, and the trace lets us inspect the attempts made under the new constraint.

With a developing body, we first have to decide which features of its organization count as persisting or recovering, which makes the comparison harder and also part of what we want to investigate. We can still ask which routes remain available after an intervention and what resources those routes share, using the Wonton result to motivate a more specific question: could the variety we observe among forms or behaviors also overstate their resilience when they depend on the same vulnerable mechanism?

For proofs, we can test this by grouping them according to the lemmas and tactic resources they use, then asking whether that description predicts survival on held-out theorem–prover groups better than counting proof shapes. That would give us a chance to explain why the diversity prediction failed, and to distinguish alternatives that merely look different from ones the prover can actually use when a resource disappears.

*This article records the early experimental framework, and the counts from the later controlled tactic-blocking cohort are being re-audited before we publish them again. Selected runs are available in the [Wonton Soup Dashboard](/dashboards/wonton-soup/).*

The [Cabinet](/cabinet/wonton-soup/README/) documents search scheduling, backend differences, and the files needed to reproduce the comparisons.
