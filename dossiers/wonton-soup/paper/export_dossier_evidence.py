"""Refresh the dossier's compact evidence export and generated count section.

Run with --db pointing to the preserved Wonton lake. Selection uses the same
completed-run filter as the paper figures. See ops/docs/report-layout.md.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import statistics
from pathlib import Path

import duckdb
from build_figures import completed_runs, query_basin_rows, seed_run_keys

ROOT = Path(__file__).resolve().parents[3]
CASE_RUN = "6043f87af1e797a1"
CASE_THEOREM = "mathlib__Mathlib__Logic__Encodable__Basic__L239__encode_inl__16849476"


def export(db: Path) -> None:
    conn = duckdb.connect(str(db), read_only=True)
    selected = completed_runs(conn)
    seed_run_keys(conn, "selected_completed_runs", [r[0] for r in selected])
    diversity_rows = query_basin_rows(conn)
    diversity_correlation = statistics.correlation(
        [r["unique_structures"] for r in diversity_rows],
        [r["lesion_recovery_rate"] for r in diversity_rows],
    )
    archive_runs = conn.execute("SELECT count(*) FROM runs").fetchone()[0]
    archive_theorems = conn.execute("""
        SELECT count(DISTINCT theorem) FROM (
            SELECT theorem FROM theorem_wild UNION ALL SELECT theorem FROM basin_seed
        )
    """).fetchone()[0]
    trials, theorems, batches, guided, blind, controls = conn.execute("""
        SELECT count(*), count(DISTINCT theorem), count(DISTINCT run_key),
               sum(attempts_total), sum(blind_attempts_total),
               count(*) FILTER (WHERE blind_attempts_total IS NOT NULL)
        FROM basin_seed JOIN selected_completed_runs USING(run_key)
    """).fetchone()
    lesions, eligible, survived, rerouted = conn.execute("""
        SELECT count(*),
          count(*) FILTER (WHERE i.baseline_solved AND n.solved),
          count(*) FILTER (WHERE i.baseline_solved AND n.solved AND i.solved),
          count(*) FILTER (WHERE i.baseline_solved AND n.solved AND i.solved AND c.hash_mismatch)
        FROM theorem_intervention i JOIN selected_completed_runs USING(run_key)
        LEFT JOIN theorem_intervention n
          ON n.run_key=i.run_key AND n.theorem=i.theorem AND n.intervention='control_null'
        LEFT JOIN theorem_intervention_comparison c
          ON c.run_key=i.run_key AND c.theorem=i.theorem AND c.intervention=i.intervention
        WHERE NOT coalesce(i.is_control, false) AND i.intervention <> 'control_null'
    """).fetchone()
    if not 0 < rerouted <= survived <= eligible <= lesions:
        raise ValueError("Invalid nested intervention counts")
    run_dir, config_raw = conn.execute(
        "SELECT run_dir, run_config FROM runs WHERE run_key=?", [CASE_RUN]
    ).fetchone()
    config = json.loads(config_raw)
    case = {
        "run_key": CASE_RUN,
        "theorem": CASE_THEOREM,
        "provider": config["provider"],
        "seed": config["seed"],
        "budget_tiers": config["budget_tiers"],
        "baseline_blocked_tactics": config["interventions"]["blocked_tactics"],
        "variants": {},
    }
    expected = {
        "wild_type": ["trivial"],
        "control_null": ["trivial"],
        "block_trivial": ["ring", "norm_num", "ring"],
    }
    for variant, tactics in expected.items():
        path = Path(run_dir) / CASE_THEOREM / f"{variant}_history.json"
        source = path.read_bytes()
        history = json.loads(source)
        indexed_hash = conn.execute(
            """
            SELECT sha256 FROM theorem_artifacts
            WHERE run_key=? AND theorem=? AND variant=? AND artifact_kind='history'
        """,
            [CASE_RUN, CASE_THEOREM, variant],
        ).fetchone()[0]
        digest = hashlib.sha256(source).hexdigest()
        if digest != indexed_hash:
            raise ValueError(f"History differs from lake index: {variant}")
        if [step["tactic"] for step in history["solution_path"]] != tactics:
            raise ValueError(f"Recorded route changed: {variant}")
        if not any(step.get("terminal_reached") for step in history["iterations"]):
            raise ValueError(f"No recorded closure: {variant}")
        case["variants"][variant] = {
            "history_sha256": digest,
            "steps": history["iteration_count"],
            "blocked_tactics": history["blocked_tactics"],
            "solution_path": [
                {"goal": s["goal"], "tactic": s["tactic"]} for s in history["solution_path"]
            ],
        }
    comparison_path = Path(run_dir) / CASE_THEOREM / "block_trivial_comparison.json"
    comparison_bytes = comparison_path.read_bytes()
    comparison = json.loads(comparison_bytes)
    if not comparison["solved"] or not comparison["hash_mismatch"]:
        raise ValueError("Showcase must retain the goal with a different proof")
    case["proof_comparison"] = {
        "sha256": hashlib.sha256(comparison_bytes).hexdigest(),
        "original_hash": comparison["wild_type_hash"],
        "alternate_hash": comparison["intervention_hash"],
        "proof_term_diff": comparison["proof_term_diff"],
    }
    evidence = {
        "indexed_archive": {
            "runs": archive_runs,
            "theorem_identifiers": archive_theorems,
            "scope": "All indexed work, including exploratory and incomplete runs",
        },
        "selection": (
            "Completed, non-partial Lean research runs from deepseek, heuristic and reprover; "
            "paper.build_figures.completed_runs"
        ),
        "completed_research_runs": len(selected),
        "selected_run_keys": sorted(r[0] for r in selected),
        "latest_run_created_at": max(r[3] for r in selected if r[3]),
        "repeated_seed": {
            "batches": batches,
            "theorems": theorems,
            "guided_trials": trials,
            "blind_controls_available": controls,
            "guided_tactic_attempts": guided,
            "blind_tactic_attempts": blind,
            "total_tactic_attempts": guided + blind,
        },
        "interventions": {
            "non_control_reruns": lesions,
            "baseline_and_null_solved": eligible,
            "still_solved": survived,
            "different_proof_hash": rerouted,
        },
        "proof_diversity_and_recovery": {
            "grouping": "Theorem and provider; paper.build_figures.query_basin_rows",
            "groups": len(diversity_rows),
            "pearson_r": diversity_correlation,
            "rows": diversity_rows,
        },
        "example": case,
    }
    output = ROOT / "site/assets/wonton-soup/dossier-evidence.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n")

    def metric(label: str, value: str, note: str) -> str:
        return (
            f'<div class="ws-metric"><div class="ws-metric-label">{html.escape(label)}</div>'
            f'<div class="ws-metric-value">{value}</div>'
            f'<div class="ws-metric-note">{html.escape(note)}</div></div>'
        )

    scale = metric(
        "Tactic attempts", f"{guided + blind:,}", "guided searches and available blind controls"
    )
    scale += metric(
        "Repeated-seed searches", f"{trials:,}", f"plus {controls:,} blind-control searches"
    )
    scale += metric(
        "Theorems revisited", f"{theorems:,}", f"across {batches:,} completed experiment batches"
    )
    survival = survived / eligible * 100
    fragment = f'''
<section class="ws-section" id="scale">
<h2 class="story-heading">Over half a million attempts to find a proof</h2>
<p class="story-deck">The archive indexes {archive_runs:,} runs and {archive_theorems:,} theorem
identifiers. Within its completed research cohort, we revisit {theorems:,} theorems under many
search seeds, comparing the prover with blind search:</p>
<div class="ws-metrics">{scale}</div>
</section>
<section class="ws-section" id="evidence">
<h2 class="story-heading">How often does the search still find a proof?</h2>
<p class="story-deck">Across {len(selected):,} completed research runs, we recorded {lesions:,}
tactic-removal reruns. For the survival comparison, {eligible:,} had both a successful original
search and a successful unchanged control. Of those, {survived:,} still found a proof after the
tactic was removed.</p>
<figure class="story-survival"><div class="story-survival-track" role="img"
aria-label="{survived:,} of {eligible:,} interventions retained a proof, {survival:.1f}
percent"><span style="width: {survival:.6f}%"></span></div><figcaption>{survived:,} still found
a proof · {eligible - survived:,} did not.</figcaption></figure>
<p class="story-deck">{rerouted:,} of the surviving searches produced a different proof hash.
The goal stayed fixed while the proof changed—the same pattern illustrated by the alternate
route above.</p>
<p class="ws-small">Counts recomputed from the preserved lake, covering completed runs through
{evidence["latest_run_created_at"][:10]}. <a
href="/assets/wonton-soup/dossier-evidence.json">Cohort selection and recorded evidence</a>.</p>
</section>
<section class="ws-section">
<h2 class="story-heading">Observed proof diversity was a poor guide to recovery</h2>
<p class="story-deck">We expected theorems with more observed proof structures to be easier
to solve after a tactic was blocked. Across {len(diversity_rows)} theorem–prover groups,
the correlation between the number of observed structures and the fraction of successful
tactic-removal reruns was {diversity_correlation:.2f}. The variety recorded in ordinary
searches gave little indication of which searches would recover.</p>
<div class="story-jumps"><a
href="../../research-notes/2026-06-10-taking-away-one-move-revealed-proof-alternatives/">
Follow the experiment →</a><a href="../../dashboards/wonton-soup/">
Inspect individual searches →</a></div>
</section>
'''
    template = ROOT / "site/templates/dossiers/wonton-soup/index.html"
    source = template.read_text()
    source, count = re.subn(
        r"(?<=<!-- GENERATED:WONTON_EVIDENCE START -->).*?"
        r"(?=<!-- GENERATED:WONTON_EVIDENCE END -->)",
        lambda _: fragment,
        source,
        flags=re.S,
    )
    if count != 1:
        raise ValueError("Expected one Wonton evidence region")
    template.write_text(source)
    print(
        json.dumps(
            {k: v for k, v in evidence.items() if k not in {"selected_run_keys", "example"}},
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    export(parser.parse_args().db)
