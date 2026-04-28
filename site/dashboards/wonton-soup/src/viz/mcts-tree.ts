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
  low: "#4a6fa5",
  high: "#d4a853",
  edge: "rgba(135, 181, 209, 0.35)",
  edgeProof: "rgba(212, 168, 83, 0.9)",
  glow: "#d4a853",
};

const INT_PALETTE = {
  low: "#3a5f4a",
  high: "#6bc88a",
  edge: "rgba(74, 138, 97, 0.35)",
  edgeProof: "rgba(107, 200, 138, 0.9)",
  glow: "#6bc88a",
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

  const childMap = new Map<string, { childId: string; tactic: string }[]>();
  const hasParent = new Set<string>();
  for (const e of edges) {
    let arr = childMap.get(e.parent_mvar_id);
    if (!arr) {
      arr = [];
      childMap.set(e.parent_mvar_id, arr);
    }
    arr.push({ childId: e.child_mvar_id, tactic: e.tactic });
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
      treeEdges.push({ source: src, target: tgt, tactic: e.tactic });
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

  for (const edge of tree.edges) {
    if (!visibleSet.has(edge.source.mvarId) || !visibleSet.has(edge.target.mvarId))
      continue;

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

    if (tree.nodes.length < 60) {
      const labelX = (edge.source.x + edge.target.x) / 2;
      const labelY = midY - 4;
      ctx.font = "12px 'Berkeley Mono', monospace";
      ctx.fillStyle = isProof ? pal.edgeProof : "rgba(110, 127, 141, 0.6)";
      ctx.textAlign = "center";
      const label = edge.tactic.length > 20 ? edge.tactic.slice(0, 18) + ".." : edge.tactic;
      ctx.fillText(label, labelX, labelY);
    }
  }

  for (const node of tree.byExpansionOrder.slice(0, visibleCount)) {
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

  ctx.restore();
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

  const existing = new Map<string, HTMLElement>();
  for (const child of overlay.children) {
    if (child instanceof HTMLElement && child.dataset.mvarId) {
      existing.set(child.dataset.mvarId, child);
    }
  }

  const keep = new Set<string>();

  for (const node of tree.byExpansionOrder.slice(0, visibleCount)) {
    keep.add(node.mvarId);
    let panel = existing.get(node.mvarId);

    if (!panel) {
      panel = document.createElement("div");
      panel.className = "mcts-math-panel";
      panel.dataset.mvarId = node.mvarId;
      panel.title = node.goalType ?? "";

      const mathSpan = document.createElement("span");
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

    const sx = node.x * t.zoom + t.panX;
    const sy = node.y * t.zoom + t.panY;
    panel.style.left = `${sx + node.radius * t.zoom + 4}px`;
    panel.style.top = `${sy - 10}px`;
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
