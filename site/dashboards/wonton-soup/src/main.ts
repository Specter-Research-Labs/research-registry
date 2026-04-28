import { initDB, getRunKeys, query } from "./db";
import { startRouter } from "./router";
import { mountNav, setActiveTab, populateRuns, getSelectedRun } from "./components/nav";
import { showLoading, hideLoading, showError } from "./components/loading";
import { mountHero, unmountHero } from "./views/hero";
import { mountProofGraph, unmountProofGraph } from "./views/proof-graph";
import { mountRescue, unmountRescue } from "./views/rescue";
import { mountExplorer, unmountExplorer } from "./views/explorer";
import type { ViewId, Run, RunAggregate } from "./types";

const app = document.getElementById("app")!;
let currentView: ViewId | null = null;

async function boot(): Promise<void> {
  showLoading("Initializing DuckDB-WASM");

  try {
    await initDB((msg) => showLoading(msg));
  } catch (err) {
    showError(
      "Failed to initialize",
      "Could not load DuckDB-WASM or connect to the data server.",
      err instanceof Error ? err.stack ?? err.message : String(err),
    );
    return;
  }

  const runKeys = await getRunKeys();
  if (runKeys.length === 0) {
    showError("No data", "The manifest loaded but no runs were found.");
    return;
  }

  const runs = await query<Run & RunAggregate>(
    `SELECT r.*, a.theorem_count, a.wild_type_solve_rate
     FROM runs r
     LEFT JOIN run_aggregates a USING(run_key)
     WHERE r.run_key IN (
       SELECT run_key FROM mcts_tree_nodes
       GROUP BY run_key
       HAVING count(DISTINCT variant) >= 2
     )
     ORDER BY r.created_at DESC NULLS LAST`,
  );
  const SHORT_MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];

  const labels = new Map<string, string>();
  for (const r of runs) {
    const parts: string[] = [];

    if (r.provider) parts.push(r.provider);

    if (r.theorem_count != null) parts.push(`${r.theorem_count} theorems`);

    const rawId = r.run_id ?? "";
    const controlMatch = rawId.match(/control=([^/]+)/);
    if (controlMatch) {
      parts.push(controlMatch[1]);
    } else {
      const segments = rawId.split("/");
      for (const seg of segments) {
        if (/\b(centralized|distributed)\b/.test(seg)) {
          const modeMatch = seg.match(/\b(centralized|distributed)\b/);
          if (modeMatch) parts.push(modeMatch[1]);
          break;
        }
      }
    }

    if (r.created_at) {
      const d = new Date(r.created_at);
      if (!isNaN(d.getTime())) {
        parts.push(`${SHORT_MONTHS[d.getMonth()]} ${d.getDate()}`);
      }
    }

    labels.set(r.run_key, parts.length > 0 ? parts.join(" / ") : r.run_key.slice(0, 16));
  }

  mountNav(app, { onRunChange: () => rerenderCurrentView() });
  populateRuns(
    runs.map((r) => r.run_key),
    labels,
  );

  hideLoading();

  startRouter((viewId, params) => {
    switchView(viewId, params);
  });
}

function getViewContainer(): HTMLElement {
  let container = document.getElementById("view-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "view-container";
    app.appendChild(container);
  }
  return container;
}

async function switchView(viewId: ViewId, params: URLSearchParams): Promise<void> {
  if (currentView) {
    teardownView(currentView);
  }

  currentView = viewId;
  setActiveTab(viewId);

  const container = getViewContainer();
  container.replaceChildren();

  const runKey = getSelectedRun();
  if (!runKey) return;

  switch (viewId) {
    case "hero":
      await mountHero(container, {
        runKey,
        theorem: params.get("theorem") ?? undefined,
        intervention: params.get("intervention") ?? undefined,
      });
      break;
    case "proof-graph":
      await mountProofGraph(container, {
        runKey,
        theorem: params.get("theorem") ?? undefined,
        variant: params.get("variant") ?? undefined,
      });
      break;
    case "rescue":
      await mountRescue(container, { runKey });
      break;
    case "explorer":
      await mountExplorer(container, { runKey });
      break;
  }
}

function teardownView(viewId: ViewId): void {
  switch (viewId) {
    case "hero":
      unmountHero();
      break;
    case "proof-graph":
      unmountProofGraph();
      break;
    case "rescue":
      unmountRescue();
      break;
    case "explorer":
      unmountExplorer();
      break;
  }
}

function rerenderCurrentView(): void {
  if (!currentView) return;
  switchView(currentView, new URLSearchParams());
}

boot();
