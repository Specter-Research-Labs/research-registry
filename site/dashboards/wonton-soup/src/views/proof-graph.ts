import { getGraphNodes, getGraphEdges, getGraphVariants, getGraphTheorems } from "../db";
import { prepareTree, renderTree, hitTest, type PreparedTree } from "../viz/proof-tree";

interface ProofGraphOpts {
  runKey: string;
  theorem?: string;
  variant?: string;
}

let _animFrame: number | null = null;
let _progress = 0;
let _highlightProof = true;
let _tooltip: HTMLElement | null = null;
let _wildTree: PreparedTree | null = null;
let _intTree: PreparedTree | null = null;
let _wildPanel: Panel | null = null;
let _intPanel: Panel | null = null;

export async function mountProofGraph(container: HTMLElement, opts: ProofGraphOpts): Promise<void> {
  container.className = "view-proof-graph";

  const controls = document.createElement("div");
  controls.className = "hero-controls";

  const theoremLabel = document.createElement("span");
  theoremLabel.className = "control-label";
  theoremLabel.textContent = "Theorem";
  const theoremSelect = document.createElement("select");
  theoremSelect.id = "pg-theorem";

  const variantLabel = document.createElement("span");
  variantLabel.className = "control-label";
  variantLabel.textContent = "Variant";
  const variantSelect = document.createElement("select");
  variantSelect.id = "pg-variant";

  const highlightLabel = document.createElement("label");
  highlightLabel.className = "control-label";
  highlightLabel.style.display = "flex";
  highlightLabel.style.alignItems = "center";
  highlightLabel.style.gap = "0.35rem";
  const highlightCheck = document.createElement("input");
  highlightCheck.type = "checkbox";
  highlightCheck.checked = _highlightProof;
  highlightCheck.addEventListener("change", () => {
    _highlightProof = highlightCheck.checked;
    if (_animFrame === null) renderCurrentFrame();
  });
  const highlightText = document.createElement("span");
  highlightText.textContent = "Highlight proof path";
  highlightLabel.append(highlightCheck, highlightText);

  controls.append(
    theoremLabel, theoremSelect,
    variantLabel, variantSelect,
    highlightLabel,
  );

  const canvasRow = document.createElement("div");
  canvasRow.className = "hero-canvas-row";

  _wildPanel = createPanel("Wild Type", "wild");
  _intPanel = createPanel("Intervention", "intervention");
  const wildPanel = _wildPanel;
  const interventionPanel = _intPanel;
  canvasRow.append(wildPanel.el, interventionPanel.el);

  _tooltip = document.createElement("div");
  _tooltip.className = "dash-tooltip";
  _tooltip.hidden = true;
  container.append(controls, canvasRow, _tooltip);

  setupHover(wildPanel.canvas, () => _wildTree);
  setupHover(interventionPanel.canvas, () => _intTree);

  const theorems = await getGraphTheorems(opts.runKey);
  populateSelect(theoremSelect, theorems, opts.theorem);

  async function loadVariants(): Promise<void> {
    const theorem = theoremSelect.value;
    if (!theorem) return;
    const variants = await getGraphVariants(opts.runKey, theorem);
    const interventions = variants.filter((v) => v !== "wild_type");
    populateSelect(variantSelect, interventions, opts.variant);
  }

  theoremSelect.addEventListener("change", async () => {
    await loadVariants();
    _progress = 0;
    await renderPair();
  });

  variantSelect.addEventListener("change", async () => {
    _progress = 0;
    await renderPair();
  });

  await loadVariants();

  async function renderPair(): Promise<void> {
    const theorem = theoremSelect.value;
    const variant = variantSelect.value;
    if (!theorem) return;

    wildPanel.loading.hidden = false;
    interventionPanel.loading.hidden = false;

    const [wildNodes, wildEdges] = await Promise.all([
      getGraphNodes(opts.runKey, theorem, "wild_type"),
      getGraphEdges(opts.runKey, theorem, "wild_type"),
    ]);

    const wildRect = wildPanel.canvas.getBoundingClientRect();
    _wildTree = prepareTree(wildNodes, wildEdges, wildRect.width, wildRect.height);

    _intTree = null;
    if (variant) {
      const [intNodes, intEdges] = await Promise.all([
        getGraphNodes(opts.runKey, theorem, variant),
        getGraphEdges(opts.runKey, theorem, variant),
      ]);
      const intRect = interventionPanel.canvas.getBoundingClientRect();
      _intTree = prepareTree(intNodes, intEdges, intRect.width, intRect.height);
    }

    wildPanel.loading.hidden = true;
    interventionPanel.loading.hidden = true;
    startAnimation(wildPanel, interventionPanel);
  }

  await renderPair();
}

interface Panel {
  el: HTMLElement;
  canvas: HTMLCanvasElement;
  loading: HTMLElement;
}

function createPanel(label: string, variant: "wild" | "intervention"): Panel {
  const el = document.createElement("div");
  el.className = "hero-panel";

  const header = document.createElement("div");
  header.className = "hero-panel-header";

  const badge = document.createElement("div");
  badge.className = `hero-panel-badge ${variant}`;

  const labelEl = document.createElement("span");
  labelEl.className = "hero-panel-label";
  labelEl.textContent = label;

  header.append(badge, labelEl);

  const canvasWrap = document.createElement("div");
  canvasWrap.style.position = "relative";
  canvasWrap.style.flex = "1";

  const canvas = document.createElement("canvas");

  const loading = document.createElement("div");
  loading.className = "hero-loading";
  loading.textContent = "Loading\u2026";
  loading.hidden = true;

  canvasWrap.append(canvas, loading);
  el.append(header, canvasWrap);

  return { el, canvas, loading };
}

function populateSelect(select: HTMLSelectElement, values: string[], preferred?: string): void {
  select.replaceChildren();
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    if (v === preferred) opt.selected = true;
    select.appendChild(opt);
  }
}

function setupHover(canvas: HTMLCanvasElement, getTree: () => PreparedTree | null): void {
  canvas.addEventListener("mousemove", (e) => {
    const tree = getTree();
    if (!tree || !_tooltip) return;

    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const hit = hitTest(tree, mx, my);

    if (hit) {
      const lines: string[] = [];
      if (hit.node.goalType) lines.push(hit.node.goalType);
      if (hit.tactic) lines.push(`tactic: ${hit.tactic}`);
      if (hit.node.inProof) lines.push("on proof path");

      _tooltip.textContent = lines.join("\n");
      _tooltip.hidden = false;
      _tooltip.style.left = `${e.clientX + 12}px`;
      _tooltip.style.top = `${e.clientY - 8}px`;
      return;
    }

    _tooltip.hidden = true;
  });

  canvas.addEventListener("mouseleave", () => {
    if (_tooltip) _tooltip.hidden = true;
  });
}

function renderCurrentFrame(): void {
  if (!_wildPanel || !_intPanel) return;
  requestAnimationFrame(() => {
    renderTree(_wildTree, {
      canvas: _wildPanel!.canvas,
      variant: "wild",
      highlightProof: _highlightProof,
      animationProgress: _progress,
    });
    renderTree(_intTree, {
      canvas: _intPanel!.canvas,
      variant: "intervention",
      highlightProof: _highlightProof,
      animationProgress: _progress,
    });
  });
}

function startAnimation(wildPanel: Panel, intPanel: Panel): void {
  if (_animFrame != null) cancelAnimationFrame(_animFrame);
  _progress = 0;

  function frame(): void {
    _progress = Math.min(1, _progress + 0.015);

    renderTree(_wildTree, {
      canvas: wildPanel.canvas,
      variant: "wild",
      highlightProof: _highlightProof,
      animationProgress: _progress,
    });

    renderTree(_intTree, {
      canvas: intPanel.canvas,
      variant: "intervention",
      highlightProof: _highlightProof,
      animationProgress: _progress,
    });

    if (_progress < 1) {
      _animFrame = requestAnimationFrame(frame);
    } else {
      _animFrame = null;
    }
  }

  _animFrame = requestAnimationFrame(frame);
}

export function unmountProofGraph(): void {
  if (_animFrame != null) {
    cancelAnimationFrame(_animFrame);
    _animFrame = null;
  }
  _progress = 0;
  _wildTree = null;
  _intTree = null;
  _wildPanel = null;
  _intPanel = null;
  if (_tooltip) {
    _tooltip.hidden = true;
    _tooltip = null;
  }
}
