#!/usr/bin/env python3
"""
Analyze failed theorems from corpus experiments.

Examines MCTS trees and history files to understand why certain theorems failed.
Categorizes failures by:
- Tactic desert: No applicable tactics found (node immediately dead)
- Search exhaustion: Budget consumed without finding solution
- Model hallucination: Model generates nonsensical/repetitive tactics

Usage:
    python analyze_failures.py logs/corpus-2025-12-28-232439/
"""

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class FailurePattern(Enum):
    TACTIC_DESERT = "TACTIC_DESERT"
    SEARCH_EXHAUSTION = "SEARCH_EXHAUSTION"
    MODEL_HALLUCINATION = "MODEL_HALLUCINATION"
    PARTIAL_PROGRESS = "PARTIAL_PROGRESS"
    UNKNOWN = "UNKNOWN"


TECHNIQUE_HINTS: dict[str, str] = {
    "add_assoc_nat": "automation",
    "list_length_append": "induction",
    "or_comm": "case_analysis",
    "de_morgan_not_and": "intro_elim",
    "de_morgan_not_or": "intro_elim",
    "and_or_distrib": "case_analysis",
    "or_and_distrib": "case_analysis",
    "false_elim": "absurdity",
    "forall_trivial": "intro_elim",
    "set_union_comm": "extensionality",
    "set_inter_comm": "extensionality",
    "logic_chain": "intro_elim",
    "imp_trans": "intro_elim",
}


CORRECT_TACTICS: dict[str, list[str]] = {
    "false_elim": ["exact False.elim hf", "cases hf", "contradiction", "exfalso"],
    "or_comm": ["cases h", "rcases h", "cases h with hp hq", "Or.comm.mp h"],
    "or_and_distrib": ["cases h", "rcases h", "Or.rec"],
    "and_or_distrib": ["obtain ⟨hp, h⟩ := h", "rcases h", "cases h.2"],
    "forall_trivial": ["intro", "intros", "fun n =>"],
    "set_union_comm": ["ext", "Set.union_comm", "funext"],
    "set_inter_comm": ["ext", "Set.inter_comm", "funext"],
    "de_morgan_not_and": ["intro hq", "fun hq =>"],
    "add_assoc_nat": ["ring", "omega", "Nat.add_assoc"],
    "list_length_append": ["induction l1", "List.length_append", "simp"],
    "logic_chain": ["apply hqr", "exact hqr (hpq hp)"],
    "imp_trans": ["intro hp", "fun hp =>"],
}


@dataclass
class FailedTheorem:
    name: str
    goal_type: str
    total_iterations: int
    total_attempts: int
    success_count: int
    failure_count: int
    blocked_count: int
    failure_ratio: float
    repeat_ratio: float
    unique_tactics_tried: int
    all_tactics_failed: bool
    max_depth_reached: int
    node_count: int
    is_dead: bool
    failure_pattern: FailurePattern
    technique_hint: str | None
    tactics_attempted: list[str] = field(default_factory=list)
    tactic_patterns: dict[str, int] = field(default_factory=dict)


def extract_tactic_base(tactic: str) -> str:
    normalized = re.sub(r"\s+", " ", tactic.strip())
    if " " in normalized:
        first_word = normalized.split()[0]
        if first_word in {"cases", "cases'", "rcases", "obtain", "induction"}:
            return first_word
        return normalized[:50]
    return normalized


def analyze_tactic_patterns(tactics: list[str]) -> dict[str, int]:
    base_tactics = [extract_tactic_base(t) for t in tactics]
    return dict(Counter(base_tactics).most_common(10))


HALLUCINATION_REPEAT_RATIO = 0.7
MAX_COMBINATOR_DEPTH = 3
MAX_CASES_DEPTH = 3


def detect_hallucination(tactics: list[str]) -> bool:
    if len(tactics) < 3:
        return False

    base_tactics = [extract_tactic_base(t) for t in tactics]
    counter = Counter(base_tactics)
    most_common_base, count = counter.most_common(1)[0]
    if count >= len(tactics) * HALLUCINATION_REPEAT_RATIO:
        return True

    for tactic in tactics:
        if tactic.count("<;>") > MAX_COMBINATOR_DEPTH:
            return True
        if tactic.count("cases'") > MAX_CASES_DEPTH:
            return True

    return False


def classify_failure(
    tactics: list[str],
    total_attempts: int,
    success_count: int,
    max_depth: int,
) -> FailurePattern:
    if total_attempts == 0:
        return FailurePattern.TACTIC_DESERT

    if detect_hallucination(tactics):
        return FailurePattern.MODEL_HALLUCINATION

    if max_depth > 0:
        return FailurePattern.PARTIAL_PROGRESS

    if success_count == 0:
        return FailurePattern.TACTIC_DESERT

    return FailurePattern.SEARCH_EXHAUSTION


def analyze_failed_theorem(theorem_dir: Path) -> FailedTheorem | None:
    history_path = theorem_dir / "wild_type_history.json"
    tree_path = theorem_dir / "wild_type_mcts_tree.json"
    metrics_path = theorem_dir / "wild_type_metrics.json"

    if not history_path.exists() or not tree_path.exists():
        return None

    with open(history_path) as f:
        history = json.load(f)
    with open(tree_path) as f:
        tree = json.load(f)

    metrics = {}
    if metrics_path.exists():
        with open(metrics_path) as f:
            metrics = json.load(f)

    trajectory = metrics.get("trajectory", {})
    if trajectory.get("depth_at_solution", 0) > 0:
        return None

    iterations = history.get("iterations", [])
    attempts = [a for it in iterations for a in it.get("attempts", [])]
    all_tactics: list[str] = []
    for attempt in attempts:
        tactic = attempt.get("tactic", "")
        if tactic:
            all_tactics.append(tactic)

    total_attempts = len(attempts)
    success_count = sum(1 for a in attempts if a.get("outcome") == "success")
    failure_count = sum(1 for a in attempts if a.get("outcome") == "failure")
    blocked_count = sum(1 for a in attempts if a.get("outcome") == "blocked")
    failure_ratio = failure_count / total_attempts if total_attempts > 0 else 0.0
    base_tactics = [extract_tactic_base(t) for t in all_tactics]
    repeat_ratio = 0.0
    if base_tactics:
        repeat_ratio = Counter(base_tactics).most_common(1)[0][1] / len(base_tactics)

    all_failed = total_attempts > 0 and failure_count == total_attempts

    nodes = tree.get("nodes", {})
    root_id = tree.get("root_mvar_id", "")
    root_node = nodes.get(root_id, {})
    goal_type = root_node.get("goal_type", "")
    max_depth = max((n.get("depth", 0) for n in nodes.values()), default=0)

    failure_pattern = classify_failure(
        all_tactics, total_attempts, success_count, max_depth
    )
    technique_hint = TECHNIQUE_HINTS.get(theorem_dir.name)

    return FailedTheorem(
        name=theorem_dir.name,
        goal_type=goal_type,
        total_iterations=len(iterations),
        total_attempts=total_attempts,
        success_count=success_count,
        failure_count=failure_count,
        blocked_count=blocked_count,
        failure_ratio=round(failure_ratio, 3),
        repeat_ratio=round(repeat_ratio, 3),
        unique_tactics_tried=len(set(base_tactics)),
        all_tactics_failed=all_failed,
        max_depth_reached=max_depth,
        node_count=len(nodes),
        is_dead=root_node.get("is_dead", False),
        failure_pattern=failure_pattern,
        technique_hint=technique_hint,
        tactics_attempted=all_tactics[:20],
        tactic_patterns=analyze_tactic_patterns(all_tactics),
    )


def generate_report(failures: list[FailedTheorem], log_dir: Path) -> dict:
    by_pattern = {}
    for pattern in FailurePattern:
        by_pattern[pattern.value] = [f for f in failures if f.failure_pattern == pattern]

    return {
        "log_dir": str(log_dir),
        "total_failures": len(failures),
        "by_pattern": {
            pattern: len(items) for pattern, items in by_pattern.items() if items
        },
        "failures": [
            {
                "name": f.name,
                "goal_type": f.goal_type,
                "failure_pattern": f.failure_pattern.value,
                "total_iterations": f.total_iterations,
                "total_attempts": f.total_attempts,
                "success_count": f.success_count,
                "failure_count": f.failure_count,
                "blocked_count": f.blocked_count,
                "failure_ratio": f.failure_ratio,
                "repeat_ratio": f.repeat_ratio,
                "unique_tactics_tried": f.unique_tactics_tried,
                "all_tactics_failed": f.all_tactics_failed,
                "max_depth_reached": f.max_depth_reached,
                "node_count": f.node_count,
                "is_dead": f.is_dead,
                "technique_hint": f.technique_hint,
                "tactic_patterns": f.tactic_patterns,
                "sample_tactics": f.tactics_attempted[:5],
                "correct_tactics": CORRECT_TACTICS.get(f.name, []),
            }
            for f in failures
        ],
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_failures.py <log_dir>")
        sys.exit(1)

    log_dir = Path(sys.argv[1])
    if not log_dir.exists():
        print(f"Error: {log_dir} does not exist")
        sys.exit(1)

    failures: list[FailedTheorem] = []
    for theorem_dir in sorted(log_dir.iterdir()):
        if not theorem_dir.is_dir() or theorem_dir.name.startswith("."):
            continue

        result = analyze_failed_theorem(theorem_dir)
        if result is not None:
            failures.append(result)

    if not failures:
        print("No failed theorems found in", log_dir)
        sys.exit(0)

    report = generate_report(failures, log_dir)

    report_path = log_dir / "failure_analysis.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Analyzed {len(failures)} failed theorems")
    print("Results saved to:")
    print(f"  {report_path}")
    print()
    print("Summary by pattern:")
    for pattern, count in report["by_pattern"].items():
        print(f"  {pattern}: {count}")


if __name__ == "__main__":
    main()
