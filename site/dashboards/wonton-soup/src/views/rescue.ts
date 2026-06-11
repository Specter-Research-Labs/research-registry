import { query, runFilterSql } from "../db";
import { renderHeatmap, type HeatmapCell } from "../viz/heatmap";
import { navigate } from "../router";

interface RescueOpts {
  runKey: string;
}

interface RescueCell {
  theorem: string;
  intervention: string;
  row_count: number | bigint;
  solved_count: number | bigint;
  failed_count: number | bigint;
  baseline_solved_count: number | bigint;
}

const RESCUE_COLORS: Record<string, string> = {
  rescued: "#3f8458",
  collapsed: "#b4573d",
  unchanged: "#c4c9cf",
  "no-data": "#e8eaed",
};

export async function mountRescue(container: HTMLElement, opts: RescueOpts): Promise<void> {
  container.className = "view-light";

  const titleEl = document.createElement("h2");
  titleEl.className = "section-title";
  titleEl.textContent = "Rescue Matrix";
  container.appendChild(titleEl);

  const wrapper = document.createElement("div");
  wrapper.className = "rescue-container";
  container.appendChild(wrapper);

  const rows = await query<RescueCell>(
    `SELECT theorem, intervention,
            count(*) AS row_count,
            sum(CASE WHEN solved THEN 1 ELSE 0 END) AS solved_count,
            sum(CASE WHEN solved = false THEN 1 ELSE 0 END) AS failed_count,
            sum(CASE WHEN baseline_solved THEN 1 ELSE 0 END) AS baseline_solved_count
     FROM theorem_intervention
     WHERE ${runFilterSql(opts.runKey)} AND is_control = false
     GROUP BY theorem, intervention
     ORDER BY theorem, intervention`,
  );

  if (rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No intervention data for this dataset.";
    wrapper.appendChild(empty);
    return;
  }

  const theorems = [...new Set(rows.map((r) => r.theorem))];
  const interventions = [...new Set(rows.map((r) => r.intervention))];

  const cells: HeatmapCell[] = rows.map((r) => ({
    row: r.intervention,
    col: r.theorem,
    value: numberValue(r.solved_count) / Math.max(1, numberValue(r.row_count)),
    category: categorize(r),
  }));

  renderHeatmap({
    container: wrapper,
    cells,
    rows: interventions,
    cols: theorems,
    colorMap: RESCUE_COLORS,
    cellSize: 32,
    onCellClick: (intervention, theorem) => {
      navigate("hero", { theorem, intervention });
    },
  });
}

function categorize(r: RescueCell): string {
  const total = numberValue(r.row_count);
  const solved = numberValue(r.solved_count);
  const failed = numberValue(r.failed_count);
  const baselineSolved = numberValue(r.baseline_solved_count);
  if (total === 0) return "no-data";
  if (baselineSolved === 0 && solved > 0) return "rescued";
  if (baselineSolved > 0 && solved === 0 && failed > 0) return "collapsed";
  if (baselineSolved > 0 && solved > 0) return "unchanged";
  return "unchanged";
}

function numberValue(value: number | bigint): number {
  return typeof value === "bigint" ? Number(value) : value;
}

export function unmountRescue(): void {}
