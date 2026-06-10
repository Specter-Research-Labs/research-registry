import type { ViewId } from "./types";

type RouteHandler = (viewId: ViewId, params: URLSearchParams) => void;
type RouteParams = Record<string, string | null | undefined>;

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

function routeHash(view: ViewId, params?: RouteParams): string {
  const next = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value != null && value !== "") next.set(key, value);
  }
  const qs = next.toString();
  return qs ? `${view}?${qs}` : view;
}

function defaultParams(): RouteParams {
  const { params } = parseHash();
  const run = params.get("run");
  return run ? { run } : {};
}

export function navigate(view: ViewId, params?: RouteParams): void {
  location.hash = routeHash(view, { ...defaultParams(), ...(params ?? {}) });
}

export function replaceRoute(view: ViewId, params?: RouteParams): void {
  const nextUrl = `${location.pathname}${location.search}#${routeHash(view, {
    ...defaultParams(),
    ...(params ?? {}),
  })}`;
  history.replaceState(null, "", nextUrl);
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
