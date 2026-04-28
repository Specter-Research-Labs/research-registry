import { query, queryScalar } from "../db";
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
    renderGoalTacticHeatmap(grid, opts.runKey),
    renderKMetrics(grid, opts.runKey),
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
    `SELECT count(DISTINCT theorem) FROM theorem_wild WHERE run_key = '${runKey}'`,
  );
  const wildSolveRate = await queryScalar<number>(
    `SELECT round(avg(CASE WHEN solved THEN 1.0 ELSE 0.0 END) * 100, 1)
     FROM theorem_wild WHERE run_key = '${runKey}'`,
  );
  const interventionSolveRate = await queryScalar<number>(
    `SELECT round(avg(CASE WHEN solved THEN 1.0 ELSE 0.0 END) * 100, 1)
     FROM theorem_intervention WHERE run_key = '${runKey}' AND is_control = false`,
  );

  addStat(statsGrid, String(theoremCount), "Theorems");
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
     WHERE run_key = '${runKey}' AND ged_search_valid = true`,
  );

  const proofGeds = await query<{ v: number }>(
    `SELECT ged_proof_norm AS v FROM theorem_intervention_comparison
     WHERE run_key = '${runKey}' AND ged_proof_valid = true`,
  );

  const traceGeds = await query<{ v: number }>(
    `SELECT ged_trace_norm AS v FROM theorem_intervention_comparison
     WHERE run_key = '${runKey}' AND ged_trace_valid = true`,
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
  const panel = createPanel(grid, "Goal Type x Tactic");
  panel.style.gridColumn = "1 / -1";

  const rows = await query<GoalTypeTactic>(
    `SELECT goal_type, tactic_norm, success, failure, blocked, total
     FROM goal_type_tactic
     WHERE run_key = '${runKey}'
     ORDER BY goal_type, tactic_norm`,
  );

  if (rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No goal-type/tactic data.";
    panel.appendChild(empty);
    return;
  }

  const goalTypes = [...new Set(rows.map((r) => r.goal_type))];
  const tactics = [...new Set(rows.map((r) => r.tactic_norm))];

  const maxTotal = Math.max(...rows.map((r) => r.total));
  const cells: HeatmapCell[] = rows.map((r) => ({
    row: r.goal_type,
    col: r.tactic_norm,
    value: r.total,
    category: r.total > maxTotal * 0.5 ? "high" : r.total > maxTotal * 0.1 ? "mid" : "low",
  }));

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

async function renderKMetrics(grid: HTMLElement, runKey: string): Promise<void> {
  const panel = createPanel(grid, "K-Metric Distribution");

  const kValues = await query<{ v: number }>(
    `SELECT K AS v FROM k_reference_score
     WHERE run_key = '${runKey}' AND valid = true`,
  );

  if (kValues.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No K-metric data for this run.";
    panel.appendChild(empty);
    return;
  }

  const histContainer = document.createElement("div");
  panel.appendChild(histContainer);
  renderHistogram({
    container: histContainer,
    values: kValues.map((r) => r.v).filter((v) => v != null),
    label: "K-metric",
    color: "#8b7142",
    bins: 20,
    width: 360,
    height: 200,
  });
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

export function unmountExplorer(): void {}
