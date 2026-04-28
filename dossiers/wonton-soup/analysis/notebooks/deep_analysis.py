import marimo

__generated_with = "0.10.0"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo

    mo.md("""
    # Proto-Cognitive Signatures in Distributed MCTS Theorem Proving
    ## Deep Analysis Notebook

    Investigates response modes, structural divergence, trajectory recovery,
    basin stability, search efficiency, controller lesion effects, and
    cross-assistant signal from the abstract evidence campaign data.
    """)
    return (mo,)


@app.cell
def _(mo):
    import os
    import duckdb
    import pandas as pd
    import numpy as np
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from scipy import stats

    db_path = os.environ.get(
        "LAKE_DB_PATH",
        "/Volumes/shared/specter-runtime/wonton-soup/artifacts/lake/lake.duckdb",
    )
    if not os.path.exists(db_path):
        db_path = "/shared/specter-runtime/wonton-soup/artifacts/lake/lake.duckdb"

    conn = duckdb.connect(db_path, read_only=True)
    # Seed an empty selected_run_keys table; the filter cell repopulates it.
    # This avoids "table does not exist" errors if other cells execute first.
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS selected_run_keys (run_key VARCHAR PRIMARY KEY)")
    # Default: select all runs
    conn.execute("INSERT OR IGNORE INTO selected_run_keys SELECT run_key FROM runs")
    mo.md(f"**Connected** to `{db_path}`")
    return conn, db_path, duckdb, go, make_subplots, np, os, pd, px, stats


# ---------------------------------------------------------------------------
# Section 0: Dataset Overview
# ---------------------------------------------------------------------------


@app.cell
def _(conn, mo, pd):
    runs_df = conn.execute("""
        SELECT r.run_key, r.run_id, r.provider, r.backend, r.mode, r.corpus,
               a.theorem_count, a.wild_type_solve_rate, a.intervention_count,
               a.intervention_solve_rate
        FROM runs r
        LEFT JOIN run_aggregates a ON r.run_key = a.run_key
        ORDER BY r.run_id
    """).df()

    # Extract campaign IDs (first path segment of run_id)
    runs_df["campaign"] = runs_df["run_id"].apply(
        lambda x: x.split("/")[0] if isinstance(x, str) and "/" in x else x
    )

    mo.md("""
    ## Section 0: Dataset Overview

    Select which campaigns and providers to include in the analysis.
    All downstream sections filter to the selected runs.
    """)
    return (runs_df,)


@app.cell
def _(mo, runs_df):
    campaigns = sorted(runs_df["campaign"].dropna().unique().tolist())
    campaign_filter = mo.ui.multiselect(
        campaigns, label="Campaigns", value=campaigns,
    )
    providers = sorted(runs_df["provider"].dropna().unique().tolist())
    provider_filter = mo.ui.multiselect(providers, label="Providers", value=providers)

    mo.hstack([campaign_filter, provider_filter])
    return campaign_filter, provider_filter, providers


@app.cell
def _(campaign_filter, conn, mo, provider_filter, runs_df):
    selected = runs_df[
        runs_df["campaign"].isin(campaign_filter.value)
        & runs_df["provider"].isin(provider_filter.value)
    ]
    selected_keys = selected["run_key"].tolist()

    # Populate a temp table so all downstream queries can filter via it.
    # DuckDB doesn't allow prepared params in CREATE VIEW, so we use a real table.
    conn.execute("CREATE OR REPLACE TEMP TABLE selected_run_keys (run_key VARCHAR PRIMARY KEY)")
    if selected_keys:
        values = ", ".join(f"('{k}')" for k in selected_keys)
        conn.execute(f"INSERT INTO selected_run_keys VALUES {values}")

    overview = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM selected_run_keys) as selected_runs,
            (SELECT COUNT(*) FROM theorem_wild w JOIN selected_run_keys s ON w.run_key = s.run_key) as wild_type_results,
            (SELECT COUNT(*) FROM theorem_intervention i JOIN selected_run_keys s ON i.run_key = s.run_key) as interventions,
            (SELECT COUNT(*) FROM mcts_controller_iterations ci JOIN selected_run_keys s ON ci.run_key = s.run_key) as controller_iterations,
            (SELECT COUNT(*) FROM basin_runs b JOIN selected_run_keys s ON b.run_key = s.run_key) as basin_theorems,
            (SELECT COUNT(*) FROM basin_seed bs JOIN selected_run_keys s ON bs.run_key = s.run_key) as basin_seeds,
            (SELECT COUNT(*) FROM k_reference_score k JOIN selected_run_keys s ON k.run_key = s.run_key WHERE k.valid) as valid_k_scores
    """).df()

    mo.md(f"""
    ### Selected Data

    **{len(selected)}** runs from **{len(campaign_filter.value)}** campaigns, **{len(provider_filter.value)}** providers

    | Metric | Value |
    |--------|-------|
    | Runs | **{overview['selected_runs'][0]}** |
    | Wild-type results | **{overview['wild_type_results'][0]:,}** |
    | Interventions | **{overview['interventions'][0]:,}** |
    | Controller iterations | **{overview['controller_iterations'][0]:,}** |
    | Basin theorems / seeds | **{overview['basin_theorems'][0]}** / **{overview['basin_seeds'][0]}** |
    | Valid K-scores | **{overview['valid_k_scores'][0]:,}** |
    """)

    mo.ui.table(selected[["run_id", "provider", "theorem_count", "wild_type_solve_rate", "intervention_count"]])
    return overview, selected, selected_keys


# ---------------------------------------------------------------------------
# Section 1: Response Mode Classification
# ---------------------------------------------------------------------------


@app.cell
def _(conn, mo, np, pd, provider_filter, px):
    modes_raw = conn.execute("""
        SELECT
            r.provider,
            r.run_key,
            i.theorem,
            i.intervention,
            i.solved AS inv_solved,
            i.baseline_solved,
            i.is_control,
            i.ged_search_norm,
            c.hash_mismatch,
            c.ged_search_value AS c_ged_value
        FROM theorem_intervention i
        JOIN runs r ON i.run_key = r.run_key
        JOIN selected_run_keys s ON r.run_key = s.run_key
        LEFT JOIN theorem_intervention_comparison c
            ON c.run_key = i.run_key AND c.theorem = i.theorem AND c.intervention = i.intervention
        WHERE i.baseline_solved = true
    """).df()

    modes_raw = modes_raw[modes_raw["provider"].isin(provider_filter.value)]

    # Separate control_null results to check reliability:
    # for publication-facing percentages, only count perturbations on theorems
    # whose control_null variant still solves.
    control_null = modes_raw[modes_raw["intervention"] == "control_null"]
    control_solved = set(
        control_null[control_null["inv_solved"] == True]
        .apply(lambda r: (r["run_key"], r["theorem"]), axis=1)
    )
    control_total = len(control_null)
    control_collapse = (control_null["inv_solved"] == False).sum()

    control_table_df = pd.DataFrame(
        columns=["provider", "control_total", "control_collapsed", "collapse_pct"]
    )
    if len(control_null) > 0:
        control_table_df = (
            control_null.groupby("provider")
            .agg(
                control_total=("theorem", "size"),
                control_collapsed=("inv_solved", lambda s: int((s == False).sum())),
            )
            .reset_index()
        )
        control_table_df["collapse_pct"] = (
            100
            * control_table_df["control_collapsed"]
            / control_table_df["control_total"].clip(lower=1)
        ).round(1)

    # Filter to non-control interventions only for mode classification.
    # The strict view also requires control_null to have solved.
    modes_all_df = modes_raw[modes_raw["is_control"] != True].copy()
    modes_all_df["control_null_ok"] = modes_all_df.apply(
        lambda row: (row["run_key"], row["theorem"]) in control_solved,
        axis=1,
    )
    modes_df = modes_all_df[modes_all_df["control_null_ok"] == True].copy()
    excluded_for_control = len(modes_all_df) - len(modes_df)

    def classify_mode(row):
        if not row["inv_solved"]:
            return "collapse"
        ged = row["ged_search_norm"]
        if ged is None or (isinstance(ged, float) and np.isnan(ged)):
            hm = row["hash_mismatch"]
            if hm is False or hm is None:
                return "replicate"
            return "reroute"
        if ged == 0:
            return "replicate"
        return "reroute"

    modes_all_df["mode"] = modes_all_df.apply(classify_mode, axis=1)
    modes_df["mode"] = modes_df.apply(classify_mode, axis=1)

    mode_counts = modes_df.groupby(["provider", "mode"]).size().reset_index(name="count")
    mode_totals = modes_df.groupby("provider").size().reset_index(name="total")
    mode_counts = mode_counts.merge(mode_totals, on="provider")
    mode_counts["pct"] = (100 * mode_counts["count"] / mode_counts["total"]).round(1)

    fig_modes = None
    if len(mode_counts) > 0:
        fig_modes = px.bar(
            mode_counts,
            x="provider",
            y="pct",
            color="mode",
            color_discrete_map={"replicate": "#2ecc71", "reroute": "#3498db", "collapse": "#e74c3c"},
            barmode="stack",
            title="Response Modes (control-null-stable, baseline-solved theorems)",
            labels={"pct": "Interventions (%)", "provider": "Provider"},
        )

    intervention_modes = modes_df.groupby(["intervention", "mode"]).size().reset_index(name="count")
    fig_by_int = None
    if len(intervention_modes) > 0:
        fig_by_int = px.bar(
            intervention_modes,
            x="intervention",
            y="count",
            color="mode",
            color_discrete_map={"replicate": "#2ecc71", "reroute": "#3498db", "collapse": "#e74c3c"},
            barmode="stack",
            title="Response Modes by Intervention Type (control-null-stable only)",
        )
        fig_by_int.update_xaxes(tickangle=45)

    raw_total = len(modes_all_df)
    total = len(modes_df)
    rep = (modes_df["mode"] == "replicate").sum()
    rer = (modes_df["mode"] == "reroute").sum()
    col = (modes_df["mode"] == "collapse").sum()
    control_table = (
        control_table_df.to_markdown(index=False)
        if len(control_table_df) > 0
        else "No control_null rows in the selected runs."
    )

    mo.md(f"""
    ## Section 1: Response Mode Classification

    **Claim**: Interventions produce three response modes: replicate, reroute, collapse.

    The main percentages below use the stricter denominator:
    **non-control interventions on baseline-solved theorems whose `control_null` variant also solved**.

    ### Control reliability by provider
    {control_table}

    **Control reliability**: {control_total} control_null interventions, {int(control_collapse)} collapsed
    ({100*control_collapse/max(control_total,1):.1f}% collapse on null control -- natural variance baseline).

    Raw non-control interventions on baseline-solved theorems: **{raw_total}**
    Strictly retained after `control_null` gating: **{total}**
    Excluded because `control_null` failed or was missing: **{excluded_for_control}**

    Among **{total}** strict-gated non-control interventions:
    - **Replicate**: {rep} ({100*rep/total:.1f}%) -- same proof structure despite intervention
    - **Reroute**: {rer} ({100*rer/total:.1f}%) -- different proof found (nonzero GED)
    - **Collapse**: {col} ({100*col/total:.1f}%) -- failed after intervention

    Recovery rate (reroute / (reroute + collapse)): **{100*rer/max(rer+col, 1):.1f}%**
    Adjusted for control baseline: interventions cause ~{100*(col/max(total,1) - control_collapse/max(control_total,1)):.1f}pp
    additional collapse beyond natural variance.
    """)
    return (
        classify_mode, col, control_collapse, control_solved, control_table_df, control_total,
        excluded_for_control,
        fig_by_int, fig_modes, intervention_modes, mode_counts,
        mode_totals, modes_all_df, modes_df, modes_raw, raw_total, rep, rer, total,
    )


@app.cell
def _(fig_modes, mo):
    if fig_modes is not None:
        mo.ui.plotly(fig_modes)
    return


@app.cell
def _(fig_by_int, mo):
    if fig_by_int is not None:
        mo.ui.plotly(fig_by_int)
    return


# ---------------------------------------------------------------------------
# Section 2: GED Analysis
# ---------------------------------------------------------------------------


@app.cell
def _(conn, mo, pd, provider_filter, px, stats):
    ged_df = conn.execute("""
        SELECT r.provider, i.theorem, i.intervention, i.solved,
               i.ged_search_value, i.ged_search_norm,
               i.ged_search_soft_value, i.ged_search_soft_norm,
               c.ged_search_value AS c_ged_value, c.ged_search_norm AS c_ged_norm
        FROM theorem_intervention i
        JOIN runs r ON i.run_key = r.run_key
        JOIN selected_run_keys s ON r.run_key = s.run_key
        LEFT JOIN theorem_intervention_comparison c
            ON c.run_key = i.run_key AND c.theorem = i.theorem AND c.intervention = i.intervention
        WHERE i.ged_search_norm IS NOT NULL
    """).df()

    ged_df = ged_df[ged_df["provider"].isin(provider_filter.value)]

    fig_ged_dist = px.histogram(
        ged_df,
        x="ged_search_norm",
        color="provider",
        nbins=40,
        marginal="box",
        title="GED (Normalized) Distribution Across Interventions",
        labels={"ged_search_norm": "Normalized GED"},
    )

    intervention_types = ged_df["intervention"].str.replace(r"_\d+$", "", regex=True).str.replace(r"_mcts_.*", "", regex=True)
    ged_df["int_type"] = intervention_types
    fig_ged_box = px.box(
        ged_df,
        x="int_type",
        y="ged_search_norm",
        color="provider",
        title="GED by Intervention Type",
        labels={"ged_search_norm": "Normalized GED", "int_type": "Intervention"},
    )
    fig_ged_box.update_xaxes(tickangle=45)

    ged_by_type = ged_df.groupby("int_type")["ged_search_norm"].agg(["median", "mean", "std", "count"]).reset_index()
    groups = [g["ged_search_norm"].dropna().values for _, g in ged_df.groupby("int_type") if len(g) > 2]
    kw_stat, kw_p = stats.kruskal(*groups) if len(groups) > 1 else (float("nan"), float("nan"))

    mo.md(f"""
    ## Section 2: GED Analysis

    **Claim**: GED captures structural divergence under intervention.

    {len(ged_df)} interventions with valid GED values.

    **Kruskal-Wallis test** across intervention types: H={kw_stat:.2f}, p={kw_p:.2e}

    {ged_by_type.to_markdown(index=False)}
    """)
    return fig_ged_box, fig_ged_dist, ged_by_type, ged_df, groups, intervention_types, kw_p, kw_stat


@app.cell
def _(fig_ged_dist, mo):
    mo.ui.plotly(fig_ged_dist)
    return


@app.cell
def _(fig_ged_box, mo):
    mo.ui.plotly(fig_ged_box)
    return


# ---------------------------------------------------------------------------
# Section 3: Trajectory Divergence/Recovery
# ---------------------------------------------------------------------------


@app.cell
def _(conn, mo, pd, provider_filter, px):
    traj_df = conn.execute("""
        SELECT r.provider, i.theorem, i.intervention, i.solved AS inv_solved,
               i.baseline_solved,
               p.goal_novelty_novel_goal_count,
               p.goal_novelty_dropped_goal_count,
               p.solution_path_soft_distance_value,
               p.solution_path_soft_distance_valid,
               p.solution_path_soft_distance_wild_len,
               p.solution_path_soft_distance_intervention_len,
               i.ged_search_norm
        FROM theorem_intervention i
        JOIN runs r ON i.run_key = r.run_key
        JOIN selected_run_keys s ON r.run_key = s.run_key
        LEFT JOIN theorem_intervention_postprocess p
            ON p.run_key = i.run_key AND p.theorem = i.theorem AND p.intervention = i.intervention
        WHERE i.baseline_solved = true
    """).df()

    traj_df = traj_df[traj_df["provider"].isin(provider_filter.value)]

    traj_with_novelty = traj_df[traj_df["goal_novelty_novel_goal_count"].notna()]

    fig_novelty = px.histogram(
        traj_with_novelty,
        x="goal_novelty_novel_goal_count",
        color="inv_solved",
        nbins=20,
        title="Novel Goals Introduced by Intervention",
        labels={"goal_novelty_novel_goal_count": "Novel Goal Count", "inv_solved": "Solved"},
        color_discrete_map={True: "#2ecc71", False: "#e74c3c"},
    )

    traj_with_dist = traj_df[traj_df["solution_path_soft_distance_valid"] == True]
    fig_path_dist = px.scatter(
        traj_with_dist,
        x="ged_search_norm",
        y="solution_path_soft_distance_value",
        color="inv_solved",
        title="Solution Path Distance vs GED",
        labels={
            "ged_search_norm": "GED (normalized)",
            "solution_path_soft_distance_value": "Solution Path Soft Distance",
            "inv_solved": "Solved",
        },
        color_discrete_map={True: "#2ecc71", False: "#e74c3c"},
    )

    recovery_total = len(traj_df)
    recovery_solved = traj_df["inv_solved"].sum()
    recovery_rate = 100 * recovery_solved / max(recovery_total, 1)

    mo.md(f"""
    ## Section 3: Trajectory Divergence/Recovery

    **Claim**: System can recover goal-directed competence after perturbation.

    Of {recovery_total} interventions on baseline-solved theorems:
    - **{int(recovery_solved)}** ({recovery_rate:.1f}%) recovered (solved despite intervention)
    - **{recovery_total - int(recovery_solved)}** ({100 - recovery_rate:.1f}%) collapsed

    Novelty data available for {len(traj_with_novelty)} interventions.
    Path distance data available for {len(traj_with_dist)} interventions.
    """)
    return (
        fig_novelty, fig_path_dist, recovery_rate, recovery_solved,
        recovery_total, traj_df, traj_with_dist, traj_with_novelty,
    )


@app.cell
def _(fig_novelty, mo):
    mo.ui.plotly(fig_novelty)
    return


@app.cell
def _(fig_path_dist, mo):
    mo.ui.plotly(fig_path_dist)
    return


# ---------------------------------------------------------------------------
# Section 4: Basin Analysis
# ---------------------------------------------------------------------------


@app.cell
def _(conn, mo, np, pd, provider_filter, px):
    basin_df = conn.execute("""
        SELECT r.provider, b.run_key, b.theorem, b.solve_rate, b.unique_structures,
               b.dominant_structure_frequency, b.seeds_requested,
               b.blind_solve_rate, b.paper_k
        FROM basin_runs b
        JOIN runs r ON b.run_key = r.run_key
        JOIN selected_run_keys s ON b.run_key = s.run_key
    """).df()

    basin_seeds_df = conn.execute("""
        SELECT r.provider, b.run_key, theorem, seed, solved, structure_hash, iterations_to_solve,
               blind_solved, blind_structure_hash
        FROM basin_seed b
        JOIN runs r ON b.run_key = r.run_key
        JOIN selected_run_keys s ON b.run_key = s.run_key
    """).df()

    structure_counts_df = conn.execute("""
        SELECT r.provider, b.run_key, theorem, structure_hash, count
        FROM basin_structure_counts b
        JOIN runs r ON b.run_key = r.run_key
        JOIN selected_run_keys s ON b.run_key = s.run_key
        ORDER BY theorem, count DESC
    """).df()

    basin_df = basin_df[basin_df["provider"].isin(provider_filter.value)]
    basin_seeds_df = basin_seeds_df[basin_seeds_df["provider"].isin(provider_filter.value)]
    structure_counts_df = structure_counts_df[
        structure_counts_df["provider"].isin(provider_filter.value)
    ]

    def shannon_entropy(counts):
        total = sum(counts)
        if total == 0:
            return 0.0
        probs = [c / total for c in counts]
        return -sum(p * np.log2(p) for p in probs if p > 0)

    basin_entropy = []
    for theorem in structure_counts_df["theorem"].unique():
        counts = structure_counts_df[structure_counts_df["theorem"] == theorem]["count"].tolist()
        basin_entropy.append({"theorem": theorem, "entropy": shannon_entropy(counts), "n_structures": len(counts)})
    entropy_df = pd.DataFrame(basin_entropy)

    fig_basin_width = px.histogram(
        basin_df,
        x="unique_structures",
        nbins=20,
        title="Basin Width: Unique Proof Structures per Theorem",
        labels={"unique_structures": "Unique Structures"},
    )

    fig_basin_dom = px.scatter(
        basin_df,
        x="unique_structures",
        y="dominant_structure_frequency",
        size="solve_rate",
        title="Dominant Structure Frequency vs Basin Width",
        labels={
            "unique_structures": "Unique Structures",
            "dominant_structure_frequency": "Dominant Structure Frequency",
        },
    )

    fig_entropy = px.histogram(
        entropy_df,
        x="entropy",
        nbins=15,
        title="Shannon Entropy of Proof Structure Distributions",
        labels={"entropy": "Shannon Entropy (bits)"},
    )

    avg_structures = basin_df["unique_structures"].mean() if len(basin_df) > 0 else float("nan")
    avg_dom_freq = (
        basin_df["dominant_structure_frequency"].mean() if len(basin_df) > 0 else float("nan")
    )
    avg_entropy = entropy_df["entropy"].mean() if len(entropy_df) > 0 else float("nan")

    mo.md(f"""
    ## Section 4: Basin Analysis

    **Claim**: Repeated runs reveal stable proof-structure basins.

    {len(basin_df)} theorems with basin analysis ({basin_seeds_df['seed'].nunique()} seeds total):
    - Mean unique structures per theorem: **{avg_structures:.1f}**
    - Mean dominant structure frequency: **{avg_dom_freq:.2f}**
    - Mean Shannon entropy: **{avg_entropy:.2f}** bits

    {len(entropy_df[entropy_df['entropy'] == 0])} theorems have entropy = 0 (single dominant structure).
    {len(entropy_df[entropy_df['entropy'] > 1])} theorems have entropy > 1 bit (diverse basins).
    """)
    return (
        avg_dom_freq, avg_entropy, avg_structures, basin_df, basin_entropy,
        basin_seeds_df, entropy_df, fig_basin_dom, fig_basin_width, fig_entropy,
        shannon_entropy, structure_counts_df,
    )


@app.cell
def _(fig_basin_width, mo):
    mo.ui.plotly(fig_basin_width)
    return


@app.cell
def _(fig_basin_dom, mo):
    mo.ui.plotly(fig_basin_dom)
    return


@app.cell
def _(fig_entropy, mo):
    mo.ui.plotly(fig_entropy)
    return


# ---------------------------------------------------------------------------
# Section 5: K-Score Search Efficiency
# ---------------------------------------------------------------------------


@app.cell
def _(conn, mo, pd, provider_filter, px, stats):
    # Wild-type K -- prioritize kfix run for deepseek (100% validity)
    k_wild_df = conn.execute("""
        SELECT r.provider, r.run_id, w.theorem, w.k_K, w.k_valid, w.solved
        FROM theorem_wild w
        JOIN runs r ON w.run_key = r.run_key
        JOIN selected_run_keys s ON r.run_key = s.run_key
        WHERE w.k_valid = true AND w.k_K IS NOT NULL
    """).df()

    k_wild_df = k_wild_df[k_wild_df["provider"].isin(provider_filter.value)]

    # Show K validity by run so user can see the kfix improvement
    k_validity_df = conn.execute("""
        SELECT r.provider, r.run_id,
            SUM(CASE WHEN w.solved THEN 1 ELSE 0 END) as solved,
            SUM(CASE WHEN w.k_valid THEN 1 ELSE 0 END) as k_valid,
            ROUND(100.0 * SUM(CASE WHEN w.k_valid THEN 1 ELSE 0 END) /
                NULLIF(SUM(CASE WHEN w.solved THEN 1 ELSE 0 END), 0), 1) as validity_pct
        FROM theorem_wild w
        JOIN runs r ON w.run_key = r.run_key
        JOIN selected_run_keys s ON r.run_key = s.run_key
        WHERE w.solved = true
        GROUP BY r.provider, r.run_id
        ORDER BY r.provider, r.run_id
    """).df()
    k_validity_df = k_validity_df[k_validity_df["provider"].isin(provider_filter.value)]

    fig_k_dist = px.histogram(
        k_wild_df,
        x="k_K",
        color="provider",
        nbins=40,
        marginal="box",
        title="Wild-Type K-Score Distribution (baseline, before intervention)",
        labels={"k_K": "K (search efficiency)"},
    )

    # Before/after: wild K vs intervention K on same theorems
    k_paired_df = conn.execute("""
        SELECT r.provider, i.theorem, i.intervention,
               w.k_K AS wild_k, i.k_K AS inv_k,
               i.k_K - w.k_K AS delta_k,
               i.solved AS inv_solved
        FROM theorem_intervention i
        JOIN runs r ON i.run_key = r.run_key
        JOIN selected_run_keys s ON r.run_key = s.run_key
        LEFT JOIN theorem_wild w ON w.run_key = i.run_key AND w.theorem = i.theorem
        WHERE w.k_K IS NOT NULL AND w.k_valid = true
    """).df()

    k_paired_df = k_paired_df[k_paired_df["provider"].isin(provider_filter.value)]

    # Melt for before/after comparison
    k_before_after = []
    for _, row in k_paired_df.iterrows():
        if row["wild_k"] is not None:
            k_before_after.append({"provider": row["provider"], "condition": "wild-type", "K": row["wild_k"]})
        if row["inv_k"] is not None:
            k_before_after.append({"provider": row["provider"], "condition": "intervention", "K": row["inv_k"]})
    k_ba_df = pd.DataFrame(k_before_after) if k_before_after else pd.DataFrame(columns=["provider", "condition", "K"])

    fig_k_before_after = px.box(
        k_ba_df,
        x="provider",
        y="K",
        color="condition",
        title="K-Score: Wild-Type (before) vs Intervention (after)",
        labels={"K": "K (search efficiency)"},
        color_discrete_map={"wild-type": "#2ecc71", "intervention": "#e74c3c"},
    ) if len(k_ba_df) > 0 else None

    # Delta-K distribution
    k_with_delta = k_paired_df[k_paired_df["delta_k"].notna()]
    fig_delta_k = px.histogram(
        k_with_delta,
        x="delta_k",
        color="provider",
        nbins=40,
        title="Delta-K (Intervention - Wild Type)",
        labels={"delta_k": "K_intervention - K_wild"},
    ) if len(k_with_delta) > 0 else None

    valid_k = k_wild_df
    if len(valid_k) > 0:
        mean_k_by_provider = valid_k.groupby("provider")["k_K"].agg(["mean", "median", "std", "count"]).reset_index()
        k_table = mean_k_by_provider.to_markdown(index=False)
    else:
        k_table = "No valid K-scores available."

    if len(k_with_delta) > 10:
        dk = k_with_delta["delta_k"].dropna()
        wil_stat, wil_p = stats.wilcoxon(dk)
        mean_dk = dk.mean()
    else:
        dk = k_with_delta["delta_k"].dropna() if len(k_with_delta) > 0 else pd.Series(dtype=float)
        wil_stat, wil_p, mean_dk = float("nan"), float("nan"), dk.mean() if len(dk) > 0 else float("nan")

    k_validity_table = k_validity_df.to_markdown(index=False)

    mo.md(f"""
    ## Section 5: K-Score Search Efficiency

    **Claim**: K-scores quantify intervention effect on search efficiency.

    ### K Validity by Run
    {k_validity_table}

    ### Wild-type K by provider (baseline)
    {k_table}

    ### Delta-K (intervention effect)
    Paired comparisons: **{len(k_with_delta)}**
    Mean delta-K: **{mean_dk:.3f}**
    Wilcoxon signed-rank test: W={wil_stat:.1f}, p={wil_p:.2e}
    (Positive delta-K = intervention made search less efficient)
    """)
    return (
        dk, fig_delta_k, fig_k_before_after, fig_k_dist, k_ba_df,
        k_paired_df, k_table, k_validity_df, k_validity_table, k_wild_df,
        k_with_delta, mean_dk, mean_k_by_provider, valid_k, wil_p, wil_stat,
    )


@app.cell
def _(fig_k_dist, mo):
    mo.ui.plotly(fig_k_dist)
    return


@app.cell
def _(fig_k_before_after, mo):
    if fig_k_before_after is not None:
        mo.ui.plotly(fig_k_before_after)
    return


@app.cell
def _(fig_delta_k, mo):
    if fig_delta_k is not None:
        mo.ui.plotly(fig_delta_k)
    return


# ---------------------------------------------------------------------------
# Section 5b: Centralized vs Distributed MCTS
# ---------------------------------------------------------------------------


@app.cell
def _(conn, mo, pd, provider_filter, px):
    cent_vs_dist = conn.execute("""
        SELECT
            r.provider,
            CASE WHEN r.run_id LIKE '%distributed%' THEN 'distributed'
                 ELSE 'centralized' END as mcts_mode,
            COUNT(DISTINCT w.theorem) as theorems,
            SUM(CASE WHEN w.solved THEN 1 ELSE 0 END) as solved,
            ROUND(100.0 * SUM(CASE WHEN w.solved THEN 1 ELSE 0 END) / COUNT(DISTINCT w.theorem), 1) as solve_pct
        FROM theorem_wild w
        JOIN runs r ON w.run_key = r.run_key
        JOIN selected_run_keys s ON r.run_key = s.run_key
        WHERE r.run_id LIKE '%matrix%' OR r.run_id LIKE '%p2-paired%'
        GROUP BY r.provider, mcts_mode
    """).df()
    cent_vs_dist = cent_vs_dist[cent_vs_dist["provider"].isin(provider_filter.value)]

    fig_cvd = px.bar(
        cent_vs_dist,
        x="provider",
        y="solve_pct",
        color="mcts_mode",
        barmode="group",
        title="Solve Rate: Centralized vs Distributed MCTS",
        labels={"solve_pct": "Solve Rate (%)", "mcts_mode": "MCTS Mode"},
        color_discrete_map={"centralized": "#3498db", "distributed": "#e74c3c"},
    ) if len(cent_vs_dist) > 0 else None

    # Per-theorem agreement between modes (same provider)
    cvd_agreement = conn.execute("""
        WITH runs_tagged AS (
            SELECT w.theorem, r.provider, w.solved,
                CASE WHEN r.run_id LIKE '%distributed%' THEN 'distributed'
                     ELSE 'centralized' END as mcts_mode
            FROM theorem_wild w
            JOIN runs r ON w.run_key = r.run_key
            JOIN selected_run_keys s ON r.run_key = s.run_key
            WHERE r.run_id LIKE '%matrix%' OR r.run_id LIKE '%p2-paired%'
        ),
        cent AS (SELECT theorem, provider, solved FROM runs_tagged WHERE mcts_mode = 'centralized'),
        dist AS (SELECT theorem, provider, solved FROM runs_tagged WHERE mcts_mode = 'distributed')
        SELECT c.provider,
            COUNT(*) as total,
            SUM(CASE WHEN c.solved = d.solved THEN 1 ELSE 0 END) as agree,
            SUM(CASE WHEN c.solved AND NOT d.solved THEN 1 ELSE 0 END) as cent_only,
            SUM(CASE WHEN NOT c.solved AND d.solved THEN 1 ELSE 0 END) as dist_only
        FROM cent c
        JOIN dist d ON c.theorem = d.theorem AND c.provider = d.provider
        GROUP BY c.provider
    """).df()
    cvd_agreement = cvd_agreement[cvd_agreement["provider"].isin(provider_filter.value)]

    # Intervention recovery by mode
    cvd_recovery = conn.execute("""
        SELECT r.provider,
            CASE WHEN r.run_id LIKE '%distributed%' THEN 'distributed'
                 ELSE 'centralized' END as mcts_mode,
            SUM(CASE WHEN i.baseline_solved THEN 1 ELSE 0 END) as on_solved,
            SUM(CASE WHEN i.baseline_solved AND i.solved THEN 1 ELSE 0 END) as recovered,
            ROUND(100.0 * SUM(CASE WHEN i.baseline_solved AND i.solved THEN 1 ELSE 0 END) /
                NULLIF(SUM(CASE WHEN i.baseline_solved THEN 1 ELSE 0 END), 0), 1) as recovery_pct
        FROM theorem_intervention i
        JOIN runs r ON i.run_key = r.run_key
        JOIN selected_run_keys s ON r.run_key = s.run_key
        WHERE (r.run_id LIKE '%matrix%' OR r.run_id LIKE '%p2-paired%') AND i.is_control != true
        GROUP BY r.provider, mcts_mode
    """).df()
    cvd_recovery = cvd_recovery[cvd_recovery["provider"].isin(provider_filter.value)]

    cvd_table = cent_vs_dist.to_markdown(index=False) if len(cent_vs_dist) > 0 else "No data yet."
    agree_table = cvd_agreement.to_markdown(index=False) if len(cvd_agreement) > 0 else "No data yet."
    recovery_table = cvd_recovery.to_markdown(index=False) if len(cvd_recovery) > 0 else "No data yet."

    mo.md(f"""
    ## Section 5b: Centralized vs Distributed MCTS

    **Claim**: The distributed coordination layer introduces stochastic perturbation
    via agent scheduling races, constituting a collective-intelligence mechanism.

    ### Solve rates by mode
    {cvd_table}

    ### Per-theorem agreement (same provider, different mode)
    {agree_table}

    ### Intervention recovery by mode
    {recovery_table}
    """)
    return cent_vs_dist, cvd_agreement, cvd_recovery, fig_cvd


@app.cell
def _(fig_cvd, mo):
    if fig_cvd is not None:
        mo.ui.plotly(fig_cvd)
    return


# ---------------------------------------------------------------------------
# Section 5c: Difficulty Modulates Resilience
# ---------------------------------------------------------------------------


@app.cell
def _(conn, mo, pd, provider_filter, px):
    difficulty_df = conn.execute("""
        SELECT
            r.provider,
            CASE
                WHEN r.corpus LIKE '%coq-paired%' THEN 'coq-paired (easy)'
                WHEN r.corpus LIKE '%matched%' THEN 'matched-slice (hard)'
                ELSE 'broad-mathlib (mixed)'
            END as corpus_difficulty,
            SUM(CASE WHEN i.baseline_solved THEN 1 ELSE 0 END) as on_solved,
            SUM(CASE WHEN i.baseline_solved AND i.solved THEN 1 ELSE 0 END) as recovered,
            SUM(CASE WHEN i.baseline_solved AND NOT i.solved THEN 1 ELSE 0 END) as collapsed,
            ROUND(100.0 * SUM(CASE WHEN i.baseline_solved AND i.solved THEN 1 ELSE 0 END) /
                NULLIF(SUM(CASE WHEN i.baseline_solved THEN 1 ELSE 0 END), 0), 1) as recovery_pct
        FROM theorem_intervention i
        JOIN runs r ON i.run_key = r.run_key
        JOIN selected_run_keys s ON r.run_key = s.run_key
        WHERE i.is_control != true
        GROUP BY r.provider, corpus_difficulty
    """).df()
    difficulty_df = difficulty_df[difficulty_df["provider"].isin(provider_filter.value)]

    fig_difficulty = px.bar(
        difficulty_df,
        x="corpus_difficulty",
        y="recovery_pct",
        title="Recovery Rate vs Corpus Difficulty",
        labels={"recovery_pct": "Recovery Rate (%)", "corpus_difficulty": "Corpus"},
        color="provider",
        barmode="group",
        color_discrete_map={
            "deepseek": "#3498db",
            "reprover": "#e67e22",
            "heuristic": "#7f8c8d",
        },
    ) if len(difficulty_df) > 0 else None

    diff_table = difficulty_df.to_markdown(index=False) if len(difficulty_df) > 0 else "No data."

    mo.md(f"""
    ## Section 5c: Difficulty Modulates Resilience

    **Claim**: Recovery capacity depends on proof-space topology. Easy theorems
    have richer proof landscapes with multiple viable paths; hard theorems have
    narrow corridors where any perturbation causes collapse.

    {diff_table}
    """)
    return difficulty_df, fig_difficulty


@app.cell
def _(fig_difficulty, mo):
    if fig_difficulty is not None:
        mo.ui.plotly(fig_difficulty)
    return


# ---------------------------------------------------------------------------
# Section 6: Controller Lesion Effects
# ---------------------------------------------------------------------------


@app.cell
def _(conn, mo, pd, provider_filter, px):
    lesion_runs_df = conn.execute("""
        SELECT r.run_id, r.provider, r.run_key,
               a.theorem_count, a.wild_type_solve_rate, a.intervention_count
        FROM runs r
        JOIN run_aggregates a ON r.run_key = a.run_key
        JOIN selected_run_keys s ON r.run_key = s.run_key
        WHERE r.run_id LIKE '%scheduler%' OR r.run_id LIKE '%condition=%'
        ORDER BY r.run_id
    """).df()
    lesion_runs_df = lesion_runs_df[lesion_runs_df["provider"].isin(provider_filter.value)]

    lesion_metrics_df = conn.execute("""
        SELECT r.run_id, r.provider,
               m.iteration_count, m.expanded_count, m.blocked_count,
               m.no_expansion_count, m.delayed_count,
               m.max_tree_nodes, m.max_tree_depth,
               m.avg_candidate_count
        FROM mcts_controller_metrics m
        JOIN runs r ON m.run_key = r.run_key
        JOIN selected_run_keys s ON r.run_key = s.run_key
        WHERE r.run_id LIKE '%scheduler%' OR r.run_id LIKE '%condition=%'
    """).df()
    lesion_metrics_df = lesion_metrics_df[lesion_metrics_df["provider"].isin(provider_filter.value)]

    lesion_agg = pd.DataFrame()
    if len(lesion_runs_df) > 0:
        fig_lesion_solve = px.bar(
            lesion_runs_df,
            x="run_id",
            y="wild_type_solve_rate",
            title="Solve Rate by Lesion Condition",
            labels={"wild_type_solve_rate": "Solve Rate", "run_id": "Condition"},
            color="provider",
        )
        fig_lesion_solve.update_xaxes(tickangle=45)
    else:
        fig_lesion_solve = None

    if len(lesion_metrics_df) > 0:
        lesion_agg = lesion_metrics_df.groupby(["provider", "run_id"]).agg(
            avg_iterations=("iteration_count", "mean"),
            avg_blocked=("blocked_count", "mean"),
            avg_depth=("max_tree_depth", "mean"),
            count=("iteration_count", "count"),
        ).reset_index()
        lesion_table = lesion_agg.to_markdown(index=False)
    else:
        lesion_table = "No lesion metrics data available."

    mo.md(f"""
    ## Section 6: Controller Lesion Effects

    **Claim**: Scheduler lesions produce measurable search behavior changes.

    {len(lesion_runs_df)} lesion runs found.

    ### MCTS Profile by Condition
    {lesion_table}
    """)
    return fig_lesion_solve, lesion_agg, lesion_metrics_df, lesion_runs_df, lesion_table


@app.cell
def _(fig_lesion_solve, mo):
    if fig_lesion_solve is not None:
        mo.ui.plotly(fig_lesion_solve)
    return


# ---------------------------------------------------------------------------
# Section 7: Cross-Assistant Lean/Rocq Signal
# ---------------------------------------------------------------------------


@app.cell
def _(conn, mo, pd, provider_filter, px):
    cross_df = conn.execute("""
        SELECT r.provider, r.corpus, w.theorem, w.solved, w.proof_term_hash
        FROM theorem_wild w
        JOIN runs r ON w.run_key = r.run_key
        JOIN selected_run_keys s ON r.run_key = s.run_key
        WHERE r.corpus LIKE '%coq-paired%'
    """).df()
    cross_df = cross_df[cross_df["provider"].isin(provider_filter.value)]

    agree = both_solved = either_solved = neither = total_pairs = 0
    pe = pe_solved = pe_unsolved = po = 0.0
    kappa = float("nan")
    cols = []
    pivot = pd.DataFrame()

    if len(cross_df) > 0:
        cross_summary = cross_df.groupby("provider").agg(
            theorems=("theorem", "nunique"),
            solved=("solved", "sum"),
            solve_rate=("solved", "mean"),
        ).reset_index()
        cross_summary["solve_rate"] = (cross_summary["solve_rate"] * 100).round(1)

        fig_cross = px.bar(
            cross_summary,
            x="provider",
            y="solve_rate",
            title="Solve Rate on Lean/Rocq Paired Benchmark (84 theorems)",
            labels={"solve_rate": "Solve Rate (%)", "provider": "Provider"},
        )

        pivot = cross_df.pivot_table(index="theorem", columns="provider", values="solved", aggfunc="any")
        if len(pivot.columns) >= 2:
            cols = list(pivot.columns)
            both_solved = ((pivot[cols[0]] == True) & (pivot[cols[1]] == True)).sum()
            either_solved = ((pivot[cols[0]] == True) | (pivot[cols[1]] == True)).sum()
            neither = ((pivot[cols[0]] != True) & (pivot[cols[1]] != True)).sum()
            agree = ((pivot[cols[0]] == pivot[cols[1]])).sum()
            total_pairs = len(pivot)

            po = agree / total_pairs
            pe_solved = (pivot[cols[0]].sum() / total_pairs) * (pivot[cols[1]].sum() / total_pairs)
            pe_unsolved = (1 - pivot[cols[0]].sum() / total_pairs) * (1 - pivot[cols[1]].sum() / total_pairs)
            pe = pe_solved + pe_unsolved
            kappa = (po - pe) / (1 - pe) if pe < 1 else 0

            cross_agreement = f"""
    Both solved: **{both_solved}**, Either solved: **{either_solved}**, Neither: **{neither}**
    Agreement rate: **{100*po:.1f}%**, Cohen's kappa: **{kappa:.3f}**
    """
        else:
            cross_agreement = "Insufficient providers for agreement analysis."

        cross_table = cross_summary.to_markdown(index=False)
    else:
        fig_cross = None
        cross_table = "No cross-assistant data."
        cross_agreement = ""

    mo.md(f"""
    ## Section 7: Cross-Assistant Lean/Rocq Solve Agreement

    **What this section does measure**: solve agreement on matched Lean/Rocq theorem pairs.

    **What it does not yet measure**: structural cross-assistant proof-graph alignment.
    Treat this as a coverage/agreement section, not a structural-signal section.

    ### Solve rates by provider
    {cross_table}

    ### Agreement
    {cross_agreement}
    """)
    return (
        agree, both_solved, cols, cross_agreement, cross_df, cross_summary,
        cross_table, either_solved, fig_cross, kappa, neither, pe, pe_solved,
        pe_unsolved, pivot, po, total_pairs,
    )


@app.cell
def _(fig_cross, mo):
    if fig_cross is not None:
        mo.ui.plotly(fig_cross)
    return


# ---------------------------------------------------------------------------
# Section 8: Key Findings Summary
# ---------------------------------------------------------------------------


@app.cell
def _(
    avg_dom_freq, avg_entropy, avg_structures, col,
    kappa, kw_p, mean_dk, mo, recovery_rate, rep, rer, total, wil_p,
):
    summary_data = [
        ("Response Modes", f"{rep} replicate, {rer} reroute, {col} collapse (n={total}, strict control gate)", "SUPPORTED" if rer > 10 else "WEAK"),
        ("GED Divergence", f"Kruskal-Wallis p={kw_p:.2e}", "SUPPORTED" if kw_p < 0.05 else "NOT SIGNIFICANT"),
        ("Trajectory Recovery", f"{recovery_rate:.1f}% recovery rate", "SUPPORTED" if recovery_rate > 20 else "WEAK"),
        ("Basin Stability", f"{avg_structures:.1f} structures, {avg_dom_freq:.2f} dominant freq, {avg_entropy:.2f} bits entropy", "SUPPORTED" if avg_dom_freq > 0.3 else "WEAK"),
        ("K-Score Effects", f"Mean delta-K={mean_dk:.3f}, Wilcoxon p={wil_p:.2e}", "SUPPORTED" if wil_p < 0.05 else "NOT SIGNIFICANT"),
        ("Cross-Assistant Solve Agreement", f"Cohen's kappa={kappa:.3f}", "PRELIMINARY" if kappa == kappa else "NO DATA"),
        ("Cross-Assistant Structural Signal", "Not directly measured in this notebook", "NOT YET TESTED"),
    ]

    rows = "\n".join(f"| {claim} | {evidence} | {verdict} |" for claim, evidence, verdict in summary_data)

    mo.md(f"""
    ## Section 8: Key Findings Summary

    | Claim | Evidence | Verdict |
    |-------|----------|---------|
    {rows}
    """)
    return rows, summary_data


if __name__ == "__main__":
    app.run()
