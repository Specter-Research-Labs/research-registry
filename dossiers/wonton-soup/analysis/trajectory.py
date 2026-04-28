from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prover.history import ExplorationHistory
    from prover.mcts import MCTSTree


@dataclass
class TrajectoryComparison:
    wild_solution_goal_sigs: list[str]
    intervention_goal_sequence: list[str]
    divergence_iteration: int | None
    reconvergence_iteration: int | None
    recovery_iterations: int | None
    shared_prefix_length: int
    reconverged: bool

    def serialize(self) -> dict:
        return {
            "wild_solution_goal_sigs": self.wild_solution_goal_sigs,
            "intervention_goal_sequence": self.intervention_goal_sequence,
            "divergence_iteration": self.divergence_iteration,
            "reconvergence_iteration": self.reconvergence_iteration,
            "recovery_iterations": self.recovery_iterations,
            "shared_prefix_length": self.shared_prefix_length,
            "reconverged": self.reconverged,
        }


def extract_solution_goal_sigs(
    solution_path: list[dict],
    mcts_tree: MCTSTree,
) -> list[str]:
    goal_sigs = []
    for step in solution_path:
        mvar_id = step.get("mvar_id")
        if mvar_id is None:
            continue
        node = mcts_tree.nodes_by_mvar.get(mvar_id)
        if node and node.goal_sig:
            goal_sigs.append(node.goal_sig)
    return goal_sigs


def _selected_goal_sequence(
    history: ExplorationHistory,
    tree: MCTSTree,
) -> list[tuple[int, str]]:
    sequence: list[tuple[int, str]] = []
    for record in history.iterations:
        if not record.selected_path:
            continue
        mvar_id = record.selected_path[-1]
        node = tree.nodes_by_mvar.get(mvar_id)
        if node is None or not node.goal_sig:
            continue
        sequence.append((record.iteration, node.goal_sig))
    return sequence


def _find_reconvergence(
    wild_solution_goal_sigs: list[str],
    int_sigs: list[str],
    start_idx: int,
) -> int | None:
    for i in range(start_idx, len(int_sigs)):
        suffix = int_sigs[i:]
        for j in range(len(wild_solution_goal_sigs)):
            if wild_solution_goal_sigs[j:] == suffix:
                return i
    return None


def compare_trajectories(
    wild_solution_goal_sigs: list[str],
    intervention_history: ExplorationHistory,
    intervention_tree: MCTSTree,
) -> TrajectoryComparison:
    int_sequence = _selected_goal_sequence(intervention_history, intervention_tree)
    int_sigs = [sig for _, sig in int_sequence]

    shared_prefix = 0
    divergence_iter = None
    divergence_idx = None

    for idx, sig in enumerate(int_sigs):
        if idx >= len(wild_solution_goal_sigs) or sig != wild_solution_goal_sigs[idx]:
            divergence_idx = idx
            divergence_iter = int_sequence[idx][0]
            break
        shared_prefix += 1

    reconvergence_iter = None
    reconvergence_idx = None
    if divergence_idx is not None:
        reconvergence_idx = _find_reconvergence(wild_solution_goal_sigs, int_sigs, divergence_idx)
        if reconvergence_idx is not None:
            reconvergence_iter = int_sequence[reconvergence_idx][0]

    recovery = None
    if divergence_iter is not None and reconvergence_iter is not None:
        recovery = reconvergence_iter - divergence_iter

    reconverged = reconvergence_iter is not None

    return TrajectoryComparison(
        wild_solution_goal_sigs=wild_solution_goal_sigs,
        intervention_goal_sequence=int_sigs,
        divergence_iteration=divergence_iter,
        reconvergence_iteration=reconvergence_iter,
        recovery_iterations=recovery,
        shared_prefix_length=shared_prefix,
        reconverged=reconverged,
    )
