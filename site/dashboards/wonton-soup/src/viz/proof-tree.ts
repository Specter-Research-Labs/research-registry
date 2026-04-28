import { hierarchy, tree as d3tree } from "d3-hierarchy";
import type { GraphNode, GraphEdge } from "../types";

export interface TreeRenderOpts {
  canvas: HTMLCanvasElement;
  variant: "wild" | "intervention";
  highlightProof: boolean;
  animationProgress: number;
}

interface LayoutNode {
  id: string;
  goalSig: string | null;
  goalType: string | null;
  inProof: boolean;
  children: LayoutNode[];
  x: number;
  y: number;
  depth: number;
  order: number;
}

interface LayoutEdge {
  src: LayoutNode;
  dst: LayoutNode;
  tactic: string | null;
  tacticFamily: string | null;
  inProof: boolean;
}

const PALETTE = {
  wild: {
    node: "#8694ad",
    nodeFill: "rgba(134,148,173,0.12)",
    nodeProof: "#a8b8cc",
    nodeProofFill: "rgba(134,148,173,0.25)",
    edge: "rgba(134,148,173,0.2)",
    edgeProof: "rgba(168,184,204,0.5)",
    glow: "rgba(134,148,173,0.08)",
    label: "rgba(134,148,173,0.7)",
    labelProof: "#a8b8cc",
    tacticLabel: "rgba(134,148,173,0.45)",
  },
  intervention: {
    node: "#4a8a61",
    nodeFill: "rgba(74,138,97,0.12)",
    nodeProof: "#6aaa81",
    nodeProofFill: "rgba(74,138,97,0.25)",
    edge: "rgba(74,138,97,0.2)",
    edgeProof: "rgba(106,170,129,0.5)",
    glow: "rgba(74,138,97,0.08)",
    label: "rgba(74,138,97,0.7)",
    labelProof: "#6aaa81",
    tacticLabel: "rgba(74,138,97,0.45)",
  },
};

export interface PreparedTree {
  allNodes: LayoutNode[];
  layoutEdges: LayoutEdge[];
  rawEdges: GraphEdge[];
  edgeTacticByKey: Map<string, string>;
  nodeRadius: number;
  totalNodes: number;
}

export function prepareTree(
  nodes: GraphNode[],
  edges: GraphEdge[],
  width: number,
  height: number,
): PreparedTree | null {
  if (nodes.length === 0) return null;

  const nodeMap = new Map<string, LayoutNode>();
  const childMap = new Map<string, string[]>();
  const hasParent = new Set<string>();

  for (const n of nodes) {
    nodeMap.set(n.node_id, {
      id: n.node_id,
      goalSig: n.goal_sig,
      goalType: n.goal_type,
      inProof: n.in_proof ?? false,
      children: [],
      x: 0,
      y: 0,
      depth: 0,
      order: 0,
    });
  }

  for (const e of edges) {
    if (!childMap.has(e.src_node_id)) childMap.set(e.src_node_id, []);
    childMap.get(e.src_node_id)!.push(e.dst_node_id);
    hasParent.add(e.dst_node_id);
  }

  const roots = nodes.filter((n) => !hasParent.has(n.node_id));
  const rootId = roots.length > 0 ? roots[0].node_id : nodes[0].node_id;
  const rootNode = nodeMap.get(rootId);
  if (!rootNode) return null;

  const visited = new Set<string>();
  function attach(node: LayoutNode): void {
    if (visited.has(node.id)) return;
    visited.add(node.id);
    for (const cid of childMap.get(node.id) ?? []) {
      const child = nodeMap.get(cid);
      if (child && !visited.has(cid)) {
        node.children.push(child);
        attach(child);
      }
    }
  }
  attach(rootNode);

  const h = hierarchy(rootNode, (d) => d.children);
  const treeLayout = d3tree<LayoutNode>().size([width - 80, height - 80]);
  const laid = treeLayout(h);

  let order = 0;
  laid.each((d) => {
    d.data.x = d.x + 40;
    d.data.y = d.y + 40;
    d.data.depth = d.depth;
    d.data.order = order++;
  });

  const allNodes = flattenTree(rootNode);

  const edgeTacticByKey = new Map<string, string>();
  const layoutEdges: LayoutEdge[] = [];
  for (const e of edges) {
    const src = nodeMap.get(e.src_node_id);
    const dst = nodeMap.get(e.dst_node_id);
    if (!src || !dst) continue;
    if (e.tactic) edgeTacticByKey.set(`${e.src_node_id}->${e.dst_node_id}`, e.tactic);
    layoutEdges.push({
      src,
      dst,
      tactic: e.tactic,
      tacticFamily: e.tactic_family,
      inProof: e.in_proof ?? false,
    });
  }

  const nodeRadius = Math.max(4, Math.min(8, 240 / Math.sqrt(allNodes.length)));

  return { allNodes, layoutEdges, rawEdges: edges, edgeTacticByKey, nodeRadius, totalNodes: allNodes.length };
}

export function renderTree(tree: PreparedTree | null, opts: TreeRenderOpts): void {
  const { canvas, variant, highlightProof, animationProgress } = opts;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  if (!tree) {
    renderEmpty(ctx, rect.width, rect.height, variant);
    return;
  }

  const { allNodes, layoutEdges, nodeRadius, totalNodes } = tree;
  const visibleCount = Math.floor(animationProgress * totalNodes);
  const visibleIds = new Set(allNodes.slice(0, visibleCount).map((n) => n.id));
  const pal = PALETTE[variant];
  const showLabels = totalNodes < 80;

  ctx.clearRect(0, 0, rect.width, rect.height);

  for (const e of layoutEdges) {
    if (!visibleIds.has(e.src.id) || !visibleIds.has(e.dst.id)) continue;
    const isProof = highlightProof && e.inProof;

    if (isProof) {
      ctx.save();
      ctx.shadowColor = pal.edgeProof;
      ctx.shadowBlur = 6;
    }

    ctx.beginPath();
    ctx.strokeStyle = isProof ? pal.edgeProof : pal.edge;
    ctx.lineWidth = isProof ? 2.5 : 1;

    const midY = (e.src.y + e.dst.y) / 2;
    ctx.moveTo(e.src.x, e.src.y);
    ctx.bezierCurveTo(e.src.x, midY, e.dst.x, midY, e.dst.x, e.dst.y);
    ctx.stroke();

    if (isProof) ctx.restore();

    if (showLabels && e.tactic) {
      const labelX = (e.src.x + e.dst.x) / 2;
      const labelY = (e.src.y + e.dst.y) / 2;
      const fontSize = Math.max(8, Math.min(11, 120 / Math.sqrt(totalNodes)));
      ctx.save();
      ctx.font = `${fontSize}px monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = isProof ? pal.labelProof : pal.tacticLabel;
      ctx.fillText(e.tactic, labelX + 4, labelY);
      ctx.restore();
    }
  }

  for (const node of allNodes) {
    if (!visibleIds.has(node.id)) continue;
    const isProof = highlightProof && node.inProof;

    if (isProof) {
      ctx.save();
      ctx.shadowColor = pal.nodeProof;
      ctx.shadowBlur = 10;
    }

    ctx.beginPath();
    ctx.arc(node.x, node.y, nodeRadius, 0, Math.PI * 2);
    ctx.fillStyle = isProof ? pal.nodeProofFill : pal.nodeFill;
    ctx.fill();
    ctx.strokeStyle = isProof ? pal.nodeProof : pal.node;
    ctx.lineWidth = isProof ? 2 : 1;
    ctx.stroke();

    if (isProof) ctx.restore();

    if (showLabels && node.goalType) {
      const label = truncateGoal(node.goalType, 32);
      const fontSize = Math.max(7, Math.min(10, 100 / Math.sqrt(totalNodes)));
      ctx.save();
      ctx.font = `${fontSize}px monospace`;
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillStyle = isProof ? pal.labelProof : pal.label;
      ctx.fillText(label, node.x + nodeRadius + 4, node.y);
      ctx.restore();
    }
  }
}

export function hitTest(
  tree: PreparedTree,
  mx: number,
  my: number,
): { node: LayoutNode; tactic: string | null } | null {
  const threshold = tree.nodeRadius + 6;
  let closest: LayoutNode | null = null;
  let closestDist = Infinity;

  for (const node of tree.allNodes) {
    const dx = node.x - mx;
    const dy = node.y - my;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < threshold && dist < closestDist) {
      closest = node;
      closestDist = dist;
    }
  }

  if (!closest) return null;

  let tactic: string | null = null;
  for (const [key, t] of tree.edgeTacticByKey) {
    if (key.endsWith(`->${closest.id}`)) {
      tactic = t;
      break;
    }
  }

  return { node: closest, tactic };
}

function truncateGoal(s: string, max: number): string {
  const clean = s.replace(/\n/g, " ").replace(/\s+/g, " ").trim();
  return clean.length > max ? clean.slice(0, max - 1) + "\u2026" : clean;
}

function flattenTree(root: LayoutNode): LayoutNode[] {
  const result: LayoutNode[] = [];
  const queue: LayoutNode[] = [root];
  while (queue.length > 0) {
    const node = queue.shift()!;
    result.push(node);
    for (const child of node.children) queue.push(child);
  }
  return result;
}

function renderEmpty(ctx: CanvasRenderingContext2D, w: number, h: number, variant: string): void {
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "rgba(110, 127, 141, 0.4)";
  ctx.font = "12px monospace";
  ctx.textAlign = "center";
  ctx.fillText(`No graph data for ${variant} variant`, w / 2, h / 2);
}
