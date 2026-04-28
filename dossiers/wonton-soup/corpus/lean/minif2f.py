from dataclasses import dataclass


@dataclass
class HardTheorem:
    name: str
    statement: str
    description: str


MINIF2F_CORPUS: list[HardTheorem] = [
    HardTheorem(
        name="algebra_binomsq",
        statement="theorem {name} (a b : Int) : (a + b)^2 = a^2 + 2*a*b + b^2 := by sorry",
        description="Binomial square expansion",
    ),
    HardTheorem(
        name="logic_demorgan",
        statement="theorem {name} (P Q : Prop) : ¬(P ∧ Q) ↔ (¬P ∨ ¬Q) := by sorry",
        description="De Morgan's law - requires constructor for iff",
    ),
    HardTheorem(
        name="logic_contrapositive",
        statement="theorem {name} (P Q : Prop) : (P → Q) → (¬Q → ¬P) := by sorry",
        description="Contrapositive - multiple intros needed",
    ),
    HardTheorem(
        name="logic_and_comm",
        statement="theorem {name} (P Q : Prop) : P ∧ Q ↔ Q ∧ P := by sorry",
        description="And commutativity - needs constructor + And.intro",
    ),
    HardTheorem(
        name="logic_or_assoc",
        statement="theorem {name} (P Q R : Prop) : (P ∨ Q) ∨ R ↔ P ∨ (Q ∨ R) := by sorry",
        description="Or associativity - multiple cases needed",
    ),
    HardTheorem(
        name="logic_distribute",
        statement="theorem {name} (P Q R : Prop) : P ∧ (Q ∨ R) ↔ (P ∧ Q) ∨ (P ∧ R) := by sorry",
        description="Distribution - complex case analysis",
    ),
    HardTheorem(
        name="nat_add_comm",
        statement="theorem {name} (n m : Nat) : n + m = m + n := by sorry",
        description="Natural number addition commutativity",
    ),
    HardTheorem(
        name="nat_mul_zero",
        statement="theorem {name} (n : Nat) : n * 0 = 0 := by sorry",
        description="Multiplication by zero",
    ),
    HardTheorem(
        name="int_neg_neg",
        statement="theorem {name} (a : Int) : -(-a) = a := by sorry",
        description="Double negation of integers",
    ),
    HardTheorem(
        name="logic_triple_neg",
        statement="theorem {name} (P : Prop) : ¬¬¬P → ¬P := by sorry",
        description="Triple negation implies single negation",
    ),
    HardTheorem(
        name="exists_and_distrib",
        statement=(
            "theorem {name} (P Q : Nat → Prop) : (∃ x, P x ∧ Q x) → "
            "(∃ x, P x) ∧ (∃ x, Q x) := by sorry"
        ),
        description="Existential distributes over and",
    ),
    HardTheorem(
        name="forall_imp_distrib",
        statement=(
            "theorem {name} (P Q : Nat → Prop) : (∀ x, P x → Q x) → "
            "(∀ x, P x) → (∀ x, Q x) := by sorry"
        ),
        description="Forall distributes over implication",
    ),
]
