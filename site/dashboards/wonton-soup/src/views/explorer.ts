import { query, queryScalar, runFilterSql } from "../db";
import { renderHistogram } from "../viz/histogram";
import { renderHeatmap, type HeatmapCell } from "../viz/heatmap";
import type { GoalTypeTactic } from "../types";

interface ExplorerOpts {
  runKey: string;
}

export async function mountExplorer(container: HTMLElement, opts: ExplorerOpts): Promise<void> {
  container.className = "view-light";

  const titleEl = document.createElement("h2");
  titleEl.className = "section-title";
  titleEl.textContent = "Data Explorer";
  container.appendChild(titleEl);

  const grid = document.createElement("div");
  grid.className = "explorer-grid";
  container.appendChild(grid);

  await Promise.all([
    renderSummaryCards(grid, opts.runKey),
    renderGedHistograms(grid, opts.runKey),
    renderKMetrics(grid, opts.runKey),
    renderPostprocessMetrics(grid, opts.runKey),
    renderGoalTacticHeatmap(grid, opts.runKey),
  ]);
}

async function renderSummaryCards(grid: HTMLElement, runKey: string): Promise<void> {
  const panel = createPanel(grid, "Summary");
  const statsGrid = document.createElement("div");
  statsGrid.style.display = "grid";
  statsGrid.style.gridTemplateColumns = "repeat(3, 1fr)";
  statsGrid.style.gap = "0.75rem";
  panel.appendChild(statsGrid);

  const theoremCount = await queryScalar<number>(
    `SELECT count(DISTINCT tw.theorem)
     FROM theorem_wild tw
     WHERE ${runFilterSql(runKey, "tw")} AND ${interventionTheoremExistsSql(runKey, "tw")}`,
  );
  const wildSolveRate = await queryScalar<number>(
    `SELECT round(avg(CASE WHEN solved THEN 1.0 ELSE 0.0 END) * 100, 1)
     FROM theorem_wild tw
     WHERE ${runFilterSql(runKey, "tw")} AND ${interventionTheoremExistsSql(runKey, "tw")}`,
  );
  const interventionSolveRate = await queryScalar<number>(
    `SELECT round(avg(CASE WHEN solved THEN 1.0 ELSE 0.0 END) * 100, 1)
     FROM theorem_intervention WHERE ${runFilterSql(runKey)} AND is_control = false`,
  );

  addStat(statsGrid, String(theoremCount), "Intervention Theorems");
  addStat(statsGrid, `${wildSolveRate}%`, "Wild Solve Rate");
  addStat(statsGrid, `${interventionSolveRate}%`, "Intervention Solve Rate");
}

async function renderGedHistograms(grid: HTMLElement, runKey: string): Promise<void> {
  const panel = createPanel(grid, "GED Distributions");
  const histRow = document.createElement("div");
  histRow.style.display = "flex";
  histRow.style.gap = "1rem";
  histRow.style.flexWrap = "wrap";
  panel.appendChild(histRow);

  const searchGeds = await query<{ v: number }>(
    `SELECT ged_search_norm AS v FROM theorem_intervention_comparison
     WHERE ${runFilterSql(runKey)} AND ged_search_valid = true`,
  );

  const proofGeds = await query<{ v: number }>(
    `SELECT ged_proof_norm AS v FROM theorem_intervention_comparison
     WHERE ${runFilterSql(runKey)} AND ged_proof_valid = true`,
  );

  const traceGeds = await query<{ v: number }>(
    `SELECT ged_trace_norm AS v FROM theorem_intervention_comparison
     WHERE ${runFilterSql(runKey)} AND ged_trace_valid = true`,
  );

  for (const [label, data, color] of [
    ["Search GED", searchGeds, "#4a8a61"],
    ["Proof GED", proofGeds, "#4f66bc"],
    ["Trace GED", traceGeds, "#8694ad"],
  ] as [string, { v: number }[], string][]) {
    const histContainer = document.createElement("div");
    histRow.appendChild(histContainer);
    renderHistogram({
      container: histContainer,
      values: data.map((r) => r.v).filter((v) => v != null),
      label,
      color,
      bins: 15,
    });
  }
}

async function renderGoalTacticHeatmap(grid: HTMLElement, runKey: string): Promise<void> {
  const panel = createPanel(grid, "Top Goal Type x Tactic");
  panel.style.gridColumn = "1 / -1";

  const rows = await query<GoalTypeTactic>(
    `WITH agg AS (
       SELECT goal_type, tactic_norm,
              sum(success) AS success,
              sum(failure) AS failure,
              sum(blocked) AS blocked,
              sum(total) AS total
       FROM goal_type_tactic
       WHERE ${runFilterSql(runKey)} AND ${interventionRunSql(runKey)}
       GROUP BY goal_type, tactic_norm
     ),
     top_goals AS (
       SELECT goal_type
       FROM agg
       GROUP BY goal_type
       ORDER BY sum(total) DESC
       LIMIT 40
     ),
     top_tactics AS (
       SELECT tactic_norm
       FROM agg
       GROUP BY tactic_norm
       ORDER BY sum(total) DESC
       LIMIT 40
     )
     SELECT agg.goal_type, agg.tactic_norm,
            sum(success) AS success,
            sum(failure) AS failure,
            sum(blocked) AS blocked,
            sum(total) AS total
     FROM agg
     JOIN top_goals USING(goal_type)
     JOIN top_tactics USING(tactic_norm)
     GROUP BY agg.goal_type, agg.tactic_norm
     ORDER BY total DESC, agg.goal_type, agg.tactic_norm`,
  );

  if (rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No goal-type/tactic data.";
    panel.appendChild(empty);
    return;
  }

  const goalTypes = sortedUniqueByTotal(rows, (row) => row.goal_type);
  const tactics = sortedUniqueByTotal(rows, (row) => row.tactic_norm);
  const totals = rows.map((r) => numberValue(r.total) ?? 0);

  const maxTotal = Math.max(...totals);
  const cells: HeatmapCell[] = rows.map((r, index) => {
    const total = totals[index];
    return {
      row: r.goal_type,
      col: r.tactic_norm,
      value: total,
      category: total > maxTotal * 0.5 ? "high" : total > maxTotal * 0.1 ? "mid" : "low",
    };
  });

  const hmContainer = document.createElement("div");
  hmContainer.style.overflowX = "auto";
  panel.appendChild(hmContainer);

  renderHeatmap({
    container: hmContainer,
    cells,
    rows: goalTypes,
    cols: tactics,
    colorMap: {
      high: "#2f6f64",
      mid: "#8db6af",
      low: "#d4e4e1",
      "no-data": "#f0f0f0",
    },
    cellSize: 18,
  });
}

function sortedUniqueByTotal<T>(rows: T[], getKey: (row: T) => string): string[] {
  const totals = new Map<string, number>();
  for (const row of rows as (T & { total: number | bigint })[]) {
    const key = getKey(row);
    totals.set(key, (totals.get(key) ?? 0) + (numberValue(row.total) ?? 0));
  }
  return Array.from(totals.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([key]) => key);
}

async function renderKMetrics(grid: HTMLElement, runKey: string): Promise<void> {
  const panel = createPanel(grid, "K Computation");

  const kRows = await query<{
    source: string;
    theorem: string;
    variant: string;
    k_valid: boolean | null;
    k_null_model: string | null;
    k_tau_agent: number | null;
    k_tau_blind: number | null;
    k_K: number | null;
  }>(
    `SELECT 'wild' AS source, theorem, 'wild_type' AS variant,
            k_valid, k_null_model, k_tau_agent, k_tau_blind, k_K
     FROM theorem_wild
     WHERE ${runFilterSql(runKey)} AND ${interventionTheoremExistsSql(runKey, "theorem_wild")}
     UNION ALL
     SELECT 'intervention' AS source, theorem, intervention AS variant,
            k_valid, k_null_model, k_tau_agent, k_tau_blind, k_K
     FROM theorem_intervention
     WHERE ${runFilterSql(runKey)} AND is_control = false
     ORDER BY source, theorem, variant`,
  );

  const validRows = kRows.filter((row) => row.k_valid === true && row.k_K != null);
  if (kRows.length === 0 || validRows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No local postprocess K data for this dataset.";
    panel.appendChild(empty);
    return;
  }

  const summary = summarizeKRows(kRows);
  const statsGrid = document.createElement("div");
  statsGrid.className = "explorer-stat-grid";
  panel.appendChild(statsGrid);
  addStat(statsGrid, `${summary.valid}/${summary.total}`, "Valid K Rows");
  addStat(statsGrid, formatNumber(summary.meanK, 3), "Mean K");
  addStat(statsGrid, formatNumber(summary.meanTauAgent, 1), "Mean Agent Attempts");
  addStat(statsGrid, formatNumber(summary.meanTauBlind, 1), "Mean Blind Attempts");

  const histContainer = document.createElement("div");
  histContainer.className = "explorer-hist-row";
  panel.appendChild(histContainer);
  renderHistogram({
    container: histContainer,
    values: validRows.map((r) => r.k_K!).filter((v) => v != null),
    label: "local postprocess K = log10(tau_blind / tau_agent)",
    color: "#ff6600",
    bins: 20,
    width: 420,
    height: 200,
  });

  const variantSummary = summarizeKByVariant(kRows).slice(0, 12);
  const table = createTable(
    ["Variant", "Rows", "Valid", "Mean K", "Mean Tau Agent", "Mean Tau Blind"],
    variantSummary.map((row) => [
      row.variant,
      String(row.total),
      String(row.valid),
      formatNumber(row.meanK, 3),
      formatNumber(row.meanTauAgent, 1),
      formatNumber(row.meanTauBlind, 1),
    ]),
  );
  panel.appendChild(table);
}

async function renderPostprocessMetrics(grid: HTMLElement, runKey: string): Promise<void> {
  const panel = createPanel(grid, "Postprocess Metrics");

  const summary = await query<{
    variant_rows: number;
    theorem_count: number;
    proof_term_rows: number;
    mean_proof_nodes: number | null;
    mean_solution_path_len: number | null;
    mean_iterations: number | null;
    mean_detour_attempts: number | null;
  }>(
    `SELECT
       count(*) AS variant_rows,
       count(DISTINCT theorem) AS theorem_count,
       count(proof_term_node_count) AS proof_term_rows,
       avg(proof_term_node_count) AS mean_proof_nodes,
       avg(solution_path_len) AS mean_solution_path_len,
       avg(trajectory_total_iterations) AS mean_iterations,
       avg(detour_total_attempts) AS mean_detour_attempts
     FROM theorem_variant_metrics
     WHERE ${runFilterSql(runKey)} AND ${interventionTheoremExistsSql(runKey, "theorem_variant_metrics")}`,
  );

  const row = summary[0];
  if (!row || row.variant_rows === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No postprocess variant metrics for this dataset.";
    panel.appendChild(empty);
    return;
  }

  const statsGrid = document.createElement("div");
  statsGrid.className = "explorer-stat-grid";
  panel.appendChild(statsGrid);
  addStat(statsGrid, String(row.theorem_count), "Intervention Theorems");
  addStat(statsGrid, String(row.variant_rows), "Variant Rows");
  addStat(statsGrid, String(row.proof_term_rows), "Proof Terms");
  addStat(statsGrid, formatNumber(row.mean_proof_nodes, 0), "Mean Proof Nodes");
  addStat(statsGrid, formatNumber(row.mean_solution_path_len, 1), "Mean Path Len");
  addStat(statsGrid, formatNumber(row.mean_detour_attempts, 1), "Mean Attempts");

  const proofRows = await query<{
    theorem: string;
    variant: string;
    proof_term_node_count: number | null;
    solution_path_len: number | null;
    trajectory_total_iterations: number | null;
    detour_total_attempts: number | null;
  }>(
    `SELECT theorem, variant, proof_term_node_count, solution_path_len,
            trajectory_total_iterations, detour_total_attempts
     FROM theorem_variant_metrics
     WHERE ${runFilterSql(runKey)} AND ${interventionTheoremExistsSql(runKey, "theorem_variant_metrics")}
       AND proof_term_node_count IS NOT NULL
     ORDER BY proof_term_node_count DESC
     LIMIT 10`,
  );

  const table = createTable(
    ["Theorem", "Variant", "Proof Nodes", "Path Len", "Iterations", "Attempts"],
    proofRows.map((metric) => [
      metric.theorem,
      metric.variant,
      formatNumber(metric.proof_term_node_count, 0),
      formatNumber(metric.solution_path_len, 0),
      formatNumber(metric.trajectory_total_iterations, 0),
      formatNumber(metric.detour_total_attempts, 0),
    ]),
  );
  panel.appendChild(table);
}

function createPanel(parent: HTMLElement, title: string): HTMLElement {
  const panel = document.createElement("div");
  panel.className = "explorer-panel";

  const titleEl = document.createElement("h3");
  titleEl.className = "explorer-panel-title";
  titleEl.textContent = title;
  panel.appendChild(titleEl);

  parent.appendChild(panel);
  return panel;
}

function interventionTheoremExistsSql(runKey: string, alias: string): string {
  return `EXISTS (
    SELECT 1
    FROM theorem_intervention ti
    WHERE ${runFilterSql(runKey, "ti")} AND ti.is_control = false
      AND ti.theorem = ${alias}.theorem
  )`;
}

function interventionRunSql(runKey: string): string {
  return `run_key IN (
    SELECT DISTINCT run_key
    FROM theorem_intervention ti
    WHERE ${runFilterSql(runKey, "ti")} AND ti.is_control = false
  )`;
}

function addStat(container: HTMLElement, value: string, label: string): void {
  const card = document.createElement("div");
  card.className = "stat-card";

  const valueEl = document.createElement("div");
  valueEl.className = "stat-value";
  valueEl.textContent = value;

  const labelEl = document.createElement("div");
  labelEl.className = "stat-label";
  labelEl.textContent = label;

  card.append(valueEl, labelEl);
  container.appendChild(card);
}

interface KSummary {
  total: number;
  valid: number;
  meanK: number | null;
  meanTauAgent: number | null;
  meanTauBlind: number | null;
}

function summarizeKRows(
  rows: {
    k_valid: boolean | null;
    k_tau_agent: number | null;
    k_tau_blind: number | null;
    k_K: number | null;
  }[],
): KSummary {
  const valid = rows.filter((row) => row.k_valid === true && row.k_K != null);
  return {
    total: rows.length,
    valid: valid.length,
    meanK: mean(valid.map((row) => row.k_K)),
    meanTauAgent: mean(valid.map((row) => row.k_tau_agent)),
    meanTauBlind: mean(valid.map((row) => row.k_tau_blind)),
  };
}

function summarizeKByVariant(
  rows: {
    variant: string;
    k_valid: boolean | null;
    k_tau_agent: number | null;
    k_tau_blind: number | null;
    k_K: number | null;
  }[],
): (KSummary & { variant: string })[] {
  const byVariant = new Map<string, typeof rows>();
  for (const row of rows) {
    const group = byVariant.get(row.variant) ?? [];
    group.push(row);
    byVariant.set(row.variant, group);
  }

  return Array.from(byVariant.entries())
    .map(([variant, group]) => ({ variant, ...summarizeKRows(group) }))
    .sort((a, b) => b.valid - a.valid || (b.meanK ?? -Infinity) - (a.meanK ?? -Infinity));
}

function mean(values: (number | null)[]): number | null {
  const nums = values
    .map(numberValue)
    .filter((value): value is number => value != null && Number.isFinite(value));
  if (nums.length === 0) return null;
  return nums.reduce((acc, value) => acc + value, 0) / nums.length;
}

function numberValue(value: number | bigint | null): number | null {
  if (typeof value === "bigint") return Number(value);
  return value;
}

function formatNumber(value: number | bigint | null, digits: number): string {
  const n = numberValue(value);
  if (n == null || !Number.isFinite(n)) return "n/a";
  return n.toFixed(digits);
}

function createTable(headers: string[], rows: string[][]): HTMLElement {
  const wrap = document.createElement("div");
  wrap.className = "explorer-table-wrap";

  const table = document.createElement("table");
  table.className = "explorer-table";

  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  for (const header of headers) {
    const th = document.createElement("th");
    th.textContent = header;
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);

  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const cell of row) {
      const td = document.createElement("td");
      td.textContent = cell;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }

  table.append(thead, tbody);
  wrap.appendChild(table);
  return wrap;
}

export function unmountExplorer(): void {}
