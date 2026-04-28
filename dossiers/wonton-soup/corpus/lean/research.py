from corpus.lean.harder_theorems import CORPUS_HARD
from corpus.lean.theorems import CORPUS, Theorem

VALIDATED_NAMES = {
    "add_comm_nat",
    "add_le_add",
    "add_right_cancel",
    "and_or_distrib",
    "contrapositive",
    "contrapositive_iff",
    "de_morgan_not_and",
    "de_morgan_not_or",
    "double_neg_elim",
    "exists_and_distrib",
    "exists_imp",
    "forall_and_distrib",
    "forall_trivial",
    "iff_intro",
    "iff_trans",
    "imp_trans",
    "impl_chain",
    "list_append_nil",
    "list_length_append",
    "logic_chain",
    "mul_add_distrib",
    "mul_comm_nat",
    "nat_conj",
    "nat_succ_pred",
    "nested_or_flatten",
    "not_or_and",
    "or_and_distrib",
    "or_comm",
    "or_left",
    "set_empty_union",
    "set_inter_comm",
    "set_inter_empty",
    "set_inter_self",
    "set_subset_refl",
    "set_subset_trans",
    "set_union_comm",
    "set_union_self",
    "sum_zero",
    "three_way_or",
    "zero_add",
}

CORPUS_RESEARCH: list[Theorem] = [
    t for t in CORPUS + CORPUS_HARD if t.name in VALIDATED_NAMES
]
