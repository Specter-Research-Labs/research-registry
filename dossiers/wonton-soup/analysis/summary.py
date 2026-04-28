from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from analysis.logs import ged_value, read_json_auto


@dataclass
class InterventionData:
    name: str
    blocked: list[str]
    solved: bool
    ged: float | None
    axiom_delta: list[str] | None
    axiom_removed: list[str] | None
    is_control: bool
    baseline_solved: bool
    metrics: dict

    @property
    def blocked_count(self) -> int:
        return self.metrics.get("detour", {}).get("blocked_count", 0)

    @property
    def is_active_block(self) -> bool:
        return self.blocked_count > 0

    @property
    def has_axiom_change(self) -> bool:
        return bool(self.axiom_delta) or bool(self.axiom_removed)


@dataclass
class TheoremData:
    name: str
    wild_type_solved: bool
    wild_type_iterations: int
    wild_type_hash: str | None
    wild_type_metrics: dict
    interventions: list[InterventionData]


@dataclass
class CorpusRun:
    run_id: str
    theorems: list[TheoremData]
    aggregates: dict
    log_dir: Path

    @classmethod
    def load(cls, log_dir: Path) -> CorpusRun:
        summary_gz = log_dir / "summary.json.gz"
        summary_path = log_dir / "summary.json"
        if summary_gz.exists():
            data = read_json_auto(summary_gz)
        elif summary_path.exists():
            data = read_json_auto(summary_path)
        else:
            raise FileNotFoundError(f"No summary.json in {log_dir}")

        theorems = []
        for t in data["theorems"]:
            interventions = [
                InterventionData(
                    name=i["name"],
                    blocked=i["blocked"],
                    solved=i["solved"],
                    ged=ged_value(i.get("ged_search_graph")),
                    axiom_delta=i.get("axiom_delta"),
                    axiom_removed=i.get("axiom_removed"),
                    is_control=i.get("is_control", False),
                    baseline_solved=i.get("baseline_solved", True),
                    metrics=i["metrics"],
                )
                for i in t["interventions"]
            ]
            theorems.append(
                TheoremData(
                    name=t["name"],
                    wild_type_solved=t["wild_type"]["solved"],
                    wild_type_iterations=t["wild_type"]["iterations"],
                    wild_type_hash=t["wild_type"]["proof_term_hash"],
                    wild_type_metrics=t["wild_type"]["metrics"],
                    interventions=interventions,
                )
            )

        return cls(
            run_id=data["run_id"],
            theorems=theorems,
            aggregates=data["aggregates"],
            log_dir=log_dir,
        )


def load_corpus_run(log_dir: Path | str) -> CorpusRun:
    return CorpusRun.load(Path(log_dir))


def tactic_replaceability(run: CorpusRun) -> dict[str, dict[str, list[str]]]:
    matrix = run.aggregates.get("goal_type_tactic_matrix", {})
    result: dict[str, dict[str, list[str]]] = {}

    for goal_type, tactics in matrix.items():
        result[goal_type] = {}
        blocked_tactics = set()
        successful_tactics = []

        for tactic, counts in tactics.items():
            if counts.get("blocked", 0) > 0:
                blocked_tactics.add(tactic)
            if counts.get("success", 0) > 0:
                successful_tactics.append(tactic)

        for blocked in blocked_tactics:
            replacements = [t for t in successful_tactics if t != blocked]
            if replacements:
                result[goal_type][blocked] = replacements

    return result


def structure_vs_semantics(run: CorpusRun) -> dict:
    categories = {
        "same_structure_axiom_same": [],
        "same_structure_axiom_changed": [],
        "diff_structure_axiom_same": [],
        "diff_structure_axiom_changed": [],
        "missing_axiom_data": [],
    }

    for theorem in run.theorems:
        for intervention in theorem.interventions:
            if intervention.is_control or not intervention.baseline_solved:
                continue
            if not intervention.solved:
                continue
            if intervention.ged is None:
                continue

            same_structure = intervention.ged == 0
            if intervention.axiom_delta is None and intervention.axiom_removed is None:
                categories["missing_axiom_data"].append(
                    {
                        "theorem": theorem.name,
                        "intervention": intervention.name,
                        "ged": intervention.ged,
                    }
                )
                continue

            axiom_changed = intervention.has_axiom_change
            struct_str = "same" if same_structure else "diff"
            axiom_str = "changed" if axiom_changed else "same"
            key = f"{struct_str}_structure_axiom_{axiom_str}"
            categories[key].append(
                {
                    "theorem": theorem.name,
                    "intervention": intervention.name,
                    "ged": intervention.ged,
                    "axiom_delta": intervention.axiom_delta,
                    "axiom_removed": intervention.axiom_removed,
                }
            )

    totals = {k: len(v) for k, v in categories.items()}
    return {"categories": categories, "counts": totals}


def goal_type_patterns(run: CorpusRun) -> dict[str, dict[str, float]]:
    matrix = run.aggregates.get("goal_type_tactic_matrix", {})
    result: dict[str, dict[str, float]] = {}

    for goal_type, tactics in matrix.items():
        result[goal_type] = {}
        for tactic, counts in tactics.items():
            success = counts.get("success", 0)
            failure = counts.get("failure", 0)
            total = success + failure
            if total > 0:
                result[goal_type][tactic] = success / total

    return result


def proof_term_clusters(run: CorpusRun) -> list[list[str]]:
    hash_to_theorems: dict[str, list[str]] = {}

    for theorem in run.theorems:
        if theorem.wild_type_hash:
            if theorem.wild_type_hash not in hash_to_theorems:
                hash_to_theorems[theorem.wild_type_hash] = []
            hash_to_theorems[theorem.wild_type_hash].append(theorem.name)

    clusters: list[list[str]] = [
        theorems for theorems in hash_to_theorems.values() if len(theorems) > 1
    ]
    clusters.sort(key=len, reverse=True)
    return clusters


def trajectory_analysis(run: CorpusRun) -> dict:
    comparisons = []

    for theorem in run.theorems:
        if not theorem.wild_type_solved:
            continue

        wild_trajectory = theorem.wild_type_metrics.get("trajectory", {})

        for intervention in theorem.interventions:
            if intervention.is_control or not intervention.baseline_solved:
                continue
            if not intervention.solved:
                continue

            int_trajectory = intervention.metrics.get("trajectory", {})

            comparisons.append(
                {
                    "theorem": theorem.name,
                    "intervention": intervention.name,
                    "blocked": intervention.blocked,
                    "wild_iterations": wild_trajectory.get("total_iterations", 0),
                    "int_iterations": int_trajectory.get("total_iterations", 0),
                    "wild_backtracks": wild_trajectory.get("backtrack_count", 0),
                    "int_backtracks": int_trajectory.get("backtrack_count", 0),
                    "wild_tactic_diversity": wild_trajectory.get("tactic_diversity", 0),
                    "int_tactic_diversity": int_trajectory.get("tactic_diversity", 0),
                    "iteration_delta": int_trajectory.get("total_iterations", 0)
                    - wild_trajectory.get("total_iterations", 0),
                    "backtrack_delta": int_trajectory.get("backtrack_count", 0)
                    - wild_trajectory.get("backtrack_count", 0),
                }
            )

    avg_iteration_delta = (
        sum(c["iteration_delta"] for c in comparisons) / len(comparisons) if comparisons else 0
    )
    avg_backtrack_delta = (
        sum(c["backtrack_delta"] for c in comparisons) / len(comparisons) if comparisons else 0
    )

    return {
        "comparisons": comparisons,
        "summary": {
            "count": len(comparisons),
            "avg_iteration_delta": avg_iteration_delta,
            "avg_backtrack_delta": avg_backtrack_delta,
        },
    }


def find_latest_corpus(logs_dir: Path) -> Path | None:
    corpus_dirs = sorted(
        [d for d in logs_dir.iterdir() if d.is_dir() and d.name.startswith("corpus-")],
        key=lambda d: d.name,
        reverse=True,
    )
    return corpus_dirs[0] if corpus_dirs else None


def convergence_summary(run: CorpusRun) -> dict:
    total = 0
    ged_zero = 0
    failed = 0
    axiom_changed = 0
    axiom_measured = 0
    ged_measured = 0
    control_total = 0
    control_solved = 0
    baseline_failed_total = 0
    baseline_failed_solved = 0

    for theorem in run.theorems:
        for intervention in theorem.interventions:
            if intervention.is_control:
                control_total += 1
                if intervention.solved:
                    control_solved += 1
                continue
            if not intervention.baseline_solved:
                baseline_failed_total += 1
                if intervention.solved:
                    baseline_failed_solved += 1
                continue

            total += 1
            if not intervention.solved:
                failed += 1
            elif intervention.ged is not None:
                ged_measured += 1
                if intervention.ged == 0:
                    ged_zero += 1
            if intervention.axiom_delta is not None or intervention.axiom_removed is not None:
                axiom_measured += 1
                if intervention.has_axiom_change:
                    axiom_changed += 1

    solved = total - failed
    return {
        "total_interventions": total,
        "solved": solved,
        "failed": failed,
        "ged_zero": ged_zero,
        "structural_convergence_rate": ged_zero / ged_measured if ged_measured > 0 else 0,
        "axiom_change_count": axiom_changed,
        "axiom_change_rate": axiom_changed / axiom_measured if axiom_measured > 0 else 0,
        "control": {
            "total": control_total,
            "solved": control_solved,
            "solve_rate": control_solved / control_total if control_total > 0 else 0,
        },
        "baseline_failed": {
            "total": baseline_failed_total,
            "solved": baseline_failed_solved,
            "solve_rate": (
                baseline_failed_solved / baseline_failed_total
                if baseline_failed_total > 0
                else 0
            ),
        },
    }


def active_block_summary(run: CorpusRun) -> dict:
    active_interventions: list[tuple[TheoremData, InterventionData]] = []

    for theorem in run.theorems:
        for intervention in theorem.interventions:
            if intervention.is_control or not intervention.baseline_solved:
                continue
            if intervention.is_active_block:
                active_interventions.append((theorem, intervention))

    if not active_interventions:
        return {
            "total": 0,
            "solved": 0,
            "failed": 0,
            "solve_rate": 0.0,
            "ged_zero": 0,
            "ged_nonzero": 0,
            "structural_convergence_rate": 0.0,
            "avg_ged": 0.0,
            "details": [],
        }

    solved_active = [(t, i) for t, i in active_interventions if i.solved]
    failed_active = [(t, i) for t, i in active_interventions if not i.solved]
    ged_zero = sum(1 for _, i in solved_active if i.ged is not None and i.ged == 0)
    ged_nonzero = sum(1 for _, i in solved_active if i.ged is not None and i.ged > 0)
    total_ged = sum(i.ged for _, i in solved_active if i.ged is not None)

    details = []
    for theorem, intervention in active_interventions:
        wild_iter = theorem.wild_type_iterations if theorem.wild_type_solved else None
        int_iter = intervention.metrics.get("trajectory", {}).get("total_iterations")
        details.append({
            "theorem": theorem.name,
            "intervention": intervention.name,
            "blocked": intervention.blocked,
            "blocked_count": intervention.blocked_count,
            "solved": intervention.solved,
            "ged": intervention.ged if intervention.solved else None,
            "wild_iterations": wild_iter,
            "int_iterations": int_iter,
            "iteration_delta": (
                int_iter - wild_iter
                if int_iter is not None and wild_iter is not None
                else None
            ),
        })

    n_solved = len(solved_active)
    ged_count = sum(1 for _, i in solved_active if i.ged is not None)
    return {
        "total": len(active_interventions),
        "solved": n_solved,
        "failed": len(failed_active),
        "solve_rate": n_solved / len(active_interventions),
        "ged_zero": ged_zero,
        "ged_nonzero": ged_nonzero,
        "structural_convergence_rate": ged_zero / ged_count if ged_count > 0 else 0.0,
        "avg_ged": total_ged / ged_count if ged_count > 0 else 0.0,
        "details": details,
    }


def generate_report(run: CorpusRun) -> str:
    lines = [f"# Convergence Analysis: {run.run_id}\n"]

    summary = convergence_summary(run)
    lines.append("## Summary\n")
    lines.append(f"- Theorems: {len(run.theorems)}")
    lines.append(f"- Total interventions: {summary['total_interventions']}")
    lines.append(f"- Solved: {summary['solved']}")
    lines.append(f"- Failed: {summary['failed']}")
    lines.append(f"- GED = 0 (structurally identical): {summary['ged_zero']}")
    lines.append(f"- **Structural convergence rate: {summary['structural_convergence_rate']:.1%}**")
    lines.append(f"- **Axiom change rate: {summary['axiom_change_rate']:.1%}**")

    ctrl = summary["control"]
    if ctrl["total"] > 0:
        lines.append(
            f"- Control interventions: {ctrl['solved']}/{ctrl['total']} "
            f"({ctrl['solve_rate']:.1%})"
        )

    bf = summary["baseline_failed"]
    if bf["total"] > 0:
        lines.append(
            f"- Baseline-failed interventions: {bf['solved']}/{bf['total']} "
            f"({bf['solve_rate']:.1%})"
        )
    lines.append("")

    active = active_block_summary(run)
    if active["total"] > 0:
        lines.append("## Active Blocks Only\n")
        lines.append("Interventions where blocked tactics were actually attempted:\n")
        lines.append(f"- Active interventions: {active['total']}")
        lines.append(f"- Solved: {active['solved']}")
        lines.append(f"- Failed: {active['failed']}")
        lines.append(f"- **Solve rate: {active['solve_rate']:.1%}**")
        lines.append(f"- GED = 0: {active['ged_zero']}")
        lines.append(f"- GED > 0 (reorganization): {active['ged_nonzero']}")
        lines.append(f"- Structural convergence rate: {active['structural_convergence_rate']:.1%}")
        lines.append(f"- Avg GED (solved): {active['avg_ged']:.2f}\n")

        lines.append("| Theorem | Intervention | Blocked | Count | Solved | GED | Iter Delta |")
        lines.append("|---------|--------------|---------|-------|--------|-----|------------|")
        for d in active["details"]:
            ged_str = f"{d['ged']:.1f}" if d["ged"] is not None else "-"
            delta_str = f"{d['iteration_delta']:+d}" if d["iteration_delta"] is not None else "-"
            blocked_str = ", ".join(d["blocked"][:2])
            if len(d["blocked"]) > 2:
                blocked_str += "..."
            row = (
                f"| {d['theorem']} | {d['intervention']} | {blocked_str} "
                f"| {d['blocked_count']} | {d['solved']} | {ged_str} | {delta_str} |"
            )
            lines.append(row)
        lines.append("")

    struct_sem = structure_vs_semantics(run)
    lines.append("## Structure vs Semantics\n")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    for key, count in struct_sem["counts"].items():
        label = key.replace("_", " ").title()
        lines.append(f"| {label} | {count} |")
    lines.append("")

    lines.append("## Per-Theorem Results\n")
    lines.append("| Theorem | Wild Solved | Interventions | GED=0 | Axiom Δ |")
    lines.append("|---------|-------------|---------------|-------|---------|")

    for theorem in run.theorems:
        n_int = len(theorem.interventions)
        n_ged0 = sum(
            1 for i in theorem.interventions if i.solved and i.ged is not None and i.ged == 0
        )
        n_axiom_changed = sum(1 for i in theorem.interventions if i.has_axiom_change)
        wild = theorem.wild_type_solved
        lines.append(f"| {theorem.name} | {wild} | {n_int} | {n_ged0} | {n_axiom_changed} |")
    lines.append("")

    traj = trajectory_analysis(run)
    if traj["comparisons"]:
        lines.append("## Trajectory Analysis\n")
        lines.append(f"- Compared pairs: {traj['summary']['count']}")
        lines.append(f"- Avg iteration delta: {traj['summary']['avg_iteration_delta']:.2f}")
        lines.append(f"- Avg backtrack delta: {traj['summary']['avg_backtrack_delta']:.2f}\n")

    clusters = proof_term_clusters(run)
    if clusters:
        lines.append("## Proof Term Clusters\n")
        lines.append("Theorems with identical proof term hashes:\n")
        for cluster in clusters[:5]:
            lines.append(f"- {', '.join(cluster)}")
        lines.append("")

    return "\n".join(lines)
