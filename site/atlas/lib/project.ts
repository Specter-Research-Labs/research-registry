import "server-only";

import fs from "node:fs";
import path from "node:path";
import { cache } from "react";

const LENIA_PROJECT_SLUG = "lenia-swarm";
const CANONICAL_FEED_ROOTS = [
  path.join(process.cwd(), "public", "projects"),
  path.join(process.cwd(), "data", "projects")
];

type CanonicalSurfaceRecord = {
  label: string;
  href?: string | null;
  publish: boolean;
};

type CanonicalDossierRecord = {
  slug: string;
  title: string;
  summary: string;
  release_stage: string;
  last_activity: string;
  hub_href?: string | null;
  cabinet_href?: string | null;
  release_surfaces: CanonicalSurfaceRecord[];
};

type CanonicalCatalog = {
  dossiers: CanonicalDossierRecord[];
};

export type AtlasProjectLink = {
  href: string;
  label: string;
};

export type AtlasProjectContext = {
  title: string;
  summary: string;
  releaseStage: string;
  lastActivity: string;
  links: AtlasProjectLink[];
};

const loadProjectContextCached = cache(async (): Promise<AtlasProjectContext | null> => {
  const catalog = await readCanonicalCatalog();
  const dossier = catalog?.dossiers.find((entry) => entry.slug === LENIA_PROJECT_SLUG);
  if (!dossier) {
    return null;
  }

  const releaseLinks = dossier.release_surfaces
    .filter((surface) => surface.publish && Boolean(surface.href))
    .map((surface) => ({
      href: surface.href!,
      label: surface.label
    }));

  const links: AtlasProjectLink[] = [];
  pushLink(links, dossier.hub_href, "Dossier");
  pushLink(links, dossier.cabinet_href, "Docs");
  for (const link of releaseLinks) {
    pushLink(links, link.href, link.label);
  }

  return {
    title: dossier.title,
    summary: dossier.summary,
    releaseStage: dossier.release_stage,
    lastActivity: dossier.last_activity,
    links
  };
});

export async function getAtlasProjectContext(): Promise<AtlasProjectContext | null> {
  return loadProjectContextCached();
}

async function readCanonicalCatalog(): Promise<CanonicalCatalog | null> {
  return readCanonicalJson<CanonicalCatalog>("catalog.json");
}

async function readCanonicalJson<T>(fileName: string): Promise<T | null> {
  const filePath = firstExistingPath(canonicalFeedPaths(fileName));
  if (!filePath) {
    return null;
  }
  const raw = await fs.promises.readFile(filePath, "utf8");
  return JSON.parse(raw) as T;
}

function canonicalFeedPaths(fileName: string): string[] {
  const candidates = CANONICAL_FEED_ROOTS.map((root) => path.join(root, fileName));
  if (process.env.NODE_ENV !== "production") {
    candidates.push(path.join(process.cwd(), "..", "projects", fileName));
  }
  return candidates;
}

function firstExistingPath(candidates: string[]): string | null {
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function pushLink(links: AtlasProjectLink[], href: string | null | undefined, label: string) {
  if (!href) {
    return;
  }
  if (links.some((entry) => entry.href === href)) {
    return;
  }
  links.push({ href, label });
}
