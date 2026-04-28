import { query } from "../db";
import { renderHeatmap, type HeatmapCell } from "../viz/heatmap";
import { navigate } from "../router";
import type { TheoremIntervention } from "../types";

interface RescueOpts {
  runKey: string;
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

  const rows = await query<TheoremIntervention>(
    `SELECT theorem, intervention, solved, status, baseline_solved
     FROM theorem_intervention
     WHERE run_key = '${opts.runKey}' AND is_control = false
     ORDER BY theorem, intervention`,
  );

  if (rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No intervention data for this run.";
    wrapper.appendChild(empty);
    return;
  }

  const theorems = [...new Set(rows.map((r) => r.theorem))];
  const interventions = [...new Set(rows.map((r) => r.intervention))];

  const cells: HeatmapCell[] = rows.map((r) => ({
    row: r.intervention,
    col: r.theorem,
    value: r.solved != null ? (r.solved ? 1 : 0) : null,
    category: categorize(r),
  }));

  renderHeatmap({
    container: wrapper,
    cells,
    rows: interventions,
    cols: theorems,
    colorMap: RESCUE_COLORS,
    onCellClick: (intervention, theorem) => {
      navigate("hero", { theorem, intervention });
    },
  });
}

function categorize(r: TheoremIntervention): string {
  if (r.baseline_solved === true && r.solved === true) return "unchanged";
  if (r.baseline_solved === true && r.solved === false) return "collapsed";
  if (r.baseline_solved === false && r.solved === true) return "rescued";
  if (r.solved == null) return "no-data";
  return "unchanged";
}

export function unmountRescue(): void {}
