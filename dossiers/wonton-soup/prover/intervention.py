from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from prover.goal_signature import GoalSignatureConfig
from prover.providers.base import (
    TacticProvider,
    goal_signature,
    normalize_tactic,
    tactic_family,
)

if TYPE_CHECKING:
    from leantree.core.lean import LeanGoal


class PegKind(Enum):
    TACTIC = "tactic"
    FAMILY = "family"
    CONDITIONAL = "conditional"
    BUDGET = "budget"


@dataclass(frozen=True)
class PegRule:
    peg_id: str
    kind: PegKind
    blocked_tactics: frozenset[str] = field(default_factory=frozenset)
    blocked_families: frozenset[str] = field(default_factory=frozenset)
    condition: str | None = None


@dataclass(frozen=True)
class PegBudget:
    peg_id: str
    max_total_attempts: int | None = None
    max_family_attempts: int | None = None


@dataclass(frozen=True)
class BlockedTactic:
    tactic: str
    tactic_norm: str
    peg_id: str
    peg_kind: str
    block_reason: str
    goal_sig: str
    provider_id: str | None = None


@dataclass
class _BudgetCounter:
    total: int = 0
    families: dict[str, int] = field(default_factory=dict)


def _goal_matches_condition(goal: LeanGoal, condition: str) -> bool:
    goal_type = goal.type
    and_symbol = "\u2227"
    or_symbol = "\u2228"
    forall_symbol = "\u2200"
    exists_symbol = "\u2203"
    imp_symbol = "\u2192"
    nat_symbol = "\u2115"
    int_symbol = "\u2124"

    if condition == "goal_has_and":
        return and_symbol in goal_type or "And" in goal_type
    if condition == "goal_has_or":
        return or_symbol in goal_type or "Or" in goal_type
    if condition == "goal_has_exists":
        return exists_symbol in goal_type or "Exists" in goal_type
    if condition == "goal_has_forall":
        return forall_symbol in goal_type or goal_type.startswith("forall")
    if condition == "goal_has_imp":
        return imp_symbol in goal_type or "->" in goal_type
    if condition == "goal_is_arith":
        return (
            "Nat" in goal_type
            or "Int" in goal_type
            or nat_symbol in goal_type
            or int_symbol in goal_type
        )
    if condition == "goal_has_eq":
        return "=" in goal_type
    raise ValueError(f"Unknown peg condition: {condition}")


class FilteredTacticProvider(TacticProvider):
    def __init__(
        self,
        base: TacticProvider,
        blocked: set[str] | None = None,
        blocked_families: set[str] | None = None,
        peg_rules: list[PegRule] | None = None,
        peg_budget: PegBudget | None = None,
        provider_id: str | None = None,
        goal_sig_config: GoalSignatureConfig | None = None,
    ):
        self.base = base
        self.blocked = set(blocked or [])
        self.blocked_families = set(blocked_families or [])
        self.peg_rules: list[PegRule] = []
        self.peg_budget = peg_budget
        self.provider_id = provider_id
        if goal_sig_config is None:
            raise ValueError("goal_sig_config is required")
        self.goal_sig_config = goal_sig_config
        self.last_blocked: list[BlockedTactic] = []
        self._budget_counts: dict[str, _BudgetCounter] = {}

        if self.blocked:
            self.peg_rules.append(
                PegRule(
                    peg_id="block_tactic",
                    kind=PegKind.TACTIC,
                    blocked_tactics=frozenset(self.blocked),
                )
            )
        if self.blocked_families:
            self.peg_rules.append(
                PegRule(
                    peg_id="block_family",
                    kind=PegKind.FAMILY,
                    blocked_families=frozenset(self.blocked_families),
                )
            )
        if peg_rules:
            self.peg_rules.extend(peg_rules)

    def describe(self) -> str:
        return (
            f"{self.__class__.__name__}(base={self.base.describe()}, "
            f"rules={len(self.peg_rules)}, budget={'yes' if self.peg_budget else 'no'})"
        )

    def set_seed(self, seed: int) -> None:
        set_seed = getattr(self.base, "set_seed", None)
        if callable(set_seed):
            set_seed(seed)

    def clear_cache(self) -> None:
        clear_cache = getattr(self.base, "clear_cache", None)
        if callable(clear_cache):
            clear_cache()
        self.last_blocked = []
        self._budget_counts = {}

    async def suggest_tactics_with_probs_async(
        self,
        goal: LeanGoal,
        mvar_id: str,
        adapter,
        n: int = 10,
    ) -> list[tuple[str, float]]:
        tactics_with_probs = await self.base.suggest_tactics_with_probs_async(
            goal, mvar_id, adapter, n * 2
        )
        return self._filter_tactics_with_probs(goal, tactics_with_probs, n, budget_key=mvar_id)

    def _filter_tactics_with_probs(
        self,
        goal: LeanGoal,
        tactics_with_probs: list[tuple[str, float]],
        n: int,
        budget_key: str | None,
    ) -> list[tuple[str, float]]:
        self.last_blocked = []
        filtered: list[tuple[str, float]] = []
        goal_sig = goal_signature(goal, self.goal_sig_config)
        budget_id = None
        if self.peg_budget is not None:
            if budget_key is None:
                raise ValueError("peg_budget requires budget_key")
            budget_id = budget_key

        for tactic, prob in tactics_with_probs:
            if len(filtered) >= n:
                break
            decision = self._match_rules(goal, tactic, goal_sig)
            if decision is None and budget_id is not None:
                decision = self._match_budget(goal_sig, tactic, budget_id)
            if decision is not None:
                self.last_blocked.append(decision)
                continue
            filtered.append((tactic, prob))

        return filtered

    def record_attempt(self, tactic: str, goal_sig: str, budget_key: str | None = None) -> None:
        if self.peg_budget is None:
            return
        if budget_key is None:
            raise ValueError("peg_budget requires budget_key")
        self._apply_budget(budget_key, tactic)

    def _match_rules(self, goal: LeanGoal, tactic: str, goal_sig: str) -> BlockedTactic | None:
        if not self.peg_rules:
            return None
        tactic_norm = normalize_tactic(tactic)
        family = tactic_family(tactic_norm)

        for rule in self.peg_rules:
            if rule.condition and not _goal_matches_condition(goal, rule.condition):
                continue
            if rule.blocked_tactics and self._matches_tactic(rule.blocked_tactics, tactic_norm):
                return BlockedTactic(
                    tactic=tactic,
                    tactic_norm=tactic_norm,
                    peg_id=rule.peg_id,
                    peg_kind=rule.kind.value,
                    block_reason="explicit",
                    goal_sig=goal_sig,
                    provider_id=self.provider_id,
                )
            if rule.blocked_families and family in rule.blocked_families:
                return BlockedTactic(
                    tactic=tactic,
                    tactic_norm=tactic_norm,
                    peg_id=rule.peg_id,
                    peg_kind=rule.kind.value,
                    block_reason="explicit",
                    goal_sig=goal_sig,
                    provider_id=self.provider_id,
                )
        return None

    def _match_budget(self, goal_sig: str, tactic: str, budget_id: str) -> BlockedTactic | None:
        if self.peg_budget is None:
            return None
        counter = self._budget_counts.get(budget_id)
        if counter is None:
            counter = _BudgetCounter()
            self._budget_counts[budget_id] = counter

        tactic_norm = normalize_tactic(tactic)
        family = tactic_family(tactic_norm)

        if self.peg_budget.max_total_attempts is not None:
            if counter.total >= self.peg_budget.max_total_attempts:
                return BlockedTactic(
                    tactic=tactic,
                    tactic_norm=tactic_norm,
                    peg_id=self.peg_budget.peg_id,
                    peg_kind=PegKind.BUDGET.value,
                    block_reason="budget_total",
                    goal_sig=goal_sig,
                    provider_id=self.provider_id,
                )

        if self.peg_budget.max_family_attempts is not None:
            family_count = counter.families.get(family, 0)
            if family_count >= self.peg_budget.max_family_attempts:
                return BlockedTactic(
                    tactic=tactic,
                    tactic_norm=tactic_norm,
                    peg_id=self.peg_budget.peg_id,
                    peg_kind=PegKind.BUDGET.value,
                    block_reason="budget_family",
                    goal_sig=goal_sig,
                    provider_id=self.provider_id,
                )

        return None

    def _apply_budget(self, budget_id: str, tactic: str) -> None:
        if self.peg_budget is None:
            return
        counter = self._budget_counts.get(budget_id)
        if counter is None:
            counter = _BudgetCounter()
            self._budget_counts[budget_id] = counter
        tactic_norm = normalize_tactic(tactic)
        family = tactic_family(tactic_norm)
        counter.total += 1
        counter.families[family] = counter.families.get(family, 0) + 1

    @staticmethod
    def _matches_tactic(blocked_tactics: frozenset[str], tactic_norm: str) -> bool:
        tactic_name = tactic_norm.split(" ", 1)[0]
        return tactic_name in blocked_tactics or tactic_norm in blocked_tactics
