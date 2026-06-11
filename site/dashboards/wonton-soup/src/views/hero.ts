import "katex/dist/katex.min.css";
import katex from "katex";
import {
  getMctsTreeNodes,
  getMctsTreeEdges,
  getMctsVariants,
  getTheorems,
  resolveMctsTraceRunKey,
} from "../db";
import type { MctsTreeNode, MctsTreeEdge } from "../types";
import {
  prepareMctsTree,
  renderMctsTree,
  renderMathPanels,
  hitTestMcts,
  DEFAULT_TRANSFORM,
  type PreparedMctsTree,
  type CanvasTransform,
} from "../viz/mcts-tree";

interface HeroOpts {
  runKey: string;
  theorem?: string;
  intervention?: string;
  onSelectionChange?: (params: {
    theorem?: string;
    intervention?: string;
    variant?: null;
  }) => void;
}

let _animFrame: number | null = null;
let _playing = true;
let _progress = 0;
let _speed = 1;
let _tooltip: HTMLElement | null = null;
let _wildTree: PreparedMctsTree | null = null;
let _intTree: PreparedMctsTree | null = null;
let _scrubber: HTMLInputElement | null = null;
let _wildTransform: CanvasTransform = { ...DEFAULT_TRANSFORM };
let _intTransform: CanvasTransform = { ...DEFAULT_TRANSFORM };
let _panZoomAbort: AbortController | null = null;
let _mountToken = 0;


export async function mountHero(container: HTMLElement, opts: HeroOpts): Promise<void> {
  const mountToken = ++_mountToken;
  let renderToken = 0;
  if (_panZoomAbort) _panZoomAbort.abort();
  _panZoomAbort = new AbortController();

  container.className = "view-hero";

  const controls = document.createElement("div");
  controls.className = "hero-controls";

  const theoremLabel = document.createElement("span");
  theoremLabel.className = "control-label";
  theoremLabel.textContent = "Theorem";
  const theoremSelect = document.createElement("select");
  theoremSelect.id = "hero-theorem";

  const interventionLabel = document.createElement("span");
  interventionLabel.className = "control-label";
  interventionLabel.textContent = "Intervention";
  const interventionSelect = document.createElement("select");
  interventionSelect.id = "hero-intervention";

  const tacticBadge = document.createElement("span");
  tacticBadge.className = "tactic-blocked-badge";
  tacticBadge.hidden = true;

  const playBtn = document.createElement("button");
  playBtn.textContent = "Pause";
  playBtn.addEventListener("click", () => {
    _playing = !_playing;
    playBtn.textContent = _playing ? "Pause" : "Play";
  });

  const resetBtn = document.createElement("button");
  resetBtn.textContent = "Reset";
  resetBtn.addEventListener("click", () => {
    _progress = 0;
  });

  const speedLabel = document.createElement("span");
  speedLabel.className = "control-label";
  speedLabel.textContent = "Speed";
  const speedSelect = document.createElement("select");
  for (const s of [0.25, 0.5, 1, 2, 4]) {
    const opt = document.createElement("option");
    opt.value = String(s);
    opt.textContent = `${s}x`;
    if (s === 1) opt.selected = true;
    speedSelect.appendChild(opt);
  }
  speedSelect.addEventListener("change", () => {
    _speed = parseFloat(speedSelect.value);
  });

  controls.append(
    theoremLabel, theoremSelect,
    interventionLabel, interventionSelect,
    tacticBadge,
    playBtn, resetBtn,
    speedLabel, speedSelect,
  );

  const canvasRow = document.createElement("div");
  canvasRow.className = "hero-canvas-row act1";

  const wildPanel = createPanel("Wild Type", "wild");
  const interventionPanel = createPanel("Intervention", "intervention");
  canvasRow.append(wildPanel.el, interventionPanel.el);

  const timeline = document.createElement("div");
  timeline.className = "hero-timeline";
  const growthLabel = document.createElement("span");
  growthLabel.className = "timeline-label";
  growthLabel.textContent = "GROWTH";
  _scrubber = document.createElement("input");
  _scrubber.type = "range";
  _scrubber.min = "0";
  _scrubber.max = "1";
  _scrubber.step = "0.001";
  _scrubber.value = "0";
  _scrubber.addEventListener("input", () => {
    _progress = parseFloat(_scrubber!.value);
    _playing = false;
    playBtn.textContent = "Play";
  });
  timeline.append(growthLabel, _scrubber);

  _tooltip = document.createElement("div");
  _tooltip.className = "dash-tooltip";
  _tooltip.hidden = true;
  container.append(controls, canvasRow, timeline, _tooltip);

  setupHover(wildPanel.canvas, () => _wildTree, () => _wildTransform);
  setupHover(interventionPanel.canvas, () => _intTree, () => _intTransform);
  setupPanZoom(wildPanel.canvas, () => _wildTransform, (t) => { _wildTransform = t; }, _panZoomAbort.signal);
  setupPanZoom(interventionPanel.canvas, () => _intTransform, (t) => { _intTransform = t; }, _panZoomAbort.signal);

  const theorems = await getTheorems(opts.runKey);
  populateSelect(theoremSelect, theorems, opts.theorem);

  async function loadInterventions(): Promise<void> {
    const theorem = theoremSelect.value;
    if (!theorem) return;
    const variants = await getMctsVariants(opts.runKey, theorem);
    const interventions = variants.filter((v) => v !== "wild_type");
    if (interventions.length === 0) {
      interventionSelect.replaceChildren();
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No intervention trace";
      opt.selected = true;
      interventionSelect.appendChild(opt);
      interventionSelect.disabled = true;
      return;
    }
    interventionSelect.disabled = false;
    populateSelect(interventionSelect, interventions, opts.intervention);
  }

  theoremSelect.addEventListener("change", async () => {
    await loadInterventions();
    _progress = 0;
    _wildTransform = { ...DEFAULT_TRANSFORM };
    _intTransform = { ...DEFAULT_TRANSFORM };
    updateRoute();
    await renderPair();
  });

  interventionSelect.addEventListener("change", async () => {
    _progress = 0;
    _wildTransform = { ...DEFAULT_TRANSFORM };
    _intTransform = { ...DEFAULT_TRANSFORM };
    updateRoute();
    await renderPair();
  });

  await loadInterventions();
  updateRoute();

  async function renderPair(): Promise<void> {
    const activeRender = ++renderToken;
    const theorem = theoremSelect.value;
    const intervention = interventionSelect.value;
    if (!theorem) return;

    wildPanel.loading.hidden = false;
    interventionPanel.loading.hidden = false;

    try {
      const traceRunKey = await resolveMctsTraceRunKey(
        opts.runKey,
        theorem,
        intervention || "wild_type",
      );
      if (!traceRunKey) throw new Error(`No MCTS trace found for ${theorem} / ${intervention}`);

      const [wildNodes, wildEdges] = await Promise.all([
        getMctsTreeNodes(traceRunKey, theorem, "wild_type"),
        getMctsTreeEdges(traceRunKey, theorem, "wild_type"),
      ]);

      if (mountToken !== _mountToken || activeRender !== renderToken) return;

      const wildRect = wildPanel.canvas.getBoundingClientRect();
      _wildTree = prepareMctsTree(wildNodes, wildEdges, wildRect.width, wildRect.height);
      const wildTrivial = isTrivialTree(_wildTree, wildNodes);

      _intTree = null;
      let intTrivial = false;
      let intNodes: MctsTreeNode[] = [];
      let intEdges: MctsTreeEdge[] = [];
      if (intervention) {
        [intNodes, intEdges] = await Promise.all([
          getMctsTreeNodes(traceRunKey, theorem, intervention),
          getMctsTreeEdges(traceRunKey, theorem, intervention),
        ]);

        if (mountToken !== _mountToken || activeRender !== renderToken) return;

        const intRect = interventionPanel.canvas.getBoundingClientRect();
        _intTree = prepareMctsTree(intNodes, intEdges, intRect.width, intRect.height);
        intTrivial = isTrivialTree(_intTree, intNodes);

        const blocked = intervention.replace("block_", "");
        tacticBadge.textContent = `blocked: ${blocked}`;
        tacticBadge.hidden = false;
      } else {
        tacticBadge.hidden = true;
      }

      showTrivialOrCanvas(wildPanel, wildTrivial, wildNodes, wildEdges);
      if (intervention) {
        showTrivialOrCanvas(interventionPanel, intTrivial, intNodes, intEdges);
      } else {
        showEmptyPanel(
          interventionPanel,
          "No intervention trace for this theorem in the paper/poster cohort.",
        );
      }
      startAnimation(wildPanel, interventionPanel);
    } catch (err) {
      if (mountToken !== _mountToken || activeRender !== renderToken) return;
      console.error("Failed to render proof trees", err);
      _wildTree = null;
      _intTree = null;
      renderMctsTree(null, {
        canvas: wildPanel.canvas,
        variant: "wild",
        phase: "idle",
        progress: 1,
        highlightProof: false,
      });
      renderMctsTree(null, {
        canvas: interventionPanel.canvas,
        variant: "intervention",
        phase: "idle",
        progress: 1,
        highlightProof: false,
      });
    } finally {
      if (mountToken === _mountToken && activeRender === renderToken) {
        wildPanel.loading.hidden = true;
        interventionPanel.loading.hidden = true;
      }
    }
  }

  function updateRoute(): void {
    opts.onSelectionChange?.({
      theorem: theoremSelect.value,
      intervention: interventionSelect.value,
      variant: null,
    });
  }

  await renderPair();
}

interface Panel {
  el: HTMLElement;
  canvas: HTMLCanvasElement;
  overlay: HTMLElement;
  loading: HTMLElement;
  empty: HTMLElement;
  canvasWrap: HTMLElement;
  tacticChain: HTMLElement;
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
  canvasWrap.className = "hero-canvas-wrap";
  canvasWrap.style.position = "relative";
  canvasWrap.style.flex = "1";

  const canvas = document.createElement("canvas");
  const overlay = document.createElement("div");
  overlay.className = "mcts-overlay";

  const loading = document.createElement("div");
  loading.className = "hero-loading";
  loading.setAttribute("aria-live", "polite");
  loading.textContent = "Loading\u2026";
  loading.hidden = true;

  const empty = document.createElement("div");
  empty.className = "hero-panel-empty";
  empty.hidden = true;

  const tacticChain = document.createElement("div");
  tacticChain.className = "tactic-chain";
  tacticChain.hidden = true;

  canvasWrap.append(canvas, overlay, loading, empty, tacticChain);
  el.append(header, canvasWrap);

  return { el, canvas, overlay, loading, empty, canvasWrap, tacticChain };
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

function setupHover(
  canvas: HTMLCanvasElement,
  getTree: () => PreparedMctsTree | null,
  getTransform: () => CanvasTransform,
): void {
  canvas.addEventListener("mousemove", (e) => {
    const tree = getTree();
    if (!tree || !_tooltip) return;

    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const hit = hitTestMcts(tree, mx, my, getTransform());

    if (hit) {
      const lines: string[] = [];
      if (hit.node.goalType) lines.push(hit.node.goalType);
      if (hit.tactic) lines.push(`tactic: ${hit.tactic}`);
      lines.push(`visits: ${hit.node.visitCount}, success: ${hit.node.successCount}`);
      if (hit.node.isTerminal) lines.push("terminal (solved)");
      if (hit.node.isDead) lines.push("dead end");

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

const ZOOM_MIN = 0.3;
const ZOOM_MAX = 5;

function setupPanZoom(
  canvas: HTMLCanvasElement,
  getTransform: () => CanvasTransform,
  setTransform: (t: CanvasTransform) => void,
  signal: AbortSignal,
): void {
  let dragging = false;
  let lastX = 0;
  let lastY = 0;

  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const t = getTransform();
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const delta = e.deltaY * -0.001;
    const newZoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, t.zoom + delta));
    const scale = newZoom / t.zoom;

    setTransform({
      panX: mx - scale * (mx - t.panX),
      panY: my - scale * (my - t.panY),
      zoom: newZoom,
    });
  }, { passive: false });

  canvas.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    canvas.style.cursor = "grabbing";
  });

  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const t = getTransform();
    setTransform({
      panX: t.panX + (e.clientX - lastX),
      panY: t.panY + (e.clientY - lastY),
      zoom: t.zoom,
    });
    lastX = e.clientX;
    lastY = e.clientY;
  }, { signal });

  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    canvas.style.cursor = "";
  }, { signal });

  canvas.addEventListener("dblclick", () => {
    setTransform({ ...DEFAULT_TRANSFORM });
  });
}

function isTrivialTree(tree: PreparedMctsTree | null, nodes: MctsTreeNode[]): boolean {
  return tree === null || nodes.length <= 2;
}

function showTrivialOrCanvas(
  panel: Panel,
  trivial: boolean,
  nodes: MctsTreeNode[],
  edges: MctsTreeEdge[],
): void {
  if (trivial && nodes.length > 0) {
    panel.canvas.hidden = true;
    panel.overlay.hidden = true;
    panel.empty.hidden = true;
    panel.tacticChain.hidden = false;
    renderTacticChain(panel.tacticChain, nodes, edges);
  } else {
    panel.canvas.hidden = false;
    panel.overlay.hidden = false;
    panel.empty.hidden = true;
    panel.tacticChain.hidden = true;
    panel.tacticChain.replaceChildren();
  }
}

function showEmptyPanel(panel: Panel, message: string): void {
  panel.canvas.hidden = true;
  panel.overlay.hidden = true;
  panel.tacticChain.hidden = true;
  panel.tacticChain.replaceChildren();
  panel.empty.textContent = message;
  panel.empty.hidden = false;
}

function renderTacticChain(
  container: HTMLElement,
  nodes: MctsTreeNode[],
  edges: MctsTreeEdge[],
): void {
  container.replaceChildren();

  if (nodes.length === 1) {
    const goalEl = document.createElement("span");
    goalEl.className = "tactic-chain-goal";
    renderGoalContent(goalEl, nodes[0].goal_type);

    const solvedLabel = document.createElement("span");
    solvedLabel.className = "tactic-chain-arrow";
    solvedLabel.textContent = "(solved immediately)";

    container.append(goalEl, solvedLabel);
    return;
  }

  const hasParent = new Set<string>();
  for (const e of edges) hasParent.add(e.child_mvar_id);
  const rootNode = nodes.find((n) => !hasParent.has(n.mvar_id)) ?? nodes[0];
  const childNode = nodes.find((n) => n.mvar_id !== rootNode.mvar_id);
  const edge = edges[0];

  const goalEl = document.createElement("span");
  goalEl.className = "tactic-chain-goal";
  renderGoalContent(goalEl, rootNode.goal_type);
  container.appendChild(goalEl);

  if (edge) {
    const arrowEl = document.createElement("span");
    arrowEl.className = "tactic-chain-arrow";
    const tacticLabel = edge.tactic.length > 30 ? edge.tactic.slice(0, 28) + ".." : edge.tactic;
    arrowEl.textContent = `\u2192 ${tacticLabel} \u2192`;
    container.appendChild(arrowEl);
  }

  if (childNode) {
    const subgoalEl = document.createElement("span");
    subgoalEl.className = "tactic-chain-goal";
    renderGoalContent(subgoalEl, childNode.goal_type);
    container.appendChild(subgoalEl);
  }
}

function renderGoalContent(el: HTMLElement, goalType: string | null): void {
  if (goalType) {
    katex.render(goalType, el, { throwOnError: false, displayMode: false });
  } else {
    el.textContent = "?";
  }
}

function startAnimation(
  wildPanel: Panel,
  intPanel: Panel,
): void {
  if (_animFrame != null) cancelAnimationFrame(_animFrame);
  _progress = 0;

  function frame(): void {
    if (_playing) {
      _progress = Math.min(1, _progress + 0.002 * _speed);
    }

    if (_scrubber) {
      _scrubber.value = String(_progress);
    }

    const highlight = _progress >= 0.7;

    renderMctsTree(_wildTree, {
      canvas: wildPanel.canvas,
      variant: "wild",
      phase: "growth",
      progress: _progress,
      highlightProof: highlight,
      transform: _wildTransform,
    });
    renderMathPanels(_wildTree, wildPanel.overlay, _progress, "wild", highlight, _wildTransform);

    renderMctsTree(_intTree, {
      canvas: intPanel.canvas,
      variant: "intervention",
      phase: "growth",
      progress: _progress,
      highlightProof: highlight,
      transform: _intTransform,
    });
    renderMathPanels(_intTree, intPanel.overlay, _progress, "intervention", highlight, _intTransform);

    _animFrame = requestAnimationFrame(frame);
  }

  _animFrame = requestAnimationFrame(frame);
}

export function unmountHero(): void {
  _mountToken++;
  if (_panZoomAbort) {
    _panZoomAbort.abort();
    _panZoomAbort = null;
  }
  if (_animFrame != null) {
    cancelAnimationFrame(_animFrame);
    _animFrame = null;
  }
  _playing = true;
  _progress = 0;
  _speed = 1;
  _wildTree = null;
  _intTree = null;
  _scrubber = null;
  _wildTransform = { ...DEFAULT_TRANSFORM };
  _intTransform = { ...DEFAULT_TRANSFORM };
  if (_tooltip) {
    _tooltip.hidden = true;
    _tooltip = null;
  }
}
