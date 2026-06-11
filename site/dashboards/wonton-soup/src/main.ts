import "./style.css";
import "./specter-polish.css";
import { initDB, getRunKeys, queryOne, PAPER_POSTER_DATASET_KEY } from "./db";
import { replaceRoute, startRouter, navigate } from "./router";
import {
  mountNav,
  setActiveTab,
  populateRuns,
  getSelectedRun,
  setSelectedRun,
} from "./components/nav";
import { showLoading, hideLoading, showError } from "./components/loading";
import { mountHero, unmountHero } from "./views/hero";
import { mountProofGraph, unmountProofGraph } from "./views/proof-graph";
import { mountRescue, unmountRescue } from "./views/rescue";
import { mountExplorer, unmountExplorer } from "./views/explorer";
import type { ViewId } from "./types";

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

  const datasetStats = await queryOne<{
    run_count: number | bigint;
    theorem_count: number | bigint;
    intervention_rows: number | bigint;
  }>(
    `SELECT
       (SELECT count(DISTINCT run_key) FROM theorem_intervention WHERE is_control = false) AS run_count,
       (SELECT count(DISTINCT theorem) FROM theorem_intervention WHERE is_control = false) AS theorem_count,
       (SELECT count(*) FROM theorem_intervention WHERE is_control = false) AS intervention_rows`,
  );
  if (!datasetStats) {
    showError("No data", "The manifest loaded but the paper/poster cohort is empty.");
    return;
  }

  const labels = new Map<string, string>();
  labels.set(
    PAPER_POSTER_DATASET_KEY,
    `Paper/poster intervention cohort / ${formatCount(datasetStats.theorem_count)} theorems / ${
      formatCount(datasetStats.run_count)
    } runs / ${formatCount(datasetStats.intervention_rows)} interventions`,
  );

  mountNav(app, { onRunChange: (runKey) => rerenderCurrentView(runKey) });
  populateRuns(
    [PAPER_POSTER_DATASET_KEY],
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
  setSelectedRun(params.get("run"));

  if (currentView) {
    teardownView(currentView);
  }

  currentView = viewId;
  setActiveTab(viewId);

  const container = getViewContainer();
  container.replaceChildren();

  const runKey = getSelectedRun();
  if (!runKey) return;

  const updateRoute = (next: Record<string, string | null | undefined>) => {
    const merged: Record<string, string | null | undefined> = {
      run: runKey,
      ...next,
    };
    replaceRoute(viewId, merged);
  };

  switch (viewId) {
    case "hero":
      await mountHero(container, {
        runKey,
        theorem: params.get("theorem") ?? undefined,
        intervention: params.get("intervention") ?? undefined,
        onSelectionChange: updateRoute,
      });
      break;
    case "proof-graph":
      await mountProofGraph(container, {
        runKey,
        theorem: params.get("theorem") ?? undefined,
        variant: params.get("variant") ?? undefined,
        onSelectionChange: updateRoute,
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

function rerenderCurrentView(runKey?: string): void {
  if (!currentView) return;
  const next: Record<string, string> = {};
  const selectedRun = runKey ?? getSelectedRun();
  if (selectedRun) next.run = selectedRun;
  navigate(currentView, next);
}

function formatCount(value: number | bigint): string {
  return new Intl.NumberFormat("en-US").format(value);
}

boot();
