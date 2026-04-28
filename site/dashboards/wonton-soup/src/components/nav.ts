import type { ViewId } from "../types";
import { navigate } from "../router";

const TABS: { id: ViewId; label: string }[] = [
  { id: "hero", label: "Proof Trees" },
  { id: "proof-graph", label: "Proof Graph" },
  { id: "rescue", label: "Rescue Matrix" },
  { id: "explorer", label: "Explorer" },
];

let _root: HTMLElement | null = null;
let _runSelect: HTMLSelectElement | null = null;
let _onRunChange: ((runKey: string) => void) | null = null;

export function mountNav(
  container: HTMLElement,
  opts: { onRunChange: (runKey: string) => void },
): void {
  _onRunChange = opts.onRunChange;

  const nav = document.createElement("nav");
  nav.className = "dash-nav";

  const tabGroup = document.createElement("div");
  tabGroup.className = "dash-nav-tabs";

  for (const tab of TABS) {
    const btn = document.createElement("button");
    btn.className = "dash-nav-tab";
    btn.dataset.view = tab.id;
    btn.textContent = tab.label;
    btn.addEventListener("click", () => navigate(tab.id));
    tabGroup.appendChild(btn);
  }

  const runSelect = document.createElement("select");
  runSelect.className = "dash-nav-run-select";
  runSelect.addEventListener("change", () => {
    _onRunChange?.(runSelect.value);
  });
  _runSelect = runSelect;

  nav.append(tabGroup, runSelect);
  container.prepend(nav);
  _root = nav;
}

export function setActiveTab(viewId: ViewId): void {
  if (!_root) return;
  for (const btn of _root.querySelectorAll<HTMLButtonElement>(".dash-nav-tab")) {
    btn.classList.toggle("active", btn.dataset.view === viewId);
  }
}

export function populateRuns(runKeys: string[], labels: Map<string, string>): void {
  if (!_runSelect) return;
  _runSelect.replaceChildren();
  for (const key of runKeys) {
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = labels.get(key) ?? key.slice(0, 12);
    _runSelect.appendChild(opt);
  }
}

export function getSelectedRun(): string | null {
  return _runSelect?.value ?? null;
}
