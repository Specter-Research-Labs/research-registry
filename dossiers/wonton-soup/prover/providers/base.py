from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from leantree.core.lean import LeanGoal
from leantree.repl_adapter.interaction import LeanInteractionException

from prover.goal_signature import GoalSignatureConfig
from prover.goal_signature import goal_signature as _goal_signature

if TYPE_CHECKING:
    from prover.adapters.lean import LeanAdapter


def normalize_tactic(tactic: str) -> str:
    return " ".join(tactic.strip().split())


def tactic_family(tactic: str) -> str:
    tactic_norm = normalize_tactic(tactic)
    head = tactic_norm.split(" ", 1)[0].lower()
    base_head = head.rstrip("0123456789") or head

    if base_head in {"simp", "simp_all", "simp_rw"}:
        return "simplify"
    if base_head in {"rw", "rewrite"}:
        return "rewrite"
    if base_head in {"intro", "intros"}:
        return "intro"
    if base_head in {"constructor"}:
        return "split"
    if base_head in {"left", "right"}:
        return "split"
    if tactic_norm.startswith("apply And.intro") or tactic_norm.startswith("apply Iff.intro"):
        return "split"
    if tactic_norm.startswith("apply Or.inl") or tactic_norm.startswith("apply Or.inr"):
        return "split"
    if base_head == "use":
        return "split"
    if base_head in {"cases", "induction"}:
        return "cases"
    if base_head in {"exact", "assumption", "trivial"}:
        return "closer"
    if base_head in {"exfalso", "contradiction"}:
        return "contradiction"
    if base_head in {"linarith", "nlinarith", "omega", "ring", "norm_num"}:
        return "arith"
    if base_head in {"aesop", "aesop?"}:
        return "automation"
    return head


def goal_signature(goal: LeanGoal, config: GoalSignatureConfig) -> str:
    return _goal_signature(goal, config)




class TacticProvider(ABC):
    @abstractmethod
    async def suggest_tactics_with_probs_async(
        self,
        goal: LeanGoal,
        mvar_id: str,
        adapter: LeanAdapter,
        n: int = 10,
    ) -> list[tuple[str, float]]:
        raise NotImplementedError

    def describe(self) -> str:
        return self.__class__.__name__


class GoalAwareTacticProvider(TacticProvider):
    DEFAULT_TACTICS = [
        "rfl",
        "trivial",
        "decide",
        "simp",
        "simp only []",
        "ring",
        "linarith",
        "omega",
        "norm_num",
        "assumption",
        "constructor",
        "intro h",
        "intros",
        "cases h",
        "induction h",
        "apply And.intro",
        "apply Or.inl",
        "apply Or.inr",
        "exfalso",
        "contradiction",
        "ext",
        "funext",
        "congr",
        "rw []",
        "simp_all",
    ]

    SLOW_TACTICS = [
        "exact?",
        "aesop",
    ]

    def __init__(self, base_tactics: list[str] | None = None, include_slow: bool = False):
        self.base_tactics = base_tactics if base_tactics is not None else self.DEFAULT_TACTICS
        if include_slow:
            self.base_tactics = self.base_tactics + self.SLOW_TACTICS
        self.last_latency_ms: float | None = None
        self.avg_latency_ms: float | None = None

    def _record_stats(self, start_time: float) -> None:
        elapsed_ms = (time.time() - start_time) * 1000
        self.last_latency_ms = elapsed_ms
        if self.avg_latency_ms is None:
            self.avg_latency_ms = elapsed_ms
        else:
            self.avg_latency_ms = (self.avg_latency_ms * 0.9) + (elapsed_ms * 0.1)

    async def suggest_tactics_with_probs_async(
        self,
        goal: LeanGoal,
        mvar_id: str,
        adapter: LeanAdapter,
        n: int = 10,
    ) -> list[tuple[str, float]]:
        start_time = time.time()
        candidates = self._generate_candidates(goal)
        if not candidates:
            return []
        scored = self._score_and_select(goal, candidates, n)
        self._record_stats(start_time)
        return scored

    def _generate_tactics(self, goal: LeanGoal, n: int) -> list[str]:
        scored = self._score_and_select(goal, self._generate_candidates(goal), n)
        return [t for t, _ in scored]

    def _generate_candidates(self, goal: LeanGoal) -> list[str]:
        tactics = []
        goal_type = goal.type.strip()

        def _has_or(s: str) -> bool:
            return ("\u2228" in s) or ("Or" in s) or ("\\/" in s)

        def _has_and(s: str) -> bool:
            return ("\u2227" in s) or ("And" in s) or ("/\\" in s)

        def _has_exists(s: str) -> bool:
            return ("\u2203" in s) or ("Exists" in s)

        def _has_forall_prefix(s: str) -> bool:
            return s.startswith("forall") or s.startswith("\u2200")

        def _has_imp(s: str) -> bool:
            return ("\u2192" in s) or ("->" in s)

        goal_has_or = _has_or(goal_type)

        for hyp in goal.hypotheses:
            hyp_name = hyp.user_name
            hyp_type = hyp.type
            if _has_or(hyp_type):
                tactics.append(f"cases {hyp_name}")
                tactics.append(f"rcases {hyp_name} with h1 | h2")

        if goal_type == "True":
            tactics.append("trivial")

        if "=" in goal_type:
            tactics.extend(["rfl", "ring", "simp", "norm_num"])

        if _has_forall_prefix(goal_type):
            tactics.extend(["intro", "intros"])

        if _has_imp(goal_type):
            tactics.extend(["intro", "intro h"])

        if _has_and(goal_type):
            tactics.append("constructor")

        if "\u2194" in goal_type or "<->" in goal_type or "Iff" in goal_type:
            tactics.append("constructor")

        if goal_has_or:
            tactics.extend(["left", "apply Or.inl", "right", "apply Or.inr"])

        if _has_exists(goal_type):
            tactics.extend(["use 1", "use 0", "use []", "refine \u27e8_, ?_\u27e9"])

        if goal_type == "False":
            tactics.extend(["exfalso", "contradiction"])
        elif "\u00ac" in goal_type or "Not" in goal_type:
            tactics.append("intro h")

        if (
            "Nat" in goal_type
            or "Int" in goal_type
            or "\u2115" in goal_type
            or "\u2124" in goal_type
        ):
            tactics.extend(["omega", "linarith", "norm_num"])

        for hyp in goal.hypotheses:
            hyp_name = hyp.user_name
            hyp_type = hyp.type.strip()

            if hyp_type == goal_type:
                tactics.insert(0, f"exact {hyp_name}")
                tactics.insert(0, "assumption")

            if "=" in hyp_type:
                tactics.append(f"rw [{hyp_name}]")
                tactics.append(f"rw [<- {hyp_name}]")
                tactics.append(f"simp [{hyp_name}]")
                tactics.append(f"simp [<- {hyp_name}]")

            if _has_imp(hyp_type):
                tactics.append(f"apply {hyp_name}")
                if "False" in hyp_type or goal_type == "False":
                    tactics.insert(0, f"apply {hyp_name}")

            if _has_and(hyp_type):
                tactics.append(f"obtain \u27e8h1, h2\u27e9 := {hyp_name}")
                tactics.append(f"rcases {hyp_name} with \u27e8h1, h2\u27e9")

            if _has_exists(hyp_type):
                tactics.append(f"obtain \u27e8w, hw\u27e9 := {hyp_name}")
                tactics.append(f"rcases {hyp_name} with \u27e8w, hw\u27e9")

        has_h = any(h.user_name == "h" for h in goal.hypotheses)
        for tactic in self.base_tactics:
            if tactic in {"cases h", "induction h"} and not has_h:
                continue
            if tactic not in tactics:
                tactics.append(tactic)

        seen = set()
        unique_tactics = []
        for t in tactics:
            if t not in seen:
                seen.add(t)
                unique_tactics.append(t)

        return unique_tactics

    def _score_and_select(
        self, goal: LeanGoal, candidates: list[str], n: int
    ) -> list[tuple[str, float]]:
        goal_type = goal.type.strip()
        hyp_names = {h.user_name for h in goal.hypotheses}
        hyp_types = [h.type for h in goal.hypotheses]

        def has_or(s: str) -> bool:
            return ("\u2228" in s) or ("Or" in s) or ("\\/" in s)

        def has_and(s: str) -> bool:
            return ("\u2227" in s) or ("And" in s) or ("/\\" in s)

        def has_exists(s: str) -> bool:
            return ("\u2203" in s) or ("Exists" in s)

        def is_arith(s: str) -> bool:
            return ("Nat" in s) or ("Int" in s) or ("\u2115" in s) or ("\u2124" in s)

        goal_has_eq = "=" in goal_type
        goal_has_or = has_or(goal_type)
        goal_has_and = has_and(goal_type)
        goal_has_exists = has_exists(goal_type)
        goal_has_forall = goal_type.startswith("forall") or goal_type.startswith("\u2200")
        goal_has_imp = ("\u2192" in goal_type) or ("->" in goal_type)
        goal_is_arith = is_arith(goal_type)

        def score(tactic: str) -> int:
            t = normalize_tactic(tactic)
            head = t.split(" ", 1)[0].lower()
            fam = tactic_family(t)

            s = 10

            if head in {"assumption", "rfl", "trivial", "decide", "native_decide"}:
                s = 120
            elif head == "exact":
                s = 110
            elif fam == "contradiction":
                is_neg = ("False" in goal_type) or ("\u00ac" in goal_type) or ("Not" in goal_type)
                s = 100 if is_neg else 40
            elif fam == "intro":
                is_intro_goal = (
                    goal_has_forall
                    or goal_has_imp
                    or ("\u00ac" in goal_type)
                    or ("Not" in goal_type)
                )
                s = 95 if is_intro_goal else 45
            elif fam == "split":
                if head in {"left", "right"} or t.startswith("apply Or."):
                    s = 95 if goal_has_or else 35
                else:
                    s = 95 if (goal_has_and or "Iff" in goal_type or "<->" in goal_type) else 35
            elif fam == "cases":
                wants = goal_has_or or any(has_or(ht) for ht in hyp_types)
                s = 85 if wants else 35
            elif fam == "simplify":
                is_structured = (
                    goal_has_eq
                    or goal_is_arith
                    or goal_has_and
                    or goal_has_or
                    or goal_has_exists
                )
                s = 80 if is_structured else 55
                if head == "simp_only":
                    s -= 5
            elif fam == "rewrite":
                s = 78 if goal_has_eq else 55
            elif fam == "arith":
                s = 95 if goal_is_arith else 50
                if head == "ring" and not goal_has_eq:
                    s -= 20
            elif head == "apply":
                s = 70
            elif fam == "automation":
                s = 45

            if head in {"cases", "induction", "rcases", "obtain"}:
                parts = t.split(" ", 2)
                if len(parts) >= 2 and parts[1] in hyp_names:
                    s += 10
                else:
                    s -= 15
            if head in {"rw", "simp"} and "[" in t and "]" in t:
                inside = t.split("[", 1)[1].split("]", 1)[0]
                for token in inside.replace("<-", " ").replace(",", " ").split():
                    if token in hyp_names:
                        s += 8
                        break

            if head == "use":
                s = 85 if goal_has_exists else 35

            return s

        weighted: list[tuple[str, int, int]] = []
        for i, t in enumerate(candidates):
            w = score(t)
            if w <= 0:
                w = 1
            weighted.append((t, w, i))

        weighted.sort(key=lambda x: (-x[1], x[2]))
        top = weighted[:n]
        total = sum(w for _, w, _ in top)
        if total <= 0:
            return []
        return [(t, (w / total)) for t, w, _ in top]


class AesopTacticProvider(TacticProvider):
    def __init__(self, search_tactic: str = "aesop?"):
        self.search_tactic = search_tactic

    def describe(self) -> str:
        return f"{self.__class__.__name__}(search={self.search_tactic})"

    async def suggest_tactics_with_probs_async(
        self,
        goal: LeanGoal,
        mvar_id: str,
        adapter: LeanAdapter,
        n: int = 10,
    ) -> list[tuple[str, float]]:
        try:
            suggestions = await adapter.get_tactic_suggestions(mvar_id, self.search_tactic)
        except LeanInteractionException as exc:
            goal_type = goal.type.strip()
            raise RuntimeError(
                f"{self.search_tactic} failed for {mvar_id} ({goal_type}). Lean reported: {exc}"
            ) from exc
        if not suggestions:
            return []
        trimmed = suggestions[:n]
        uniform_prob = 1.0 / len(trimmed)
        return [(tactic, uniform_prob) for tactic in trimmed]
