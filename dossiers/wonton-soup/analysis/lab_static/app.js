const state = {
  view: "dashboard",
  bootstrap: null,
  analysis: null,
  runs: [],
  contrasts: [],
  jobs: [],
  selectedRun: null,
  selectedContrast: null,
  selectedContrastProvider: null,
  selectedContrastTheorem: null,
  contrastVariant: "wild_type",
  contrastDetail: null,
  selectedTheorem: null,
  runDetail: null,
  theoremDetail: null,
  leftVariant: "wild_type",
  rightVariant: null,
  artifactKind: null,
  runFilter: "",
  artifactCache: new Map(),
  flash: null,
};

const POLL_MS = 3000;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatDate(value) {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function formatNumber(value, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) return "n/a";
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
  });
}

function formatPercent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "n/a";
  return `${(value * 100).toFixed(1)}%`;
}

function pluralize(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function statusTone(status) {
  switch (status) {
    case "running":
      return "is-blue";
    case "succeeded":
    case "completed":
      return "is-accent";
    case "failed":
    case "cancelled":
    case "orphaned":
      return "is-danger";
    case "stopping":
      return "is-warn";
    default:
      return "";
  }
}

function chip(label, value, tone = "") {
  const css = ["chip", tone].filter(Boolean).join(" ");
  return `<span class="${css}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></span>`;
}

function metricsCard(label, value) {
  return `
    <div class="metric-card">
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-value">${escapeHtml(value)}</div>
    </div>
  `;
}

function emptyState(message) {
  return `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function codeBlock(content) {
  return `<pre class="code-block">${escapeHtml(content)}</pre>`;
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function fetchArtifact(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return { contentType, data: await response.json() };
  }
  return { contentType, text: await response.text() };
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

function qs(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, value);
  }
  return search.toString();
}

async function loadBootstrap() {
  state.bootstrap = await fetchJson("/api/bootstrap");
  state.analysis = state.bootstrap.runtime;
}

async function refreshAnalysis() {
  state.analysis = await fetchJson("/api/analysis");
}

async function refreshRuns() {
  const payload = await fetchJson("/api/runs");
  state.runs = Array.isArray(payload.runs) ? payload.runs : [];
  if (state.selectedRun && !state.runs.some((run) => run.rel_run_dir === state.selectedRun)) {
    state.selectedRun = null;
    state.runDetail = null;
    state.selectedTheorem = null;
    state.theoremDetail = null;
  }
}

async function refreshContrasts() {
  const payload = await fetchJson("/api/contrasts");
  state.contrasts = Array.isArray(payload.contrasts) ? payload.contrasts : [];
  if (state.selectedContrast && !state.contrasts.some((item) => item.rel_dir === state.selectedContrast)) {
    state.selectedContrast = null;
    state.contrastDetail = null;
    state.selectedContrastProvider = null;
    state.selectedContrastTheorem = null;
  }
}

async function refreshJobs() {
  const payload = await fetchJson("/api/jobs");
  state.jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
}

async function refreshSelectedRun() {
  if (!state.selectedRun) return;
  state.runDetail = await fetchJson(`/api/run?${qs({ run: state.selectedRun })}`);
}

async function refreshSelectedTheorem() {
  if (!state.selectedRun || !state.selectedTheorem) return;
  state.theoremDetail = await fetchJson(
    `/api/theorem?${qs({ run: state.selectedRun, theorem: state.selectedTheorem })}`,
  );
  ensureVariantSelection();
}

async function refreshSelectedContrast() {
  if (!state.selectedContrast) return;
  state.contrastDetail = await fetchJson(`/api/contrast?${qs({ contrast: state.selectedContrast })}`);
  ensureContrastSelection();
}

function contrastTheoremRows() {
  const rows = state.contrastDetail?.theorem_pairs || [];
  if (!state.selectedContrastProvider) return rows;
  return rows.filter((row) => row.provider === state.selectedContrastProvider);
}

function selectedContrastTheoremRow() {
  return contrastTheoremRows().find((row) => row.theorem === state.selectedContrastTheorem) || null;
}

function ensureContrastSelection() {
  const providerRows = state.contrastDetail?.providers || [];
  if (!providerRows.length) {
    state.selectedContrastProvider = null;
    state.selectedContrastTheorem = null;
    state.contrastVariant = "wild_type";
    return;
  }
  const providerNames = providerRows.map((row) => row.provider).filter(Boolean);
  if (!state.selectedContrastProvider || !providerNames.includes(state.selectedContrastProvider)) {
    state.selectedContrastProvider = providerNames[0] || null;
  }
  const theoremRows = contrastTheoremRows();
  if (!theoremRows.length) {
    state.selectedContrastTheorem = null;
    state.contrastVariant = "wild_type";
    return;
  }
  if (!state.selectedContrastTheorem || !theoremRows.some((row) => row.theorem === state.selectedContrastTheorem)) {
    state.selectedContrastTheorem = theoremRows[0].theorem;
  }
  const selected = selectedContrastTheoremRow();
  const variants = selected?.common_variants || [];
  if (!variants.includes(state.contrastVariant)) {
    state.contrastVariant = variants.includes("wild_type") ? "wild_type" : variants[0] || "wild_type";
  }
}

function ensureVariantSelection() {
  const variants = state.theoremDetail?.index?.variants || [];
  if (!variants.length) {
    state.leftVariant = "wild_type";
    state.rightVariant = null;
    state.artifactKind = null;
    return;
  }
  if (!variants.includes(state.leftVariant)) {
    state.leftVariant = variants.includes("wild_type") ? "wild_type" : variants[0];
  }
  if (state.rightVariant && !variants.includes(state.rightVariant)) {
    state.rightVariant = null;
  }
  if (state.rightVariant === state.leftVariant) {
    state.rightVariant = variants.find((variant) => variant !== state.leftVariant) || null;
  }
  if (state.rightVariant === null) {
    state.rightVariant = variants.find((variant) => variant !== state.leftVariant) || null;
  }
  const kinds = availableArtifactKinds();
  if (!kinds.length) {
    state.artifactKind = null;
  } else if (!kinds.includes(state.artifactKind)) {
    state.artifactKind = kinds.includes("comparison")
      ? "comparison"
      : kinds.includes("graph")
        ? "graph"
        : kinds[0];
  }
}

function availableArtifactKinds() {
  const variantFiles = state.theoremDetail?.index?.variant_files || {};
  const left = variantFiles[state.leftVariant] || {};
  const right = state.rightVariant ? variantFiles[state.rightVariant] || {} : {};
  const kinds = new Set([...Object.keys(left), ...Object.keys(right)]);
  return Array.from(kinds);
}

function artifactCacheKeyFor(run, theorem, filename) {
  return `${run}::${theorem || ""}::${filename}`;
}

function ensureArtifactLoadedFor(run, theorem, filename) {
  if (!filename || !run) return null;
  const key = artifactCacheKeyFor(run, theorem, filename);
  if (state.artifactCache.has(key)) {
    return state.artifactCache.get(key);
  }
  state.artifactCache.set(key, { loading: true });
  fetchArtifact(`/api/file?${qs({ run, theorem, file: filename })}`)
    .then((payload) => {
      state.artifactCache.set(key, { loading: false, ...payload });
      renderDynamic();
    })
    .catch((error) => {
      state.artifactCache.set(key, { loading: false, error: error.message });
      renderDynamic();
    });
  return { loading: true };
}

function ensureArtifactLoaded(filename) {
  if (!filename || !state.selectedRun || !state.selectedTheorem) return null;
  return ensureArtifactLoadedFor(state.selectedRun, state.selectedTheorem, filename);
}

async function selectRun(relRunDir, { changeView = true } = {}) {
  state.selectedRun = relRunDir;
  state.selectedTheorem = null;
  state.theoremDetail = null;
  state.artifactKind = null;
  await refreshSelectedRun();
  if (changeView) {
    state.view = "runs";
  }
  renderDynamic();
}

async function selectContrast(relDir, { changeView = true } = {}) {
  state.selectedContrast = relDir;
  state.selectedContrastTheorem = null;
  state.contrastDetail = null;
  await refreshSelectedContrast();
  if (changeView) {
    state.view = "contrasts";
  }
  renderDynamic();
}

function selectContrastTheorem(theoremName) {
  state.selectedContrastTheorem = theoremName;
  ensureContrastSelection();
  renderDynamic();
}

async function selectTheorem(theoremName) {
  state.selectedTheorem = theoremName;
  state.artifactKind = null;
  await refreshSelectedTheorem();
  renderDynamic();
}

function setupThemeControls() {
  const themeSelect = document.getElementById("theme-select");
  const densitySelect = document.getElementById("density-select");
  themeSelect.value = document.documentElement.dataset.theme || "academic-light";
  densitySelect.value = document.documentElement.dataset.density || "compact";
  themeSelect.addEventListener("change", () => {
    document.documentElement.dataset.theme = themeSelect.value;
    window.localStorage.setItem("wonton-lab-theme", themeSelect.value);
  });
  densitySelect.addEventListener("change", () => {
    document.documentElement.dataset.density = densitySelect.value;
    window.localStorage.setItem("wonton-lab-density", densitySelect.value);
  });
}

function bindGlobalHandlers() {
  document.addEventListener("click", async (event) => {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    const action = target.dataset.action;
    if (action === "select-view") {
      state.view = target.dataset.view || "dashboard";
      renderDynamic();
      return;
    }
    if (action === "select-run") {
      await selectRun(target.dataset.run);
      return;
    }
    if (action === "select-contrast") {
      await selectContrast(target.dataset.contrast);
      return;
    }
    if (action === "select-contrast-theorem") {
      selectContrastTheorem(target.dataset.theorem);
      return;
    }
    if (action === "select-theorem") {
      await selectTheorem(target.dataset.theorem);
      return;
    }
    if (action === "cancel-job") {
      try {
        await postJson(`/api/jobs/${target.dataset.job}/cancel`, {});
        await refreshJobs();
        renderDynamic();
      } catch (error) {
        flash(`cancel failed: ${error.message}`);
      }
      return;
    }
    if (action === "artifact-kind") {
      state.artifactKind = target.dataset.kind || null;
      renderDynamic();
      return;
    }
    if (action === "open-file") {
      openFileDialog({
        run: target.dataset.run,
        theorem: target.dataset.theorem || null,
        filename: target.dataset.file,
      });
      return;
    }
    if (action === "show-selected-run") {
      if (state.selectedRun) {
        state.view = "runs";
        renderDynamic();
      }
    }
  });

  document.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) return;
    if (target.dataset.control === "left-variant") {
      state.leftVariant = target.value;
      ensureVariantSelection();
      renderDynamic();
      return;
    }
    if (target.dataset.control === "right-variant") {
      state.rightVariant = target.value || null;
      ensureVariantSelection();
      renderDynamic();
      return;
    }
    if (target.dataset.control === "contrast-provider") {
      state.selectedContrastProvider = target.value || null;
      state.selectedContrastTheorem = null;
      ensureContrastSelection();
      renderDynamic();
      return;
    }
    if (target.dataset.control === "contrast-variant") {
      state.contrastVariant = target.value || "wild_type";
      renderDynamic();
    }
  });

  document.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement)) return;
    if (target.dataset.control === "run-filter") {
      state.runFilter = target.value;
      renderDynamic();
    }
  });

  document.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.dataset.launcher) return;
    event.preventDefault();
    const payload = serializeLauncherForm(form);
    payload.kind = form.dataset.launcher;
    if (payload.kind === "postprocess" && !payload.run_dir && state.selectedRun) {
      payload.run_dir = state.selectedRun;
    }
    try {
      const job = await postJson("/api/jobs/launch", payload);
      flash(`launched ${job.label}`);
      await refreshJobs();
      await refreshAnalysis();
      if (payload.kind === "analysis_export") {
        state.view = "notebook";
      }
      renderDynamic();
    } catch (error) {
      flash(`launch failed: ${error.message}`);
    }
  });
}

function serializeLauncherForm(form) {
  const payload = {};
  const elements = Array.from(form.querySelectorAll("[name]"));
  for (const element of elements) {
    if (element instanceof HTMLInputElement && element.type === "checkbox") {
      payload[element.name] = element.checked;
    } else if (element instanceof HTMLInputElement || element instanceof HTMLSelectElement) {
      payload[element.name] = element.value;
    }
  }
  return payload;
}

function flash(message) {
  state.flash = { message, at: Date.now() };
  renderStatusStrip();
  window.setTimeout(() => {
    if (state.flash && Date.now() - state.flash.at > 4000) {
      state.flash = null;
      renderStatusStrip();
    }
  }, 4300);
}

function renderLaunchers() {
  const root = document.getElementById("launchers");
  const specs = state.bootstrap?.launchers || [];
  root.innerHTML = specs
    .map((launcher) => {
      const fields = (launcher.fields || [])
        .map((field) => renderLauncherField(launcher.id, field))
        .join("");
      return `
        <form class="launcher-card" data-launcher="${escapeHtml(launcher.id)}">
          <div class="launcher-title">
            <strong>${escapeHtml(launcher.label)}</strong>
          </div>
          <div class="launcher-description">${escapeHtml(launcher.description || "")}</div>
          <div class="form-grid">${fields}</div>
          <div class="form-actions">
            <button class="primary-button" type="submit">Launch</button>
          </div>
        </form>
      `;
    })
    .join("");
}

function renderLauncherField(launcherId, field) {
  const name = escapeHtml(field.id);
  const label = escapeHtml(field.label);
  const defaultValue = field.default ?? "";
  if (field.type === "boolean") {
    return `
      <div class="field">
        <label>${label}</label>
        <label class="checkbox-row">
          <input type="checkbox" name="${name}" ${defaultValue ? "checked" : ""} />
          <span>${label}</span>
        </label>
      </div>
    `;
  }
  if (field.type === "select") {
    const options = (field.options || [])
      .map(
        (option) => `
          <option value="${escapeHtml(option.value)}" ${option.value === defaultValue ? "selected" : ""}>
            ${escapeHtml(option.label)}
          </option>
        `,
      )
      .join("");
    return `
      <div class="field">
        <label for="${launcherId}-${name}">${label}</label>
        <select id="${launcherId}-${name}" name="${name}">${options}</select>
      </div>
    `;
  }
  const inputType = field.type === "number" ? "number" : "text";
  return `
    <div class="field">
      <label for="${launcherId}-${name}">${label}</label>
      <input id="${launcherId}-${name}" type="${inputType}" name="${name}" value="${escapeHtml(defaultValue)}" />
    </div>
  `;
}

function renderStatusStrip() {
  const root = document.getElementById("status-strip");
  const runtime = state.analysis || state.bootstrap?.runtime;
  const chips = [];
  if (runtime) {
    chips.push(chip("Logs", runtime.logs_dir, ""));
    chips.push(chip("Lake DB", runtime.lake?.db_exists ? "ready" : "missing", runtime.lake?.db_exists ? "is-accent" : "is-warn"));
    chips.push(chip("Indexed runs", String(runtime.lake?.runs_indexed ?? "n/a"), "is-blue"));
  }
  const runningJobs = state.jobs.filter((job) => job.status === "running" || job.status === "stopping").length;
  chips.push(chip("Active jobs", String(runningJobs), runningJobs ? "is-blue" : ""));
  if (state.selectedRun) {
    chips.push(
      `<button class="status-chip is-accent" data-action="show-selected-run">Selected run <strong>${escapeHtml(state.selectedRun)}</strong></button>`,
    );
  }
  if (state.flash) {
    chips.push(`<span class="status-chip is-accent">${escapeHtml(state.flash.message)}</span>`);
  }
  root.innerHTML = chips.join("");
}

function renderJobsPanel() {
  const root = document.getElementById("jobs-panel");
  if (!state.jobs.length) {
    root.innerHTML = emptyState("No UI-launched jobs yet.");
    return;
  }
  root.innerHTML = `
    <div class="jobs-list">
      ${state.jobs
        .slice(0, 12)
        .map((job) => {
          const tail = Array.isArray(job.recent_lines) ? job.recent_lines.slice(-10).join("\n") : "";
          return `
            <div class="job-card ${statusTone(job.status)}">
              <div class="job-head">
                <div class="job-label">${escapeHtml(job.label)}</div>
                ${chip("status", job.status, statusTone(job.status))}
              </div>
              <div class="job-meta">
                ${chip("started", formatDate(job.started_at || job.created_at))}
                ${job.run_dir ? `<button class="chip is-accent" data-action="select-run" data-run="${escapeHtml(job.run_dir)}">run ${escapeHtml(job.run_dir)}</button>` : ""}
                ${job.output_path ? chip("output", job.output_path) : ""}
                ${typeof job.exit_code === "number" ? chip("exit", String(job.exit_code), job.exit_code === 0 ? "is-accent" : "is-danger") : ""}
              </div>
              ${tail ? `<pre class="job-log">${escapeHtml(tail)}</pre>` : ""}
              <div class="form-actions">
                ${job.status === "running" || job.status === "stopping" ? `<button class="secondary-button" type="button" data-action="cancel-job" data-job="${escapeHtml(job.id)}">Cancel</button>` : ""}
              </div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function recentRuns(limit = 10) {
  return state.runs.slice(0, limit);
}

function renderDashboardView() {
  const runtime = state.analysis || state.bootstrap?.runtime;
  const selected = state.runDetail;
  return `
    <div class="workspace-grid">
      <section class="panel">
        <div class="panel-head">
          <h2>Runtime</h2>
          <div class="panel-subtitle">local dossier state</div>
        </div>
        <div class="metric-grid">
          ${metricsCard("Lake indexed runs", String(runtime?.lake?.runs_indexed ?? "n/a"))}
          ${metricsCard("Recent outputs", String(runtime?.lake?.recent_job_outputs?.length ?? 0))}
          ${metricsCard("Notebook", runtime?.notebook ? "ready" : "missing")}
          ${metricsCard("Active jobs", String(state.jobs.filter((job) => job.status === "running").length))}
        </div>
        <div class="chip-row">
          ${chip("logs", runtime?.logs_dir || "n/a")}
          ${chip("db", runtime?.lake?.db_path || "n/a")}
          ${chip("presets", String((runtime?.presets || []).length))}
        </div>
      </section>
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-head">
            <h2>Selected Run Snapshot</h2>
            <div class="panel-subtitle">current inspection target</div>
          </div>
          ${selected ? renderRunSnapshot(selected) : emptyState("Select a run to inspect it here.")}
        </section>
        <section class="panel">
          <div class="panel-head">
            <h2>Recent Runs</h2>
            <div class="panel-subtitle">filesystem discovery from logs root</div>
          </div>
          ${renderRunsTable(recentRuns(12))}
        </section>
      </div>
    </div>
  `;
}

function renderRunSnapshot(run) {
  const dashboard = run.dashboard;
  const behavior = run.behavior_breakdown;
  const progress = run.run_status?.progress || {};
  const progressBits = [
    progress.current_theorem || progress.theorem_name,
    progress.phase,
    progress.current_intervention,
  ].filter(Boolean);
  return `
    <div class="section-stack">
      <div class="metric-grid">
        ${metricsCard("Status", String(run.run_status?.status || "unknown"))}
        ${metricsCard("Wild solve rate", formatPercent(dashboard?.wild_type_solve_rate))}
        ${metricsCard("Intervention solve rate", formatPercent(dashboard?.intervention_solve_rate))}
        ${metricsCard("Interventions", String(dashboard?.intervention_count ?? 0))}
        ${behavior ? metricsCard("Rescues", `${behavior.counts.rescued} / ${behavior.counts.total}`) : ""}
      </div>
      ${progressBits.length ? `<div class="chip-row">${progressBits.map((item) => chip("live", item, "is-blue")).join("")}</div>` : ""}
      <div class="form-actions">
        <button class="primary-button" type="button" data-action="select-view" data-view="runs">Open Run View</button>
      </div>
    </div>
  `;
}

function renderRunsTable(runs) {
  if (!runs.length) {
    return emptyState("No runs found.");
  }
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Run</th>
            <th>Status</th>
            <th>Theorems</th>
            <th>Wild</th>
            <th>Interventions</th>
          </tr>
        </thead>
        <tbody>
          ${runs
            .map(
              (run) => `
                <tr data-action="select-run" data-run="${escapeHtml(run.rel_run_dir)}" class="${run.rel_run_dir === state.selectedRun ? "row-selected" : ""}">
                  <td>
                    <div class="run-title">${escapeHtml(run.run_id || run.rel_run_dir)}</div>
                    <div class="run-subtitle">${escapeHtml(run.rel_run_dir)}</div>
                  </td>
                  <td>${chip("status", run.status || "unknown", statusTone(run.status))}</td>
                  <td>${escapeHtml(String(run.theorem_count ?? "n/a"))}</td>
                  <td>${escapeHtml(formatPercent(run.wild_type_solve_rate))}</td>
                  <td>${escapeHtml(formatPercent(run.intervention_solve_rate))}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function filteredRuns() {
  const term = state.runFilter.trim().toLowerCase();
  if (!term) return state.runs;
  return state.runs.filter((run) => {
    const haystacks = [run.rel_run_dir, run.run_id, run.provider, run.mode, run.corpus];
    return haystacks.some((value) => value && String(value).toLowerCase().includes(term));
  });
}

function renderRunsView() {
  const runs = filteredRuns();
  return `
    <div class="run-layout">
      <section class="panel list-panel">
        <div class="panel-head">
          <h2>Runs</h2>
          <div class="panel-subtitle">${pluralize(state.runs.length, "run")}</div>
        </div>
        <div class="field">
          <label for="run-filter">Filter</label>
          <input id="run-filter" data-control="run-filter" type="text" value="${escapeHtml(state.runFilter)}" />
        </div>
        <div class="section-stack">
          ${runs.length
            ? runs
                .map((run) => {
                  const selected = run.rel_run_dir === state.selectedRun;
                  return `
                    <button class="run-item ${selected ? "is-selected" : ""}" data-action="select-run" data-run="${escapeHtml(run.rel_run_dir)}">
                      <div class="run-title">${escapeHtml(run.run_id || run.rel_run_dir)}</div>
                      <div class="run-subtitle">${escapeHtml(run.rel_run_dir)}</div>
                      <div class="run-quick">
                        ${chip("status", run.status || "unknown", statusTone(run.status))}
                        ${chip("theorems", String(run.theorem_count ?? "n/a"))}
                        ${run.provider ? chip("provider", run.provider) : ""}
                      </div>
                    </button>
                  `;
                })
                .join("")
            : emptyState("No runs match the current filter.")}
        </div>
      </section>
      <section class="workspace-grid">
        ${state.runDetail ? renderRunDetail(state.runDetail) : `<section class="panel">${emptyState("Select a run from the left column.")}</section>`}
        ${state.theoremDetail ? renderTheoremDetail() : ""}
      </section>
    </div>
  `;
}

function renderRunDetail(run) {
  const dashboard = run.dashboard;
  const behavior = run.behavior_breakdown;
  const progress = run.run_status?.progress || {};
  const rescueRows = dashboard?.rescue_matrix?.rows || [];
  const rescueMatrix = dashboard?.rescue_matrix?.matrix || [];
  const rescueBars = rescueRows
    .map((name, index) => ({
      name,
      rescueRate: rescueMatrix[index]?.[0] || 0,
      wildRate: rescueMatrix[index]?.[1] || 0,
    }))
    .sort((a, b) => b.rescueRate - a.rescueRate)
    .slice(0, 12);
  const interestingProgress = [
    ["Current theorem", progress.current_theorem || progress.theorem_name],
    ["Phase", progress.phase],
    ["Current intervention", progress.current_intervention],
    ["Tier", progress.current_tier || progress.tier],
    [
      "Completed",
      progress.completed_theorems && progress.total_theorems
        ? `${progress.completed_theorems}/${progress.total_theorems}`
        : null,
    ],
    ["Nodes", progress.node_count || progress.nodes],
    ["Leaves", progress.leaf_count || progress.leaves],
    ["Depth", progress.max_depth || progress.depth],
    ["Restarts", progress.restart_count || progress.restarts],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");

  return `
    <section class="panel">
      <div class="panel-head">
        <h2>${escapeHtml(run.rel_run_dir)}</h2>
        <div class="panel-subtitle">${escapeHtml(run.run_dir)}</div>
      </div>
      <div class="metric-grid">
        ${metricsCard("Status", String(run.run_status?.status || "unknown"))}
        ${metricsCard("Theorems", String(dashboard?.theorem_count ?? run.theorem_names?.length ?? 0))}
        ${metricsCard("Wild solve rate", formatPercent(dashboard?.wild_type_solve_rate))}
        ${metricsCard("Intervention solve rate", formatPercent(dashboard?.intervention_solve_rate))}
        ${metricsCard("Interventions", String(dashboard?.intervention_count ?? 0))}
        ${metricsCard("Crashed", String(dashboard?.crashed_count ?? 0))}
      </div>
      ${
        interestingProgress.length
          ? `
            <div class="panel-head">
              <h2>Live Progress</h2>
              <div class="panel-subtitle">run_status.json</div>
            </div>
            <div class="metric-grid">
              ${interestingProgress.map(([label, value]) => metricsCard(label, String(value))).join("")}
            </div>
          `
          : ""
      }
      ${
        behavior
          ? `
            <div class="panel-head">
              <h2>Behavior Fractions</h2>
              <div class="panel-subtitle">derived from theorem intervention outcomes</div>
            </div>
            <div class="metric-grid">
              ${metricsCard("Rescued", `${behavior.counts.rescued} (${formatPercent(behavior.rates.rescued)})`)}
              ${metricsCard("Preserved", `${behavior.counts.preserved} (${formatPercent(behavior.rates.preserved)})`)}
              ${metricsCard("Degraded", `${behavior.counts.degraded} (${formatPercent(behavior.rates.degraded)})`)}
              ${metricsCard("Inert", `${behavior.counts.inert} (${formatPercent(behavior.rates.inert)})`)}
            </div>
          `
          : ""
      }
      ${
        rescueBars.length
          ? `
            <div class="panel-head">
              <h2>Rescue Matrix</h2>
              <div class="panel-subtitle">highest rescue-rate interventions</div>
            </div>
            <div class="bar-list">
              ${rescueBars
                .map(
                  (row) => `
                    <div class="bar-row">
                      <span>${escapeHtml(row.name)}</span>
                      <span class="bar-track"><span class="bar-fill" style="width:${Math.max(2, row.rescueRate * 100)}%"></span></span>
                      <span class="mono">${formatPercent(row.rescueRate)}</span>
                    </div>
                  `,
                )
                .join("")}
            </div>
          `
          : ""
      }
      ${
        run.provider_deep_dive?.providers?.length
          ? `
            <div class="panel-head">
              <h2>Provider Deep Dive</h2>
              <div class="panel-subtitle">run-backed provider summaries</div>
            </div>
            ${renderProviderDeepDive(run.provider_deep_dive)}
          `
          : ""
      }
      <div class="panel-head">
        <h2>Theorems</h2>
        <div class="panel-subtitle">click a theorem to inspect variants and artifacts</div>
      </div>
      ${renderTheoremRows(run.theorem_rows || [])}
      <div class="panel-head">
        <h2>Run Files</h2>
        <div class="panel-subtitle">top-level artifacts and logs</div>
      </div>
      <div class="chip-row">
        ${(run.root_files || [])
          .map(
            (file) => `
              <button class="pill-button" data-action="open-file" data-run="${escapeHtml(run.rel_run_dir)}" data-file="${escapeHtml(file.name)}">
                ${escapeHtml(file.name)}
              </button>
            `,
          )
          .join("") || emptyState("No top-level files available.")}
      </div>
    </section>
  `;
}

function renderProviderDeepDive(payload) {
  const rows = payload.providers || [];
  if (!rows.length) return emptyState("No provider summary available.");
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Provider</th>
            <th>Solve rate</th>
            <th>Theorems</th>
            <th>Interventions</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr>
                  <td>${escapeHtml(row.provider || row.name || "provider")}</td>
                  <td>${escapeHtml(formatPercent(row.solve_rate))}</td>
                  <td>${escapeHtml(String(row.theorem_count ?? "n/a"))}</td>
                  <td>${escapeHtml(String(row.intervention_count ?? "n/a"))}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderTheoremRows(rows) {
  if (!rows.length) {
    return emptyState("No theorem summaries available yet.");
  }
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Theorem</th>
            <th>Wild</th>
            <th>Iterations</th>
            <th>Interventions</th>
            <th>Rescued</th>
            <th>Degraded</th>
            <th>Mean GED</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr data-action="select-theorem" data-theorem="${escapeHtml(row.name)}" class="${row.name === state.selectedTheorem ? "row-selected" : ""}">
                  <td>${escapeHtml(row.name)}</td>
                  <td>${row.wild_solved ? chip("wild", "solved", "is-accent") : chip("wild", "failed", "is-danger")}</td>
                  <td>${escapeHtml(String(row.iterations ?? "n/a"))}</td>
                  <td>${escapeHtml(String(row.intervention_count ?? 0))}</td>
                  <td>${escapeHtml(String(row.rescued_count ?? 0))}</td>
                  <td>${escapeHtml(String(row.degraded_count ?? 0))}</td>
                  <td>${escapeHtml(formatNumber(row.mean_ged))}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderTheoremDetail() {
  const detail = state.theoremDetail;
  const variants = detail.index?.variants || [];
  const leftSummary = detail.variant_summaries?.[state.leftVariant] || {};
  const rightSummary = state.rightVariant ? detail.variant_summaries?.[state.rightVariant] || {} : null;
  const kinds = availableArtifactKinds();
  return `
    <section class="panel">
      <div class="panel-head">
        <h2>Theorem: ${escapeHtml(detail.theorem)}</h2>
        <div class="panel-subtitle">${escapeHtml(state.selectedRun || "")}</div>
      </div>
      ${renderTheoremSummary(detail.summary)}
      <div class="artifact-toolbar">
        <div class="artifact-controls">
          <div class="field">
            <label for="left-variant">Left variant</label>
            <select id="left-variant" data-control="left-variant">
              ${variants
                .map(
                  (variant) => `
                    <option value="${escapeHtml(variant)}" ${variant === state.leftVariant ? "selected" : ""}>
                      ${escapeHtml(variant)}
                    </option>
                  `,
                )
                .join("")}
            </select>
          </div>
          <div class="field">
            <label for="right-variant">Right variant</label>
            <select id="right-variant" data-control="right-variant">
              <option value="">none</option>
              ${variants
                .map(
                  (variant) => `
                    <option value="${escapeHtml(variant)}" ${variant === state.rightVariant ? "selected" : ""}>
                      ${escapeHtml(variant)}
                    </option>
                  `,
                )
                .join("")}
            </select>
          </div>
        </div>
        <div class="chip-row">
          ${kinds
            .map(
              (kind) => `
                <button class="pill-button ${kind === state.artifactKind ? "is-active" : ""}" data-action="artifact-kind" data-kind="${escapeHtml(kind)}">
                  ${escapeHtml(kind)}
                </button>
              `,
            )
            .join("")}
        </div>
      </div>
      <div class="compare-grid">
        <div class="subpanel">
          <div class="panel-head">
            <h2>${escapeHtml(state.leftVariant)}</h2>
            <div class="panel-subtitle">variant summary</div>
          </div>
          ${renderVariantSummary(leftSummary)}
        </div>
        ${
          state.rightVariant
            ? `
              <div class="subpanel">
                <div class="panel-head">
                  <h2>${escapeHtml(state.rightVariant)}</h2>
                  <div class="panel-subtitle">variant summary</div>
                </div>
                ${renderVariantSummary(rightSummary)}
              </div>
            `
            : ""
        }
      </div>
      <div class="subpanel">
        <div class="panel-head">
          <h2>Artifact View</h2>
          <div class="panel-subtitle">${escapeHtml(state.artifactKind || "none")}</div>
        </div>
        ${renderArtifactView()}
      </div>
    </section>
  `;
}

function renderTheoremSummary(summary) {
  if (!summary) return emptyState("No theorem summary found in summary.json.gz.");
  const interventions = Array.isArray(summary.interventions) ? summary.interventions : [];
  return `
    <div class="metric-grid">
      ${metricsCard("Wild solved", summary.wild_type?.solved ? "yes" : "no")}
      ${metricsCard("Wild iterations", String(summary.wild_type?.iterations ?? "n/a"))}
      ${metricsCard("Interventions", String(interventions.length))}
      ${metricsCard("Rescues", String(interventions.filter((item) => item.solved && !item.baseline_solved).length))}
    </div>
  `;
}

function renderVariantSummary(summary) {
  if (!summary || !Object.keys(summary).length) {
    return emptyState("No variant files found.");
  }
  const cards = [];
  const metrics = summary.metrics || {};
  const graph = summary.graph || {};
  const tree = summary.mcts_tree || {};
  const history = summary.history || {};
  if (metrics.total_iterations !== undefined) cards.push(metricsCard("Iterations", String(metrics.total_iterations)));
  if (metrics.total_attempts !== undefined) cards.push(metricsCard("Attempts", String(metrics.total_attempts)));
  if (metrics.max_depth_reached !== undefined) cards.push(metricsCard("Max depth", String(metrics.max_depth_reached)));
  if (graph.node_count !== undefined) cards.push(metricsCard("Graph nodes", String(graph.node_count)));
  if (graph.edge_count !== undefined) cards.push(metricsCard("Graph edges", String(graph.edge_count)));
  if (tree.node_count !== undefined) cards.push(metricsCard("Tree nodes", String(tree.node_count)));
  if (history.solution_steps !== undefined && history.solution_steps !== null) {
    cards.push(metricsCard("Solution steps", String(history.solution_steps)));
  }
  const topTactics = graph.top_tactics || history.top_tactics || [];
  return `
    <div class="section-stack">
      <div class="metric-grid">${cards.join("") || metricsCard("Files", "present")}</div>
      ${
        topTactics.length
          ? `
            <div class="bar-list">
              ${topTactics
                .slice(0, 6)
                .map(
                  (item) => `
                    <div class="bar-row">
                      <span>${escapeHtml(item.tactic)}</span>
                      <span class="bar-track"><span class="bar-fill" style="width:${Math.max(8, item.count * 12)}%"></span></span>
                      <span class="mono">${escapeHtml(String(item.count))}</span>
                    </div>
                  `,
                )
                .join("")}
            </div>
          `
          : ""
      }
    </div>
  `;
}

function variantFilename(variant, kind) {
  if (!variant || !kind) return null;
  const files = state.theoremDetail?.index?.variant_files?.[variant] || {};
  return files[kind] || null;
}

function renderArtifactView() {
  const kind = state.artifactKind;
  if (!kind) return emptyState("No artifact kind available.");
  if (kind === "graph") {
    return renderGraphCompare();
  }
  if (kind === "comparison") {
    return renderComparisonView();
  }
  return renderRawArtifactCompare(kind);
}

function renderComparisonView() {
  if (!state.rightVariant) {
    return emptyState("Comparison files exist on intervention variants. Select a right variant.");
  }
  const filename = variantFilename(state.rightVariant, "comparison");
  if (!filename) {
    return emptyState("No comparison file for the selected right variant.");
  }
  const artifact = ensureArtifactLoaded(filename);
  if (!artifact || artifact.loading) {
    return emptyState("Loading comparison artifact...");
  }
  if (artifact.error) {
    return emptyState(artifact.error);
  }
  const data = artifact.data || {};
  const proofTermDiff = data.proof_term_diff || {};
  return `
    <div class="section-stack">
      <div class="metric-grid">
        ${metricsCard("GED", formatNumber(data.ged))}
        ${metricsCard("Hash mismatch", data.hash_mismatch ? "yes" : "no")}
        ${metricsCard("Divergence depth", String(proofTermDiff.divergence_depth ?? "n/a"))}
        ${metricsCard("Axiom delta", String((data.axiom_delta || []).length))}
      </div>
      ${(data.axiom_delta || []).length ? `<div class="chip-row">${data.axiom_delta.map((item) => chip("axiom", item, "is-warn")).join("")}</div>` : ""}
      ${proofTermDiff.divergence_path ? codeBlock(proofTermDiff.divergence_path) : ""}
      ${codeBlock(JSON.stringify(data, null, 2))}
    </div>
  `;
}

function renderRawArtifactCompare(kind) {
  const leftFile = variantFilename(state.leftVariant, kind);
  const rightFile = state.rightVariant ? variantFilename(state.rightVariant, kind) : null;
  if (!leftFile && !rightFile) {
    return emptyState(`No ${kind} files for the selected variants.`);
  }
  return `
    <div class="artifact-compare">
      <div class="subpanel">
        <div class="panel-head">
          <h2>${escapeHtml(state.leftVariant)}</h2>
          <div class="panel-subtitle">${escapeHtml(leftFile || "missing")}</div>
        </div>
        ${renderArtifactPayload(leftFile)}
      </div>
      ${
        state.rightVariant
          ? `
            <div class="subpanel">
              <div class="panel-head">
                <h2>${escapeHtml(state.rightVariant)}</h2>
                <div class="panel-subtitle">${escapeHtml(rightFile || "missing")}</div>
              </div>
              ${renderArtifactPayload(rightFile)}
            </div>
          `
          : ""
      }
    </div>
  `;
}

function renderArtifactPayload(filename) {
  if (!filename) return emptyState("Missing artifact.");
  const artifact = ensureArtifactLoaded(filename);
  if (!artifact || artifact.loading) return emptyState("Loading artifact...");
  if (artifact.error) return emptyState(artifact.error);
  if (artifact.data) return codeBlock(JSON.stringify(artifact.data, null, 2));
  return codeBlock(artifact.text || "");
}

function renderGraphCompare() {
  const leftFile = variantFilename(state.leftVariant, "graph");
  const rightFile = state.rightVariant ? variantFilename(state.rightVariant, "graph") : null;
  if (!leftFile && !rightFile) {
    return emptyState("No graph files for the selected variants.");
  }
  return `
    <div class="artifact-compare">
      <div class="subpanel">
        <div class="panel-head">
          <h2>${escapeHtml(state.leftVariant)}</h2>
          <div class="panel-subtitle">${escapeHtml(leftFile || "missing")}</div>
        </div>
        ${renderGraphPayload(leftFile)}
      </div>
      ${
        state.rightVariant
          ? `
            <div class="subpanel">
              <div class="panel-head">
                <h2>${escapeHtml(state.rightVariant)}</h2>
                <div class="panel-subtitle">${escapeHtml(rightFile || "missing")}</div>
              </div>
              ${renderGraphPayload(rightFile)}
            </div>
          `
          : ""
      }
    </div>
  `;
}

function renderGraphPayload(filename) {
  if (!filename) return emptyState("Missing graph artifact.");
  const artifact = ensureArtifactLoaded(filename);
  if (!artifact || artifact.loading) return emptyState("Loading graph...");
  if (artifact.error) return emptyState(artifact.error);
  const data = artifact.data;
  if (!data || !Array.isArray(data.nodes) || !Array.isArray(data.edges)) {
    return codeBlock(JSON.stringify(data, null, 2));
  }
  if (data.nodes.length > 120) {
    return `
      ${emptyState(`Graph has ${data.nodes.length} nodes; raw display only.`)}
      ${codeBlock(JSON.stringify(data, null, 2))}
    `;
  }
  return `<div class="graph-canvas">${graphSvg(data)}</div>`;
}

function graphSvg(graph) {
  const width = 640;
  const marginX = 54;
  const marginY = 36;
  const nodes = graph.nodes.filter((node) => typeof node === "object" && node !== null);
  const edges = graph.edges.filter((edge) => typeof edge === "object" && edge !== null);
  const depths = new Map();
  for (const node of nodes) {
    const depth = Number.isInteger(node.depth) ? node.depth : 0;
    if (!depths.has(depth)) depths.set(depth, []);
    depths.get(depth).push(node);
  }
  const sortedDepths = Array.from(depths.keys()).sort((a, b) => a - b);
  const depthIndex = new Map(sortedDepths.map((depth, index) => [depth, index]));
  const positions = new Map();
  const maxPerDepth = Math.max(...Array.from(depths.values()).map((bucket) => bucket.length), 1);
  const height = Math.max(220, marginY * 2 + maxPerDepth * 64);
  for (const [depth, bucket] of depths.entries()) {
    const x = marginX + (sortedDepths.length <= 1 ? 0 : (depthIndex.get(depth) * (width - marginX * 2)) / (sortedDepths.length - 1));
    bucket.forEach((node, index) => {
      const y = marginY + ((index + 1) * (height - marginY * 2)) / (bucket.length + 1);
      positions.set(node.id, { x, y, label: node.goal_sig || node.id });
    });
  }
  const edgeMarkup = edges
    .map((edge) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) return "";
      return `<line x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" stroke="rgba(37,99,235,0.35)" stroke-width="1.5" />`;
    })
    .join("");
  const nodeMarkup = nodes
    .map((node) => {
      const position = positions.get(node.id);
      if (!position) return "";
      const fill = node.is_terminal ? "rgba(15,118,110,0.82)" : "rgba(16,24,32,0.72)";
      const label = String(position.label).slice(0, 16);
      return `
        <g>
          <circle cx="${position.x}" cy="${position.y}" r="9" fill="${fill}" />
          <text x="${position.x}" y="${position.y - 14}" text-anchor="middle" font-size="11" fill="currentColor">${escapeHtml(label)}</text>
        </g>
      `;
    })
    .join("");
  return `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
      <rect x="0" y="0" width="${width}" height="${height}" fill="transparent" />
      ${edgeMarkup}
      ${nodeMarkup}
    </svg>
  `;
}

function formatDeltaPercent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)}%`;
}

function renderContrastsView() {
  return `
    <div class="run-layout">
      <section class="panel list-panel">
        <div class="panel-head">
          <h2>Paired Contrasts</h2>
          <div class="panel-subtitle">${pluralize(state.contrasts.length, "contrast")}</div>
        </div>
        ${
          state.contrasts.length
            ? state.contrasts
                .map((contrast) => {
                  const selected = contrast.rel_dir === state.selectedContrast;
                  return `
                    <button class="run-item ${selected ? "is-selected" : ""}" data-action="select-contrast" data-contrast="${escapeHtml(contrast.rel_dir)}">
                      <div class="run-title">${escapeHtml(contrast.run_id || contrast.rel_dir)}</div>
                      <div class="run-subtitle">${escapeHtml(contrast.rel_dir)}</div>
                      <div class="run-quick">
                        ${chip("providers", String(contrast.provider_count ?? 0))}
                        ${chip("pairs", String(contrast.theorem_pair_count ?? 0))}
                        ${contrast.corpus ? chip("corpus", contrast.corpus) : ""}
                      </div>
                    </button>
                  `;
                })
                .join("")
            : emptyState("No paired contrast summaries found. Launch Causal Contrast from the sidebar.")
        }
      </section>
      ${state.contrastDetail ? renderContrastDetail(state.contrastDetail) : `<section class="panel">${emptyState("Select a contrast from the left column.")}</section>`}
    </div>
  `;
}

function renderContrastDetail(detail) {
  const providerRows = detail.providers || [];
  const theoremRows = contrastTheoremRows();
  const selected = selectedContrastTheoremRow();
  return `
    <section class="panel">
      <div class="panel-head">
        <h2>${escapeHtml(detail.run_id || detail.rel_dir || "paired contrast")}</h2>
        <div class="panel-subtitle">${escapeHtml(detail.root_dir || "")}</div>
      </div>
      <div class="metric-grid">
        ${metricsCard("Providers", String(providerRows.length))}
        ${metricsCard("Theorem pairs", String((detail.theorem_pairs || []).length))}
        ${metricsCard("Corpus", String(detail.experiment?.corpus || "n/a"))}
        ${metricsCard("Budget", String(detail.experiment?.budget || "n/a"))}
      </div>
      ${renderProviderContrastTable(providerRows)}
      <div class="artifact-toolbar">
        <div class="artifact-controls">
          <div class="field">
            <label for="contrast-provider">Provider</label>
            <select id="contrast-provider" data-control="contrast-provider">
              ${providerRows
                .map(
                  (row) => `
                    <option value="${escapeHtml(row.provider)}" ${row.provider === state.selectedContrastProvider ? "selected" : ""}>
                      ${escapeHtml(row.provider)}
                    </option>
                  `,
                )
                .join("")}
            </select>
          </div>
          <div class="field">
            <label for="contrast-variant">Variant</label>
            <select id="contrast-variant" data-control="contrast-variant">
              ${(selected?.common_variants || ["wild_type"])
                .map(
                  (variant) => `
                    <option value="${escapeHtml(variant)}" ${variant === state.contrastVariant ? "selected" : ""}>
                      ${escapeHtml(variant)}
                    </option>
                  `,
                )
                .join("")}
            </select>
          </div>
        </div>
        <div class="chip-row">
          ${chip("central", detail.modes?.[state.selectedContrastProvider]?.centralized?.rel_run_dir || "n/a")}
          ${chip("distributed", detail.modes?.[state.selectedContrastProvider]?.distributed?.rel_run_dir || "n/a", "is-blue")}
        </div>
      </div>
      <div class="compare-grid">
        <div class="subpanel">
          <div class="panel-head">
            <h2>Theorem Pairs</h2>
            <div class="panel-subtitle">same theorem slice, provider, budget, corpus, lesion definitions</div>
          </div>
          ${renderContrastTheoremTable(theoremRows)}
        </div>
        <div class="subpanel">
          <div class="panel-head">
            <h2>Selected Pair</h2>
            <div class="panel-subtitle">${escapeHtml(selected?.theorem || "none")}</div>
          </div>
          ${selected ? renderContrastPairSummary(selected) : emptyState("Select a theorem pair.")}
        </div>
      </div>
      ${selected ? renderContrastGraphCompare(detail, selected) : ""}
    </section>
  `;
}

function renderProviderContrastTable(rows) {
  if (!rows.length) return emptyState("No provider metrics available.");
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Provider</th>
            <th>Central recovery</th>
            <th>Distributed recovery</th>
            <th>Delta</th>
            <th>Central reroute</th>
            <th>Distributed reroute</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr>
                  <td>${escapeHtml(row.provider)}</td>
                  <td>${escapeHtml(formatPercent(row.centralized?.recovery_rate))}</td>
                  <td>${escapeHtml(formatPercent(row.distributed?.recovery_rate))}</td>
                  <td>${escapeHtml(formatDeltaPercent(row.delta?.recovery_rate))}</td>
                  <td>${escapeHtml(formatPercent(row.centralized?.reroute_rate_among_recovered))}</td>
                  <td>${escapeHtml(formatPercent(row.distributed?.reroute_rate_among_recovered))}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderContrastTheoremTable(rows) {
  if (!rows.length) return emptyState("No theorem pairs for the selected provider.");
  return `
    <div class="table-wrap compact-table">
      <table>
        <thead>
          <tr>
            <th>Theorem</th>
            <th>Central</th>
            <th>Distributed</th>
            <th>Recovery delta</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr data-action="select-contrast-theorem" data-theorem="${escapeHtml(row.theorem)}" class="${row.theorem === state.selectedContrastTheorem ? "row-selected" : ""}">
                  <td>${escapeHtml(row.theorem)}</td>
                  <td>${row.centralized?.wild_solved ? chip("wild", "solved", "is-accent") : chip("wild", "failed", "is-danger")}</td>
                  <td>${row.distributed?.wild_solved ? chip("wild", "solved", "is-accent") : chip("wild", "failed", "is-danger")}</td>
                  <td>${escapeHtml(formatDeltaPercent(row.delta?.recovery_rate))}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderContrastPairSummary(row) {
  return `
    <div class="section-stack">
      <div class="metric-grid">
        ${metricsCard("Central recovery", formatPercent(row.centralized?.recovery_rate))}
        ${metricsCard("Distributed recovery", formatPercent(row.distributed?.recovery_rate))}
        ${metricsCard("Recovery delta", formatDeltaPercent(row.delta?.recovery_rate))}
        ${metricsCard("Common graph variants", String((row.common_variants || []).length))}
      </div>
      <div class="metric-grid">
        ${metricsCard("Central GED", formatNumber(row.centralized?.mean_ged))}
        ${metricsCard("Distributed GED", formatNumber(row.distributed?.mean_ged))}
        ${metricsCard("Central reroutes", String(row.centralized?.rerouted_interventions ?? 0))}
        ${metricsCard("Distributed reroutes", String(row.distributed?.rerouted_interventions ?? 0))}
      </div>
    </div>
  `;
}

function renderContrastGraphCompare(detail, row) {
  const providerModes = detail.modes?.[row.provider] || {};
  const centralRun = providerModes.centralized?.rel_run_dir;
  const distributedRun = providerModes.distributed?.rel_run_dir;
  const centralFile = row.centralized?.variants?.[state.contrastVariant] || null;
  const distributedFile = row.distributed?.variants?.[state.contrastVariant] || null;
  return `
    <div class="subpanel">
      <div class="panel-head">
        <h2>Proof Graph Contrast</h2>
        <div class="panel-subtitle">${escapeHtml(row.theorem)} / ${escapeHtml(state.contrastVariant)}</div>
      </div>
      <div class="artifact-compare">
        <div class="subpanel">
          <div class="panel-head">
            <h2>Centralized</h2>
            <div class="panel-subtitle">${escapeHtml(centralRun || "missing")}</div>
          </div>
          ${renderContrastGraphPayload(centralRun, row.theorem, centralFile)}
        </div>
        <div class="subpanel">
          <div class="panel-head">
            <h2>Distributed</h2>
            <div class="panel-subtitle">${escapeHtml(distributedRun || "missing")}</div>
          </div>
          ${renderContrastGraphPayload(distributedRun, row.theorem, distributedFile)}
        </div>
      </div>
    </div>
  `;
}

function renderContrastGraphPayload(run, theorem, filename) {
  if (!run || !filename) return emptyState("Missing graph artifact.");
  const artifact = ensureArtifactLoadedFor(run, theorem, filename);
  if (!artifact || artifact.loading) return emptyState("Loading graph...");
  if (artifact.error) return emptyState(artifact.error);
  const data = artifact.data;
  if (!data || !Array.isArray(data.nodes) || !Array.isArray(data.edges)) {
    return codeBlock(JSON.stringify(data, null, 2));
  }
  if (data.nodes.length > 120) {
    return `
      ${emptyState(`Graph has ${data.nodes.length} nodes; raw display only.`)}
      ${codeBlock(JSON.stringify(data, null, 2))}
    `;
  }
  return `<div class="graph-canvas">${graphSvg(data)}</div>`;
}

function renderAnalysisView() {
  const runtime = state.analysis;
  const presets = runtime?.presets || [];
  return `
    <div class="workspace-grid">
      <section class="panel">
        <div class="panel-head">
          <h2>Lake Runtime</h2>
          <div class="panel-subtitle">indexed state and output roots</div>
        </div>
        <div class="metric-grid">
          ${metricsCard("Indexed runs", String(runtime?.lake?.runs_indexed ?? "n/a"))}
          ${metricsCard("DB", runtime?.lake?.db_exists ? "ready" : "missing")}
          ${metricsCard("Preset count", String(presets.length))}
          ${metricsCard("Notebook", runtime?.notebook ? "ready" : "missing")}
        </div>
        <div class="chip-row">
          ${chip("db", runtime?.lake?.db_path || "n/a")}
          ${chip("jobs", runtime?.lake?.jobs_dir || "n/a")}
          ${chip("exports", runtime?.lake?.exports_dir || "n/a")}
        </div>
      </section>
      <section class="panel">
        <div class="panel-head">
          <h2>Lake Presets</h2>
          <div class="panel-subtitle">pinned, versioned queries and generators</div>
        </div>
        ${
          presets.length
            ? `
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Preset</th>
                      <th>Reference</th>
                      <th>Datasets</th>
                      <th>Config</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${presets
                      .map(
                        (preset) => `
                          <tr>
                            <td>
                              <div class="run-title">${escapeHtml(preset.name)}</div>
                              <div class="run-subtitle">${escapeHtml(preset.path)}</div>
                            </td>
                            <td>${preset.reference ? chip("reference", "yes", "is-warn") : chip("reference", "none")}</td>
                            <td>${escapeHtml(String((preset.datasets || []).length))}</td>
                            <td><span class="muted">use sidebar launcher</span></td>
                          </tr>
                        `,
                      )
                      .join("")}
                  </tbody>
                </table>
              </div>
            `
            : emptyState("No preset configs discovered.")}
      </section>
      <section class="panel">
        <div class="panel-head">
          <h2>Recent Lake Outputs</h2>
          <div class="panel-subtitle">materialized preset runs</div>
        </div>
        ${
          runtime?.lake?.recent_job_outputs?.length
            ? `
              <div class="section-stack">
                ${runtime.lake.recent_job_outputs
                  .map(
                    (item) => `
                      <div class="run-item">
                        <div class="run-title">${escapeHtml(item.name)}</div>
                        <div class="run-subtitle">${escapeHtml(item.path)}</div>
                        <div class="run-quick">${chip("updated", formatDate(item.modified_at), "is-blue")}</div>
                      </div>
                    `,
                  )
                  .join("")}
              </div>
            `
            : emptyState("No lake job outputs found yet.")}
      </section>
    </div>
  `;
}

function renderNotebookView() {
  const notebook = state.analysis?.notebook;
  if (!notebook) {
    return `
      <section class="panel">
        <div class="panel-head">
          <h2>Notebook</h2>
          <div class="panel-subtitle">deep analysis export is missing</div>
        </div>
        ${emptyState("Run the Notebook Export launcher in the sidebar to generate the HTML view.")}
      </section>
    `;
  }
  const src = `/api/notebook?ts=${encodeURIComponent(notebook.modified_at || String(Date.now()))}`;
  return `
    <section class="panel">
      <div class="panel-head">
        <h2>Notebook</h2>
        <div class="panel-subtitle">${escapeHtml(notebook.path)}</div>
      </div>
      <div class="chip-row">
        ${chip("updated", formatDate(notebook.modified_at), "is-blue")}
        ${chip("bytes", formatNumber(notebook.bytes, 0))}
      </div>
      <iframe class="notebook-frame" src="${escapeHtml(src)}" title="Deep Analysis Notebook"></iframe>
    </section>
  `;
}

function renderWorkspace() {
  switch (state.view) {
    case "runs":
      return renderRunsView();
    case "contrasts":
      return renderContrastsView();
    case "analysis":
      return renderAnalysisView();
    case "notebook":
      return renderNotebookView();
    default:
      return renderDashboardView();
  }
}

function renderDynamic() {
  document.querySelectorAll(".nav-box").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === state.view);
  });
  renderStatusStrip();
  renderJobsPanel();
  document.getElementById("workspace-root").innerHTML = renderWorkspace();
}

async function openFileDialog({ run, theorem, filename }) {
  const dialog = document.getElementById("file-dialog");
  const title = document.getElementById("file-dialog-title");
  const subtitle = document.getElementById("file-dialog-subtitle");
  const body = document.getElementById("file-dialog-body");
  title.textContent = filename || "Artifact";
  subtitle.textContent = theorem ? `${run} / ${theorem}` : run || "";
  body.innerHTML = emptyState("Loading file...");
  if (!dialog.open) {
    dialog.showModal();
  }
  if (!run || !filename) {
    body.innerHTML = emptyState("Missing run or filename.");
    return;
  }
  try {
    const artifact = await fetchArtifact(`/api/file?${qs({ run, theorem, file: filename })}`);
    if (artifact.data) {
      body.innerHTML = codeBlock(JSON.stringify(artifact.data, null, 2));
    } else {
      body.innerHTML = codeBlock(artifact.text || "");
    }
  } catch (error) {
    body.innerHTML = emptyState(error.message);
  }
}

async function refreshLoop() {
  try {
    await Promise.all([refreshJobs(), refreshRuns(), refreshContrasts(), refreshAnalysis()]);
    if (state.selectedRun) {
      await refreshSelectedRun();
      if (state.selectedTheorem) {
        await refreshSelectedTheorem();
      }
    }
    if (state.selectedContrast) {
      await refreshSelectedContrast();
    }
    renderDynamic();
  } catch (error) {
    flash(`refresh failed: ${error.message}`);
  }
}

async function init() {
  setupThemeControls();
  bindGlobalHandlers();
  await Promise.all([loadBootstrap(), refreshRuns(), refreshContrasts(), refreshJobs()]);
  renderLaunchers();
  if (!state.selectedRun && state.runs.length) {
    await selectRun(state.runs[0].rel_run_dir, { changeView: false });
  } else if (!state.selectedContrast && state.contrasts.length) {
    await selectContrast(state.contrasts[0].rel_dir, { changeView: false });
  } else {
    renderDynamic();
  }
  window.setInterval(refreshLoop, POLL_MS);
}

init().catch((error) => {
  document.getElementById("workspace-root").innerHTML = `
    <section class="panel">
      <div class="panel-head">
        <h2>Wonton Lab failed to boot</h2>
        <div class="panel-subtitle">frontend initialization error</div>
      </div>
      ${codeBlock(error.stack || error.message || String(error))}
    </section>
  `;
});
