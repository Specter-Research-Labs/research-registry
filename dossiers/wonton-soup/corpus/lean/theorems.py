# ruff: noqa: E402, E501
import re
from dataclasses import dataclass

from prover.history import ExplorationHistory
from prover.providers.base import normalize_tactic

_TACTIC_HEAD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_'.?]*")


@dataclass
class Intervention:
    name: str
    blocked: set[str]
    is_control: bool = False


@dataclass
class Theorem:
    name: str
    statement: str

    def generate_interventions(self, wild_type_history: ExplorationHistory) -> list[Intervention]:
        if wild_type_history.solution_path is not None:
            used_tactics = wild_type_history.tactics_on_solution_path()
        else:
            used_tactics = sorted(wild_type_history.attempted_tactics())

        used_heads = {
            head
            for tactic in used_tactics
            if tactic and (head := _tactic_head(tactic)) is not None
        }
        interventions = [
            Intervention(name=f"block_{head}", blocked={head})
            for head in sorted(used_heads)
        ]

        attempted_heads = {
            head
            for tactic in wild_type_history.attempted_tactics()
            if (head := _tactic_head(tactic)) is not None
        }
        unused_heads = sorted(attempted_heads - used_heads)
        if unused_heads:
            control_tactic = unused_heads[0]
            interventions.append(Intervention(
                name="control_null",
                blocked={control_tactic},
                is_control=True,
            ))

        return interventions


def _tactic_head(tactic: str) -> str | None:
    tactic_norm = normalize_tactic(tactic)
    if not tactic_norm:
        return None
    head = tactic_norm.split(" ", 1)[0]
    if _TACTIC_HEAD_RE.fullmatch(head) is None:
        return None
    return head.rstrip("0123456789") or head


CORPUS: list[Theorem] = [
    Theorem("logic_chain", "theorem {name} (P Q R : Prop) (hp : P) (hpq : P -> Q) (hqr : Q -> R) : R := by\n  sorry"),
    Theorem("and_intro", "theorem {name} (P Q : Prop) (hp : P) (hq : Q) : P /\\ Q := by\n  sorry"),
    Theorem("or_left", "theorem {name} (P Q : Prop) (hp : P) : P \\/ Q := by\n  sorry"),
    Theorem("arith_simple", "theorem {name} : 2 + 2 = 4 := by\n  sorry"),
    Theorem("arith_ineq", "theorem {name} (n : Nat) : n <= n + 1 := by\n  sorry"),
    Theorem("sum_zero", "theorem {name} (n : Nat) : n + 0 = n := by\n  sorry"),
    Theorem("impl_chain", "theorem {name} (P Q : Prop) (hp : P) (hpq : P -> Q) : Q := by\n  sorry"),
    Theorem("true_trivial", "theorem {name} : True := by\n  sorry"),
    Theorem("false_elim", "theorem {name} (P : Prop) (hf : False) : P := by\n  sorry"),
    Theorem("and_triple", "theorem {name} (P Q R : Prop) (hp : P) (hq : Q) (hr : R) : P /\\ Q /\\ R := by\n  sorry"),
    Theorem("nat_conj", "theorem {name} (n : Nat) : n + 0 = n /\\ 0 + n = n := by\n  sorry"),
    Theorem("or_comm", "theorem {name} (P Q : Prop) (h : P \\/ Q) : Q \\/ P := by\n  sorry"),
    Theorem("iff_intro", "theorem {name} (P Q : Prop) (hpq : P -> Q) (hqp : Q -> P) : P <-> Q := by\n  sorry"),
    Theorem("and_comm_hyp", "theorem {name} (P Q : Prop) (h : P /\\ Q) : Q /\\ P := by\n  sorry"),
    Theorem("forall_trivial", "theorem {name} (P : Prop) (hp : P) : forall n : Nat, P := by\n  sorry"),
    Theorem("list_length", "theorem {name} : [1, 2, 3].length = 3 := by\n  sorry"),
    Theorem("set_subset_refl", "theorem {name} (s : Set Nat) : s ⊆ s := by\n  sorry"),
    Theorem("set_subset_trans", "theorem {name} (s t u : Set Nat) (hst : s ⊆ t) (htu : t ⊆ u) : s ⊆ u := by\n  sorry"),
    Theorem("set_union_comm", "theorem {name} (s t : Set Nat) : s ∪ t = t ∪ s := by\n  sorry"),
    Theorem("set_inter_comm", "theorem {name} (s t : Set Nat) : s ∩ t = t ∩ s := by\n  sorry"),
    Theorem("set_union_subset", "theorem {name} (s t u : Set Nat) (hs : s ⊆ u) (ht : t ⊆ u) : s ∪ t ⊆ u := by\n  sorry"),
    Theorem("set_subset_inter", "theorem {name} (s t u : Set Nat) (hs : s ⊆ t) (ht : s ⊆ u) : s ⊆ t ∩ u := by\n  sorry"),
    Theorem("set_mem_union_left", "theorem {name} (x : Nat) (s t : Set Nat) (h : x ∈ s) : x ∈ s ∪ t := by\n  sorry"),
    Theorem("set_mem_inter", "theorem {name} (x : Nat) (s t : Set Nat) (hs : x ∈ s) (ht : x ∈ t) : x ∈ s ∩ t := by\n  sorry"),
    Theorem("de_morgan_not_and", "theorem {name} (P Q : Prop) (h : ¬(P ∧ Q)) (hp : P) : ¬Q := by\n  sorry"),
    Theorem("de_morgan_not_or", "theorem {name} (P Q : Prop) (h : ¬(P ∨ Q)) : ¬P ∧ ¬Q := by\n  sorry"),
    Theorem("contrapositive", "theorem {name} (P Q : Prop) (h : P → Q) (hnq : ¬Q) : ¬P := by\n  sorry"),
    Theorem("double_neg_elim", "theorem {name} (P : Prop) (h : ¬¬P) : P := by\n  sorry"),
    Theorem("add_comm_nat", "theorem {name} (a b : Nat) : a + b = b + a := by\n  sorry"),
    Theorem("add_assoc_nat", "theorem {name} (a b c : Nat) : (a + b) + c = a + (b + c) := by\n  sorry"),
    Theorem("mul_comm_nat", "theorem {name} (a b : Nat) : a * b = b * a := by\n  sorry"),
    Theorem("mul_add_distrib", "theorem {name} (a b c : Nat) : a * (b + c) = a * b + a * c := by\n  sorry"),
    Theorem("zero_add", "theorem {name} (n : Nat) : 0 + n = n := by\n  sorry"),
    Theorem("mul_one", "theorem {name} (n : Nat) : n * 1 = n := by\n  sorry"),
    Theorem("add_le_add", "theorem {name} (a b c d : Nat) (hab : a ≤ b) (hcd : c ≤ d) : a + c ≤ b + d := by\n  sorry"),
    Theorem("le_trans", "theorem {name} (a b c : Nat) (hab : a ≤ b) (hbc : b ≤ c) : a ≤ c := by\n  sorry"),
    Theorem("list_append_nil", "theorem {name} (l : List Nat) : l ++ [] = l := by\n  sorry"),
    Theorem("list_nil_append", "theorem {name} (l : List Nat) : [] ++ l = l := by\n  sorry"),
    Theorem("list_length_append", "theorem {name} (l1 l2 : List Nat) : (l1 ++ l2).length = l1.length + l2.length := by\n  sorry"),
    Theorem("exists_intro", "theorem {name} (P : Nat → Prop) (h : P 0) : ∃ n, P n := by\n  sorry"),
    Theorem("exists_and_distrib", "theorem {name} (P Q : Nat → Prop) (h : ∃ n, P n ∧ Q n) : (∃ n, P n) ∧ (∃ n, Q n) := by\n  sorry"),
    Theorem("forall_and_distrib", "theorem {name} (P Q : Nat → Prop) (hp : ∀ n, P n) (hq : ∀ n, Q n) : ∀ n, P n ∧ Q n := by\n  sorry"),
    Theorem("imp_trans", "theorem {name} (P Q R : Prop) (hpq : P → Q) (hqr : Q → R) : P → R := by\n  sorry"),
    Theorem("and_or_distrib", "theorem {name} (P Q R : Prop) (h : P ∧ (Q ∨ R)) : (P ∧ Q) ∨ (P ∧ R) := by\n  sorry"),
    Theorem("or_and_distrib", "theorem {name} (P Q R : Prop) (h : P ∨ (Q ∧ R)) : (P ∨ Q) ∧ (P ∨ R) := by\n  sorry"),
    Theorem("exists_imp", "theorem {name} (P : Nat → Prop) (Q : Prop) (h : ∃ n, P n → Q) (hp : ∀ n, P n) : Q := by\n  sorry"),
    Theorem("add_right_cancel", "theorem {name} (a b c : Nat) (h : a + c = b + c) : a = b := by\n  sorry"),
    Theorem("contrapositive_iff", "theorem {name} (P Q : Prop) : (P → Q) ↔ (¬Q → ¬P) := by\n  sorry"),
]

from corpus.lean.deepseek_theorems import DEEPSEEK_CORPUS
from corpus.lean.mathlib_theorems import MATHLIB_CORPUS
from corpus.lean.minif2f_theorems import MINIF2F_CORPUS
from corpus.lean.proverbench_theorems import PROVERBENCH_CORPUS

CORPUS_EXPANDED: list[Theorem] = [
    *CORPUS,
    *DEEPSEEK_CORPUS,
]

CORPUS_PROVERBENCH: list[Theorem] = [
    *CORPUS,
    *PROVERBENCH_CORPUS,
]

CORPUS_MATHLIB: list[Theorem] = [
    *CORPUS,
    *MATHLIB_CORPUS,
]

CORPUS_MINIF2F: list[Theorem] = [
    *CORPUS,
    *MINIF2F_CORPUS,
]
