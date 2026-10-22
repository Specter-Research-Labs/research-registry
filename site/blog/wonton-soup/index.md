---
title: "Proof search with a missing tactic"
release: "published"
summary: We block one tactic from a successful Lean proof search and rerun it under the same budget to see whether the prover still reaches the theorem by another route.
series: B-001
pdf: wonton-soup.pdf
cover: /assets/blog/wonton-soup/fig1-mcts-tree.png
cover_alt: A proof search tree in which two rewrites of a * (b + c) lead to proofs by ring.
---

# Proof search with a missing tactic

In one Wonton search the prover proved a theorem with `contrapose!`, and when we blocked that tactic it still got there, this time through `intro` and `exact`. It is a small detour, but it is the question we built Wonton to ask: if a theorem admits several proofs, how many of them can a given prover actually reach once the route it normally takes is closed?

Counting proofs does not answer that, because visibly different proofs can lean on the same tactic, and losing that tactic closes all of them at once. So we record the attempted tactics and intermediate goals, block one tactic the successful search used, and give the prover the same budget again, which shows where the alternatives come from and where they run out. Some searches recover, some fail, and occasionally the block helps by taking an unproductive branch out of the search.

## Following the detour

At each unfinished goal the prover proposes tactics, and each attempt fails, opens new goals or closes the proof. The gallery follows three searches that still succeeded after the block, because a success can hide how much changed underneath it. Blocking `contrapose!` sends the prover through a direct argument that assumes the premise and derives the conclusion. The other two are local swaps in which the goals stay the same and only the last step changes, so a comparison of graph shapes alone would miss them.

<div class="ws-stepper ws-vignette-stepper" data-title="Three searches with one tactic blocked" data-slides='[
  {
    "label":"contrapositive / block contrapose!",
    "metrics":"Solved | edit distance 0.67 | different route",
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
    "caption":"With contrapose! blocked, the prover argues forward with intro and exact.",
    "lightbox":false
  },
  {
    "label":"nat_succ_pred / block positivity",
    "metrics":"Solved | edit distance 0.00 | last step swapped",
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
    "caption":"With positivity blocked, the prover makes the same rewrite and closes the remaining goal with Nat.ne_of_gt. The blocked simp attempts in the original search come from this sweep, which blocks simp in every run.",
    "lightbox":false
  },
  {
    "label":"iff_intro / block exact",
    "metrics":"Solved | edit distance 0.00 | last step swapped",
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
    "caption":"With exact blocked, the prover still splits the iff with constructor and closes the goal with assumption instead.",
    "lightbox":false
  }
]'>
<div class="ws-stepper-fallback">
<p>Interactive graph gallery requires JavaScript.</p>
</div>
</div>


The examples come from runs in February 2026. Edit distance is the normalized graph edit distance between the two recorded search graphs, which is 0 when they have the same shape.

## The control changed too

Before blaming a changed proof on the block, we needed to know how much the search changes when its available tactics stay the same. We reran it with a tactic blocked that the original run never had available (an inert block), and while ReProver repeated itself, some DeepSeek searches changed under this control too.

We had fixed the search seed, but the model server still sampled new tactic suggestions, and hard theorems made more calls to it, giving small differences more chances to redirect the search. A configuration flag named `deterministic_inference` made this easy to miss, because it fixed only the search seed, and earlier DeepSeek campaigns had mostly run without the paired controls that would have exposed it. We now count a comparison only when both the original search and its inert rerun solve the theorem.

## When removing a move helps

Blocking a tactic can help when it cuts off a branch the prover would otherwise spend its budget on, leaving more attempts for a route that works. The restricted search may then reach a theorem the original missed, or reach it sooner, and the trace shows where the saved attempts went.

To size that saving against a blind policy we use $K = \log_{10}(\tau_{blind}/\tau_{agent})$, the saving in orders of magnitude when both policies face the same moves, constraints, goal, horizon and cost units. Those choices define the number, so changing them changes what it tells us; the [K reference](/cabinet/k-semantics-reference/k-equations/) works through them, and the [analysis reference](/cabinet/wonton-soup/concepts/analysis-metrics/) describes the measurements Wonton stores.

## What can travel between systems?

One reason we built this experiment is Levin's [TAME framework](https://arxiv.org/abs/2201.10346) and its question of how a system reaches the same outcome when it has to find another way. Proof search makes that problem unusually explicit, because the goal is fixed in advance, a checker decides whether it was reached, and the trace shows every attempt made under the new constraint.

With a developing body we first have to decide which features of its organization count as persisting or recovering, which makes the comparison harder and is part of what we want to study. The proof searches still suggest a specific question for bodies: does the variety we see among forms or behaviors overstate their resilience when they all depend on the same vulnerable mechanism?

For proofs we can test this by grouping them by the lemmas and tactics they use and asking whether that grouping predicts survival on held-out theorem and prover pairs better than counting proof shapes does. That would separate alternatives that only look different from ones the prover can still use when a resource disappears.

Selected runs are in the [Wonton Soup dashboard](/dashboards/wonton-soup/), and the [Cabinet](/cabinet/wonton-soup/README/) documents search scheduling, backend differences and the files needed to reproduce the comparisons.
