import type { ViewId } from "./types";

type RouteHandler = (viewId: ViewId, params: URLSearchParams) => void;

const VALID_VIEWS: ViewId[] = ["hero", "proof-graph", "rescue", "explorer"];
const DEFAULT_VIEW: ViewId = "hero";

let _handler: RouteHandler | null = null;

export function parseHash(): { view: ViewId; params: URLSearchParams } {
  const raw = location.hash.replace(/^#/, "");
  const [path, qs] = raw.split("?", 2);
  const view = VALID_VIEWS.includes(path as ViewId) ? (path as ViewId) : DEFAULT_VIEW;
  const params = new URLSearchParams(qs ?? "");
  return { view, params };
}

export function navigate(view: ViewId, params?: Record<string, string>): void {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  location.hash = `${view}${qs}`;
}

export function startRouter(handler: RouteHandler): void {
  _handler = handler;
  window.addEventListener("hashchange", () => {
    const { view, params } = parseHash();
    _handler?.(view, params);
  });
  const { view, params } = parseHash();
  handler(view, params);
}
