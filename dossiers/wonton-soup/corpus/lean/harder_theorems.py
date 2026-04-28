# ruff: noqa: E501
from corpus.lean.theorems import Theorem

CORPUS_HARD: list[Theorem] = [
    Theorem("three_way_or", "theorem {name} (P Q R S : Prop) (h : P \\/ Q \\/ R) (hp : P -> S) (hq : Q -> S) (hr : R -> S) : S := by\n  sorry"),
    Theorem("nested_or_flatten", "theorem {name} (P Q R S : Prop) (h : (P \\/ Q) \\/ (R \\/ S)) : P \\/ Q \\/ R \\/ S := by\n  sorry"),
    Theorem("and_assoc", "theorem {name} (P Q R : Prop) (h : (P /\\ Q) /\\ R) : P /\\ (Q /\\ R) := by\n  sorry"),
    Theorem("iff_trans", "theorem {name} (P Q R : Prop) (hpq : P <-> Q) (hqr : Q <-> R) : P <-> R := by\n  sorry"),
    Theorem("or_iff_comm", "theorem {name} (P Q : Prop) : P \\/ Q <-> Q \\/ P := by\n  sorry"),
    Theorem("and_iff_comm", "theorem {name} (P Q : Prop) : P /\\ Q <-> Q /\\ P := by\n  sorry"),
    Theorem("exists_imp_hard", "theorem {name} (P Q : Nat -> Prop) (h : forall n, P n -> Q n) (hex : exists n, P n) : exists n, Q n := by\n  sorry"),
    Theorem("forall_imp", "theorem {name} (P Q : Nat -> Prop) (h : forall n, P n -> Q n) (hp : forall n, P n) : forall n, Q n := by\n  sorry"),
    Theorem("not_and_or", "theorem {name} (P Q : Prop) (h : ¬(P ∧ Q)) : ¬P ∨ ¬Q := by\n  sorry"),
    Theorem("not_or_and", "theorem {name} (P Q : Prop) (h : ¬(P ∨ Q)) : ¬P ∧ ¬Q := by\n  sorry"),
    Theorem("contrapositive_iff_hard", "theorem {name} (P Q : Prop) : (P → Q) ↔ (¬Q → ¬P) := by\n  sorry"),
    Theorem("nat_succ_pred", "theorem {name} (n : Nat) (h : n > 0) : Nat.succ (Nat.pred n) = n := by\n  sorry"),
    Theorem("add_right_cancel_hard", "theorem {name} (a b c : Nat) (h : a + c = b + c) : a = b := by\n  sorry"),
    Theorem("mul_zero_left", "theorem {name} (n : Nat) : 0 * n = 0 := by\n  sorry"),
    Theorem("set_empty_union", "theorem {name} (s : Set Nat) : ∅ ∪ s = s := by\n  sorry"),
    Theorem("set_inter_empty", "theorem {name} (s : Set Nat) : s ∩ ∅ = ∅ := by\n  sorry"),
    Theorem("set_union_self", "theorem {name} (s : Set Nat) : s ∪ s = s := by\n  sorry"),
    Theorem("set_inter_self", "theorem {name} (s : Set Nat) : s ∩ s = s := by\n  sorry"),
    Theorem("list_cons_append", "theorem {name} (x : Nat) (l1 l2 : List Nat) : (x :: l1) ++ l2 = x :: (l1 ++ l2) := by\n  sorry"),
    Theorem("list_append_assoc", "theorem {name} (l1 l2 l3 : List Nat) : (l1 ++ l2) ++ l3 = l1 ++ (l2 ++ l3) := by\n  sorry"),
]
