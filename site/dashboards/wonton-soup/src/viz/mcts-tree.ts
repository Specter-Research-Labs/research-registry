import { hierarchy, tree as d3Tree, type HierarchyPointNode } from "d3-hierarchy";
import { scaleLog, scaleSequential } from "d3-scale";
import { interpolateRgb } from "d3-interpolate";
import katex from "katex";
import type { MctsTreeNode, MctsTreeEdge } from "../types";

export interface LayoutNode {
  mvarId: string;
  goalType: string | null;
  depth: number;
  visitCount: number;
  successCount: number;
  isTerminal: boolean;
  isDead: boolean;
  expansionOrder: number | null;
  x: number;
  y: number;
  radius: number;
}

interface TreeEdge {
  source: LayoutNode;
  target: LayoutNode;
  tactic: string;
  edgeOrder: number;
}

export interface PreparedMctsTree {
  root: LayoutNode;
  nodes: LayoutNode[];
  edges: TreeEdge[];
  maxVisits: number;
  maxDepth: number;
  byExpansionOrder: LayoutNode[];
}

export interface CanvasTransform {
  panX: number;
  panY: number;
  zoom: number;
}

export const DEFAULT_TRANSFORM: CanvasTransform = { panX: 0, panY: 0, zoom: 1 };

export type AnimPhase = "growth" | "proof_highlight" | "idle";

export interface RenderOpts {
  canvas: HTMLCanvasElement;
  variant: "wild" | "intervention";
  phase: AnimPhase;
  progress: number;
  highlightProof: boolean;
  transform?: CanvasTransform;
}

const WILD_PALETTE = {
  low: "#425f7b",
  high: "#ff6600",
  edge: "rgba(66, 95, 123, 0.32)",
  edgeProof: "rgba(255, 102, 0, 0.9)",
  glow: "#ff6600",
};

const INT_PALETTE = {
  low: "#2f6f64",
  high: "#00a645",
  edge: "rgba(47, 111, 100, 0.32)",
  edgeProof: "rgba(0, 166, 69, 0.9)",
  glow: "#00a645",
};

interface HierNode {
  id: string;
  data: MctsTreeNode;
  children?: HierNode[];
}

export function prepareMctsTree(
  nodes: MctsTreeNode[],
  edges: MctsTreeEdge[],
  width: number,
  height: number,
): PreparedMctsTree | null {
  if (nodes.length === 0) return null;

  const byId = new Map<string, MctsTreeNode>();
  for (const n of nodes) byId.set(n.mvar_id, n);

  const childMap = new Map<string, { childId: string; tactic: string; edgeOrder: number }[]>();
  const hasParent = new Set<string>();
  const seenEdges = new Set<string>();
  for (const e of edges) {
    const edgeKey = `${e.parent_mvar_id}\u0000${e.child_mvar_id}\u0000${e.tactic}\u0000${e.edge_order}`;
    if (seenEdges.has(edgeKey)) continue;
    seenEdges.add(edgeKey);

    let arr = childMap.get(e.parent_mvar_id);
    if (!arr) {
      arr = [];
      childMap.set(e.parent_mvar_id, arr);
    }
    arr.push({ childId: e.child_mvar_id, tactic: e.tactic, edgeOrder: Number(e.edge_order) });
    hasParent.add(e.child_mvar_id);
  }

  const rootNode = nodes.find((n) => !hasParent.has(n.mvar_id)) ?? nodes[0];

  function buildHier(mvarId: string): HierNode {
    const node = byId.get(mvarId)!;
    const kids = childMap.get(mvarId) ?? [];
    const children: HierNode[] = [];
    for (const k of kids) {
      if (byId.has(k.childId)) {
        children.push(buildHier(k.childId));
      }
    }
    return {
      id: mvarId,
      data: node,
      children: children.length > 0 ? children : undefined,
    };
  }

  const hierRoot = buildHier(rootNode.mvar_id);
  const root = hierarchy(hierRoot);

  const padding = { top: 40, right: 40, bottom: 40, left: 40 };
  const innerW = Math.max(width - padding.left - padding.right, 100);
  const innerH = Math.max(height - padding.top - padding.bottom, 100);

  const layout = d3Tree<HierNode>().size([innerW, innerH]);
  const laid = layout(root);

  const maxVisits = Math.max(1, ...nodes.map((n) => Number(n.visit_count)));
  const maxDepth = Math.max(1, ...nodes.map((n) => Number(n.depth)));
  const radiusScale = scaleLog().domain([1, Math.max(2, maxVisits)]).range([5, 16]).clamp(true);

  const layoutNodes: LayoutNode[] = [];
  const nodeMap = new Map<string, LayoutNode>();

  laid.each((d: HierarchyPointNode<HierNode>) => {
    const ln: LayoutNode = {
      mvarId: d.data.id,
      goalType: d.data.data.goal_type,
      depth: Number(d.data.data.depth),
      visitCount: Number(d.data.data.visit_count),
      successCount: Number(d.data.data.success_count),
      isTerminal: Boolean(d.data.data.is_terminal),
      isDead: Boolean(d.data.data.is_dead),
      expansionOrder: d.data.data.expansion_order != null ? Number(d.data.data.expansion_order) : null,
      x: d.x + padding.left,
      y: d.y + padding.top,
      radius: radiusScale(Math.max(1, Number(d.data.data.visit_count))),
    };
    layoutNodes.push(ln);
    nodeMap.set(ln.mvarId, ln);
  });

  const treeEdges: TreeEdge[] = [];
  for (const e of edges) {
    const src = nodeMap.get(e.parent_mvar_id);
    const tgt = nodeMap.get(e.child_mvar_id);
    if (src && tgt) {
      const edgeKey = `${e.parent_mvar_id}\u0000${e.child_mvar_id}\u0000${e.tactic}\u0000${e.edge_order}`;
      if (seenEdges.has(edgeKey)) {
        treeEdges.push({
          source: src,
          target: tgt,
          tactic: e.tactic,
          edgeOrder: Number(e.edge_order),
        });
        seenEdges.delete(edgeKey);
      }
    }
  }

  const byExpansionOrder = [...layoutNodes].sort((a, b) => {
    const ao = a.expansionOrder ?? Infinity;
    const bo = b.expansionOrder ?? Infinity;
    return ao - bo || a.depth - b.depth;
  });

  return {
    root: nodeMap.get(rootNode.mvar_id)!,
    nodes: layoutNodes,
    edges: treeEdges,
    maxVisits,
    maxDepth,
    byExpansionOrder,
  };
}

export function renderMctsTree(
  tree: PreparedMctsTree | null,
  opts: RenderOpts,
): void {
  const { canvas, variant, phase, progress } = opts;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, rect.width, rect.height);

  if (!tree) return;

  const t = opts.transform ?? DEFAULT_TRANSFORM;

  const pal = variant === "wild" ? WILD_PALETTE : INT_PALETTE;
  const colorScale = scaleSequential<string>()
    .domain([0, tree.maxVisits])
    .interpolator(interpolateRgb(pal.low, pal.high));

  const visibleCount =
    phase === "growth"
      ? Math.max(1, Math.floor(progress * tree.byExpansionOrder.length))
      : tree.byExpansionOrder.length;

  const visibleSet = new Set(
    tree.byExpansionOrder.slice(0, visibleCount).map((n) => n.mvarId),
  );

  ctx.save();
  ctx.translate(t.panX, t.panY);
  ctx.scale(t.zoom, t.zoom);

  const visibleEdges = tree.edges.filter((edge) => (
    visibleSet.has(edge.source.mvarId) && visibleSet.has(edge.target.mvarId)
  ));

  for (const edge of visibleEdges) {
    const isProof = opts.highlightProof && edge.source.successCount > 0 && edge.target.successCount > 0;

    ctx.beginPath();
    const midY = (edge.source.y + edge.target.y) / 2;
    ctx.moveTo(edge.source.x, edge.source.y);
    ctx.bezierCurveTo(
      edge.source.x, midY,
      edge.target.x, midY,
      edge.target.x, edge.target.y,
    );

    if (isProof) {
      ctx.strokeStyle = pal.edgeProof;
      ctx.lineWidth = 2.5;
      ctx.shadowColor = pal.glow;
      ctx.shadowBlur = 8;
    } else {
      ctx.strokeStyle = pal.edge;
      ctx.lineWidth = 1.2;
      ctx.shadowBlur = 0;
    }
    ctx.stroke();
    ctx.shadowBlur = 0;

  }

  const visibleNodes = tree.byExpansionOrder.slice(0, visibleCount);
  for (const node of visibleNodes) {
    const isProof = opts.highlightProof && node.successCount > 0;
    const color = colorScale(node.visitCount);

    if (isProof) {
      ctx.shadowColor = pal.glow;
      ctx.shadowBlur = 12;
    }

    ctx.beginPath();
    ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();

    if (node.isTerminal) {
      ctx.strokeStyle = pal.glow;
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    ctx.shadowBlur = 0;

    if (node.radius > 8) {
      ctx.font = "bold 11px 'Berkeley Mono', monospace";
      ctx.fillStyle = "rgba(15, 20, 30, 0.8)";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(node.visitCount), node.x, node.y);
    }
  }

  renderEdgeLabels(ctx, visibleEdges, visibleNodes, opts.highlightProof, pal);

  ctx.restore();
}

function renderEdgeLabels(
  ctx: CanvasRenderingContext2D,
  edges: TreeEdge[],
  nodes: LayoutNode[],
  highlightProof: boolean,
  pal: typeof WILD_PALETTE,
): void {
  if (edges.length === 0 || edges.length > 48) return;

  const occupied: Rect[] = nodes.map((node) => {
    const r = node.radius + 10;
    return { left: node.x - r, top: node.y - r, right: node.x + r, bottom: node.y + r };
  });

  ctx.save();
  ctx.font = "11px 'Berkeley Mono', monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  for (const edge of edges) {
    const isProof = highlightProof && edge.source.successCount > 0 && edge.target.successCount > 0;
    if (edges.length > 14 && !isProof) continue;

    const label = compactTactic(edge.tactic);
    if (!label) continue;

    const labelWidth = Math.min(170, ctx.measureText(label).width);
    const rectWidth = labelWidth + 14;
    const rectHeight = 22;
    const candidates = edgeLabelCandidates(edge, rectWidth, rectHeight);
    const placement = candidates.find((candidate) => {
      const rect = toRect(candidate.left, candidate.top, rectWidth, rectHeight);
      return occupied.every((existing) => !intersects(rect, existing));
    });
    if (!placement) continue;

    const rect = toRect(placement.left, placement.top, rectWidth, rectHeight);
    occupied.push(rect);

    ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
    ctx.strokeStyle = isProof ? pal.edgeProof : "rgba(11, 14, 20, 0.18)";
    ctx.lineWidth = 1;
    roundedRect(ctx, rect.left, rect.top, rectWidth, rectHeight, 4);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = isProof ? pal.edgeProof : "rgba(11, 14, 20, 0.64)";
    ctx.fillText(label, rect.left + rectWidth / 2, rect.top + rectHeight / 2 + 0.5, labelWidth);
  }

  ctx.restore();
}

interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

function edgeLabelCandidates(
  edge: TreeEdge,
  width: number,
  height: number,
): { left: number; top: number }[] {
  const dy = edge.edgeOrder % 2 === 0 ? -18 : 18;
  const altDy = -dy;
  const ts = edge.edgeOrder % 2 === 0
    ? [0.42, 0.58, 0.28, 0.72]
    : [0.58, 0.42, 0.72, 0.28];

  return [
    placeAt(edge, ts[0], width, height, dy),
    placeAt(edge, ts[1], width, height, altDy),
    placeAt(edge, ts[2], width, height, dy - 10),
    placeAt(edge, ts[3], width, height, altDy + 10),
    placeAt(edge, 0.5, width, height, -32),
    placeAt(edge, 0.5, width, height, 32),
  ];
}

function placeAt(
  edge: TreeEdge,
  t: number,
  width: number,
  height: number,
  dy: number,
): { left: number; top: number } {
  const p = edgePoint(edge, t);
  return { left: p.x - width / 2, top: p.y - height / 2 + dy };
}

function edgePoint(edge: TreeEdge, t: number): { x: number; y: number } {
  const midY = (edge.source.y + edge.target.y) / 2;
  const p0 = { x: edge.source.x, y: edge.source.y };
  const p1 = { x: edge.source.x, y: midY };
  const p2 = { x: edge.target.x, y: midY };
  const p3 = { x: edge.target.x, y: edge.target.y };
  const mt = 1 - t;
  return {
    x: mt ** 3 * p0.x + 3 * mt ** 2 * t * p1.x + 3 * mt * t ** 2 * p2.x + t ** 3 * p3.x,
    y: mt ** 3 * p0.y + 3 * mt ** 2 * t * p1.y + 3 * mt * t ** 2 * p2.y + t ** 3 * p3.y,
  };
}

function compactTactic(tactic: string): string {
  const normalized = tactic.replace(/\s+/g, " ").trim();
  if (!normalized) return "";
  if (/^rw \[/.test(normalized) && normalized.length > 22) return "rw [...]";

  const decideMatch = normalized.match(/^cases decide \((.+)\)$/);
  if (decideMatch) return `cases decide ${decideMatch[1].replace(/\s+/g, "")}`;

  const byCasesMatch = normalized.match(/^by_cases\s+[^:]+:\s*(.+)$/);
  if (byCasesMatch) return `by_cases ${byCasesMatch[1].replace(/\s+/g, "")}`;

  return normalized.length > 24 ? `${normalized.slice(0, 22)}..` : normalized;
}

function toRect(left: number, top: number, width: number, height: number): Rect {
  return { left, top, right: left + width, bottom: top + height };
}

function intersects(a: Rect, b: Rect): boolean {
  return !(a.left >= b.right || a.right <= b.left || a.top >= b.bottom || a.bottom <= b.top);
}

function roundedRect(
  ctx: CanvasRenderingContext2D,
  left: number,
  top: number,
  width: number,
  height: number,
  radius: number,
): void {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(left + r, top);
  ctx.lineTo(left + width - r, top);
  ctx.quadraticCurveTo(left + width, top, left + width, top + r);
  ctx.lineTo(left + width, top + height - r);
  ctx.quadraticCurveTo(left + width, top + height, left + width - r, top + height);
  ctx.lineTo(left + r, top + height);
  ctx.quadraticCurveTo(left, top + height, left, top + height - r);
  ctx.lineTo(left, top + r);
  ctx.quadraticCurveTo(left, top, left + r, top);
  ctx.closePath();
}

export function renderMathPanels(
  tree: PreparedMctsTree | null,
  overlay: HTMLElement,
  progress: number,
  _variant: "wild" | "intervention",
  highlightProof: boolean,
  transform?: CanvasTransform,
): void {
  if (!tree) {
    overlay.replaceChildren();
    return;
  }

  const t = transform ?? DEFAULT_TRANSFORM;
  const visibleCount = Math.max(1, Math.floor(progress * tree.byExpansionOrder.length));
  const visibleNodes = tree.byExpansionOrder.slice(0, visibleCount);
  const panelNodes = highlightProof
    ? visibleNodes.filter((node) => node.successCount > 0 || node.isTerminal)
    : visibleNodes.filter((node, index) => (
      visibleNodes.length <= 18
      || index === 0
      || index === visibleNodes.length - 1
      || node.isTerminal
    ));
  const overlayRect = overlay.getBoundingClientRect();
  const margin = 12;
  const maxPanelWidth = Math.max(180, Math.min(460, overlayRect.width - margin * 2));

  const existing = new Map<string, HTMLElement>();
  for (const child of overlay.children) {
    if (child instanceof HTMLElement && child.dataset.mvarId) {
      existing.set(child.dataset.mvarId, child);
    }
  }

  const keep = new Set<string>();

  for (const node of panelNodes) {
    keep.add(node.mvarId);
    let panel = existing.get(node.mvarId);

    if (!panel) {
      panel = document.createElement("div");
      panel.className = "mcts-math-panel";
      panel.dataset.mvarId = node.mvarId;
      panel.title = node.goalType ?? "";

      const mathSpan = document.createElement("span");
      mathSpan.className = "mcts-math";
      if (node.goalType) {
        katex.render(node.goalType, mathSpan, {
          throwOnError: false,
          displayMode: false,
        });
      } else {
        mathSpan.textContent = node.mvarId;
      }
      panel.appendChild(mathSpan);

      const badge = document.createElement("span");
      badge.className = "mcts-visit-badge";
      badge.textContent = `v${node.visitCount}`;
      panel.appendChild(badge);

      overlay.appendChild(panel);
    }

    const isProof = highlightProof && node.successCount > 0;
    panel.classList.toggle("on-proof-path", isProof);
    panel.classList.toggle("dimmed", !isProof && highlightProof);
    panel.style.maxWidth = `${maxPanelWidth}px`;
    panel.style.width = "";

    const sx = node.x * t.zoom + t.panX;
    const sy = node.y * t.zoom + t.panY;
    const measuredWidth = panel.scrollWidth || panel.offsetWidth || Math.min(320, maxPanelWidth);
    const panelWidth = Math.min(measuredWidth, maxPanelWidth);
    panel.style.width = `${panelWidth}px`;
    const panelHeight = panel.offsetHeight || 28;
    const nodeRadius = node.radius * t.zoom;
    const gap = Math.max(18, nodeRadius + 14);
    const candidates = [
      { left: sx + gap, top: sy - panelHeight / 2 },
      { left: sx - gap - panelWidth, top: sy - panelHeight / 2 },
      { left: sx - panelWidth / 2, top: sy + gap },
      { left: sx - panelWidth / 2, top: sy - gap - panelHeight },
    ];

    const placed = candidates.find((candidate) => (
      withinBounds(candidate.left, candidate.top, panelWidth, panelHeight, overlayRect.width, overlayRect.height, margin)
      && !overlapsNode(candidate.left, candidate.top, panelWidth, panelHeight, sx, sy, nodeRadius + 6)
    )) ?? candidates[0];

    const left = clamp(placed.left, margin, overlayRect.width - panelWidth - margin);
    const top = clamp(placed.top, margin, overlayRect.height - panelHeight - margin);
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
  }

  for (const [id, el] of existing) {
    if (!keep.has(id)) el.remove();
  }
}

export function hitTestMcts(
  tree: PreparedMctsTree,
  mx: number,
  my: number,
  transform?: CanvasTransform,
): { node: LayoutNode; tactic: string | null } | null {
  const t = transform ?? DEFAULT_TRANSFORM;
  const wmx = (mx - t.panX) / t.zoom;
  const wmy = (my - t.panY) / t.zoom;
  for (const node of tree.nodes) {
    const dx = wmx - node.x;
    const dy = wmy - node.y;
    const hitR = Math.max(node.radius, 8);
    if (dx * dx + dy * dy <= hitR * hitR) {
      const inEdge = tree.edges.find((e) => e.target.mvarId === node.mvarId);
      return { node, tactic: inEdge?.tactic ?? null };
    }
  }
  return null;
}

function clamp(value: number, min: number, max: number): number {
  if (max < min) return min;
  return Math.min(max, Math.max(min, value));
}

function withinBounds(
  left: number,
  top: number,
  width: number,
  height: number,
  boundsWidth: number,
  boundsHeight: number,
  margin: number,
): boolean {
  return (
    left >= margin
    && top >= margin
    && left + width <= boundsWidth - margin
    && top + height <= boundsHeight - margin
  );
}

function overlapsNode(
  left: number,
  top: number,
  width: number,
  height: number,
  nodeX: number,
  nodeY: number,
  radius: number,
): boolean {
  return !(
    left > nodeX + radius
    || left + width < nodeX - radius
    || top > nodeY + radius
    || top + height < nodeY - radius
  );
}
