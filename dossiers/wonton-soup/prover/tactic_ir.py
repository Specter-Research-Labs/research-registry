from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

ACTION_KIND_TACTIC_STEP = "tactic_step"
ACTION_KIND_TERM_CONSTRUCTOR = "term_constructor"
ACTION_KIND_PROOF_RULE = "proof_rule"
ACTION_KIND_OTHER = "other"

CONTINUATION_KIND_SOLVE = "solve"
CONTINUATION_KIND_CHAIN = "chain"
CONTINUATION_KIND_BRANCH = "branch"
CONTINUATION_KIND_STRUCTURAL = "structural"
CONTINUATION_KIND_REFINE = "refine"

GOAL_COUPLING_NONE = "none"
GOAL_COUPLING_INDEPENDENT = "independent"
GOAL_COUPLING_COUPLED = "coupled"
GOAL_COUPLING_UNKNOWN = "unknown"

EFFECT_BUILDS_TERM = "builds_term"
EFFECT_OPENS_BINDER = "opens_binder"
EFFECT_BRANCHES_GOALS = "branches_goals"
EFFECT_REWRITES_TARGET = "rewrites_target"
EFFECT_NORMALIZES_GOAL = "normalizes_goal"
EFFECT_DISCHARGES_GOAL = "discharges_goal"
EFFECT_SEARCHES = "searches"
EFFECT_INSTANTIATES_GOAL = "instantiates_goal"
EFFECT_DERIVES_FACT = "derives_fact"
EFFECT_TRANSFORMS_GOALS = "transforms_goals"
EFFECT_CLOSES_GOALS = "closes_goals"
EFFECT_OPENS_GOALS = "opens_goals"
EFFECT_SPAWNS_GOALS = "spawns_goals"
EFFECT_USES_HYPOTHESES = "uses_hypotheses"
EFFECT_REFINES_TERM = "refines_term"
EFFECT_COMPLETES_TERM = "completes_term"
EFFECT_COUPLES_GOALS = "couples_goals"
EFFECT_SPLITS_INDEPENDENT_GOALS = "splits_independent_goals"

VALID_ACTION_KINDS = frozenset(
    {
        ACTION_KIND_TACTIC_STEP,
        ACTION_KIND_TERM_CONSTRUCTOR,
        ACTION_KIND_PROOF_RULE,
        ACTION_KIND_OTHER,
    }
)
VALID_CONTINUATION_KINDS = frozenset(
    {
        CONTINUATION_KIND_SOLVE,
        CONTINUATION_KIND_CHAIN,
        CONTINUATION_KIND_BRANCH,
        CONTINUATION_KIND_STRUCTURAL,
        CONTINUATION_KIND_REFINE,
    }
)
VALID_GOAL_COUPLINGS = frozenset(
    {
        GOAL_COUPLING_NONE,
        GOAL_COUPLING_INDEPENDENT,
        GOAL_COUPLING_COUPLED,
        GOAL_COUPLING_UNKNOWN,
    }
)


@dataclass(frozen=True)
class RoleSemantics:
    operator_kind: str
    motif_kind: str


@dataclass(frozen=True)
class TacticActionIR:
    action_kind: str
    operator_kind: str
    motif_kind: str
    effect_flags: frozenset[str]
    branch_arity: int
    continuation_kind: str
    goal_coupling: str


_ROLE_SEMANTICS = {
    "fn": RoleSemantics(operator_kind="apply", motif_kind="motif:term_apply"),
    "arg": RoleSemantics(operator_kind="apply", motif_kind="motif:term_apply"),
    "binder_type": RoleSemantics(operator_kind="bind", motif_kind="motif:term_bind"),
    "body": RoleSemantics(operator_kind="bind", motif_kind="motif:term_bind"),
    "value": RoleSemantics(operator_kind="value", motif_kind="motif:term_value"),
    "fam:intro": RoleSemantics(operator_kind="bind", motif_kind="motif:bind_open"),
    "fam:split": RoleSemantics(operator_kind="branch", motif_kind="motif:branch_split"),
    "fam:cases": RoleSemantics(operator_kind="branch", motif_kind="motif:branch_split"),
    "fam:rewrite": RoleSemantics(operator_kind="rewrite", motif_kind="motif:rewrite_step"),
    "fam:simplify": RoleSemantics(operator_kind="rewrite", motif_kind="motif:rewrite_step"),
    "fam:arith": RoleSemantics(operator_kind="normalize", motif_kind="motif:normalize_step"),
    "fam:closer": RoleSemantics(operator_kind="close", motif_kind="motif:close_goal"),
    "fam:contradiction": RoleSemantics(
        operator_kind="close",
        motif_kind="motif:close_goal",
    ),
    "fam:automation": RoleSemantics(
        operator_kind="automation",
        motif_kind="motif:auto_step",
    ),
    "fam:apply": RoleSemantics(operator_kind="apply", motif_kind="motif:apply_step"),
}

_DEFAULT_EFFECT_FLAGS_BY_ROLE = {
    "fn": frozenset({EFFECT_BUILDS_TERM}),
    "arg": frozenset({EFFECT_BUILDS_TERM}),
    "binder_type": frozenset({EFFECT_BUILDS_TERM}),
    "body": frozenset({EFFECT_BUILDS_TERM}),
    "value": frozenset({EFFECT_BUILDS_TERM}),
    "fam:intro": frozenset({EFFECT_OPENS_BINDER}),
    "fam:split": frozenset({EFFECT_BRANCHES_GOALS}),
    "fam:cases": frozenset({EFFECT_BRANCHES_GOALS}),
    "fam:rewrite": frozenset({EFFECT_REWRITES_TARGET}),
    "fam:simplify": frozenset({EFFECT_REWRITES_TARGET, EFFECT_NORMALIZES_GOAL}),
    "fam:arith": frozenset({EFFECT_NORMALIZES_GOAL}),
    "fam:closer": frozenset({EFFECT_DISCHARGES_GOAL}),
    "fam:contradiction": frozenset({EFFECT_DISCHARGES_GOAL}),
    "fam:automation": frozenset({EFFECT_SEARCHES}),
    "fam:apply": frozenset({EFFECT_INSTANTIATES_GOAL}),
}


def stable_unique_strings(values: Iterable[object]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def normalize_action_kind(raw: object) -> str:
    if isinstance(raw, str):
        value = raw.strip()
        if value in VALID_ACTION_KINDS:
            return value
    return ACTION_KIND_OTHER


def normalize_continuation_kind(
    raw: object,
    *,
    action_kind: str,
    branch_arity: int,
) -> str:
    if isinstance(raw, str):
        value = raw.strip()
        if value in VALID_CONTINUATION_KINDS:
            return value
    if action_kind == ACTION_KIND_TERM_CONSTRUCTOR:
        return CONTINUATION_KIND_STRUCTURAL
    if branch_arity <= 0:
        return CONTINUATION_KIND_SOLVE
    if branch_arity == 1:
        return CONTINUATION_KIND_CHAIN
    return CONTINUATION_KIND_BRANCH


def normalize_goal_coupling(
    raw: object,
    *,
    action_kind: str,
    branch_arity: int,
) -> str:
    if isinstance(raw, str):
        value = raw.strip()
        if value in VALID_GOAL_COUPLINGS:
            return value
    if action_kind != ACTION_KIND_TACTIC_STEP or branch_arity <= 1:
        return GOAL_COUPLING_NONE
    return GOAL_COUPLING_UNKNOWN


def explicit_effect_flags(raw: object) -> frozenset[str]:
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(stable_unique_strings(raw))


def ordered_effect_flags(*groups: Iterable[object]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in stable_unique_strings(group):
            if value in seen:
                continue
            seen.add(value)
            out.append(value)
    return out


def role_semantics(role: str) -> RoleSemantics:
    return _ROLE_SEMANTICS.get(
        role,
        RoleSemantics(operator_kind="other", motif_kind="motif:other"),
    )


def default_effect_flags_for_role(role: str, *, action_kind: str) -> frozenset[str]:
    mapped = _DEFAULT_EFFECT_FLAGS_BY_ROLE.get(role)
    if mapped is not None:
        return mapped
    if action_kind == ACTION_KIND_TERM_CONSTRUCTOR:
        return frozenset({EFFECT_BUILDS_TERM})
    if action_kind == ACTION_KIND_PROOF_RULE:
        return frozenset({EFFECT_DERIVES_FACT})
    if action_kind == ACTION_KIND_TACTIC_STEP:
        return frozenset({EFFECT_TRANSFORMS_GOALS})
    return frozenset()
