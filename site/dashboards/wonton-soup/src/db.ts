import * as duckdb from "@duckdb/duckdb-wasm";
import duckdb_wasm from "@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url";
import mvp_worker from "@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url";
import duckdb_wasm_eh from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";
import eh_worker from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import type { Manifest, ManifestTable } from "./types";

function defaultDataBaseUrl(): string {
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1" || host === "::1") {
    return `${window.location.origin}/dashboards/wonton-soup/data`;
  }
  return "https://specterlab.org/data/wonton-soup";
}

const DATA_BASE_URL = import.meta.env.VITE_DATA_URL ?? defaultDataBaseUrl();
export const PAPER_POSTER_DATASET_KEY = "paper-poster-cohort";

const MANUAL_BUNDLES: duckdb.DuckDBBundles = {
  mvp: { mainModule: duckdb_wasm, mainWorker: mvp_worker },
  eh: { mainModule: duckdb_wasm_eh, mainWorker: eh_worker },
};

let _conn: duckdb.AsyncDuckDBConnection | null = null;
let _manifest: Manifest | null = null;

export async function initDB(onProgress?: (msg: string) => void): Promise<void> {
  onProgress?.("Fetching DuckDB-WASM bundles");

  const bundle = await duckdb.selectBundle(MANUAL_BUNDLES);

  const worker = new Worker(bundle.mainWorker!);

  const logger = new duckdb.ConsoleLogger();
  const db = new duckdb.AsyncDuckDB(logger, worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);

  _conn = await db.connect();

  onProgress?.("Loading manifest");
  const manifestUrl = `${DATA_BASE_URL}/dashboard_manifest.json`;
  const resp = await fetch(manifestUrl);
  if (!resp.ok) throw new Error(`Failed to fetch manifest: ${resp.status} ${resp.statusText}`);
  _manifest = (await resp.json()) as Manifest;

  onProgress?.("Registering parquet views");
  for (const table of _manifest.tables) {
    await registerTable(table);
  }

  onProgress?.("Ready");
}

const SAFE_TABLE_NAME = /^[a-z][a-z0-9_]+$/;

async function registerTable(table: ManifestTable): Promise<void> {
  if (!SAFE_TABLE_NAME.test(table.name)) {
    throw new Error(`Unsafe table name: ${table.name}`);
  }
  const conn = getConn();
  const url = `${DATA_BASE_URL}/${table.file}`;
  await conn.query(`
    CREATE VIEW ${table.name} AS
    SELECT * FROM parquet_scan('${url}')
  `);
}

function getConn(): duckdb.AsyncDuckDBConnection {
  if (!_conn) throw new Error("DuckDB not initialized — call initDB() first");
  return _conn;
}

export function getManifest(): Manifest {
  if (!_manifest) throw new Error("Manifest not loaded — call initDB() first");
  return _manifest;
}

function esc(value: string): string {
  return value.replaceAll("'", "''");
}

function isPaperPosterDataset(scopeKey: string): boolean {
  return scopeKey === PAPER_POSTER_DATASET_KEY;
}

export function runFilterSql(scopeKey: string, alias?: string): string {
  if (isPaperPosterDataset(scopeKey)) return "TRUE";
  const column = alias ? `${alias}.run_key` : "run_key";
  return `${column} = '${esc(scopeKey)}'`;
}

export async function query<T>(sql: string): Promise<T[]> {
  const conn = getConn();
  const result = await conn.query(sql);
  return result.toArray().map((row) => row.toJSON() as T);
}

export async function queryOne<T>(sql: string): Promise<T | null> {
  const rows = await query<T>(sql);
  return rows.length > 0 ? rows[0] : null;
}

export async function queryScalar<T>(sql: string): Promise<T> {
  const conn = getConn();
  const result = await conn.query(sql);
  const rows = result.toArray();
  if (rows.length === 0) throw new Error(`queryScalar returned no rows: ${sql}`);
  const values = Object.values(rows[0].toJSON() as Record<string, unknown>);
  return values[0] as T;
}

export async function getRunKeys(): Promise<string[]> {
  return (
    await query<{ run_key: string }>(
      `SELECT DISTINCT run_key FROM mcts_tree_nodes
       GROUP BY run_key HAVING count(DISTINCT variant) >= 2
       ORDER BY run_key`,
    )
  ).map((r) => r.run_key);
}

export async function getTheorems(runKey: string): Promise<string[]> {
  return (
    await query<{ theorem: string }>(
      `SELECT theorem FROM mcts_tree_nodes
       WHERE ${runFilterSql(runKey)}
       GROUP BY theorem
       HAVING count(DISTINCT CASE WHEN variant <> 'wild_type' THEN variant END) > 0
       ORDER BY theorem`,
    )
  ).map((r) => r.theorem);
}

export async function getInterventions(runKey: string, theorem: string): Promise<string[]> {
  return (
    await query<{ intervention: string }>(
      `SELECT DISTINCT intervention FROM theorem_intervention
       WHERE ${runFilterSql(runKey)} AND theorem = '${esc(theorem)}'
         AND is_control = false
       ORDER BY intervention`,
    )
  ).map((r) => r.intervention);
}

export async function resolveMctsTraceRunKey(
  scopeKey: string,
  theorem: string,
  variant: string,
): Promise<string | null> {
  if (!isPaperPosterDataset(scopeKey)) return scopeKey;
  return resolveTraceRunKey("mcts_tree_nodes", scopeKey, theorem, variant);
}

export async function resolveGraphTraceRunKey(
  scopeKey: string,
  theorem: string,
  variant: string,
): Promise<string | null> {
  if (!isPaperPosterDataset(scopeKey)) return scopeKey;
  return resolveTraceRunKey("graph_nodes", scopeKey, theorem, variant, "search_trace");
}

async function resolveTraceRunKey(
  tableName: "mcts_tree_nodes" | "graph_nodes",
  scopeKey: string,
  theorem: string,
  variant: string,
  graphKind?: string,
): Promise<string | null> {
  const graphFilter = graphKind ? `AND graph_kind = '${esc(graphKind)}'` : "";
  const rows = await query<{ run_key: string }>(
    `WITH candidates AS (
       SELECT run_key
       FROM ${tableName}
       WHERE ${runFilterSql(scopeKey)} AND theorem = '${esc(theorem)}'
         AND variant = '${esc(variant)}' ${graphFilter}
       GROUP BY run_key
     ),
     wild AS (
       SELECT run_key
       FROM ${tableName}
       WHERE ${runFilterSql(scopeKey)} AND theorem = '${esc(theorem)}'
         AND variant = 'wild_type' ${graphFilter}
       GROUP BY run_key
     ),
     variant_counts AS (
       SELECT run_key, count(DISTINCT variant) AS variant_count
       FROM ${tableName}
       WHERE ${runFilterSql(scopeKey)} AND theorem = '${esc(theorem)}' ${graphFilter}
       GROUP BY run_key
     )
     SELECT c.run_key
     FROM candidates c
     JOIN wild w USING(run_key)
     JOIN variant_counts vc USING(run_key)
     LEFT JOIN runs r USING(run_key)
     ORDER BY vc.variant_count DESC,
       CASE r.provider
         WHEN 'deepseek' THEN 0
         WHEN 'heuristic' THEN 1
         WHEN 'reprover' THEN 2
         ELSE 3
       END,
       r.created_at DESC NULLS LAST,
       c.run_key
     LIMIT 1`,
  );
  return rows[0]?.run_key ?? null;
}

export async function getMctsTreeNodes(
  runKey: string,
  theorem: string,
  variant: string,
): Promise<import("./types").MctsTreeNode[]> {
  return query<import("./types").MctsTreeNode>(
    `SELECT * FROM mcts_tree_nodes
     WHERE run_key = '${esc(runKey)}' AND theorem = '${esc(theorem)}' AND variant = '${esc(variant)}'
     ORDER BY depth, mvar_id`,
  );
}

export async function getMctsTreeEdges(
  runKey: string,
  theorem: string,
  variant: string,
): Promise<import("./types").MctsTreeEdge[]> {
  return query<import("./types").MctsTreeEdge>(
    `SELECT * FROM mcts_tree_edges
     WHERE run_key = '${esc(runKey)}' AND theorem = '${esc(theorem)}' AND variant = '${esc(variant)}'
     ORDER BY parent_mvar_id, edge_order`,
  );
}

export async function getMctsVariants(
  runKey: string,
  theorem: string,
): Promise<string[]> {
  return (
    await query<{ variant: string }>(
      `SELECT DISTINCT variant FROM mcts_tree_nodes
       WHERE ${runFilterSql(runKey)} AND theorem = '${esc(theorem)}'
       ORDER BY variant`,
    )
  ).map((r) => r.variant);
}

export async function getGraphNodes(
  runKey: string,
  theorem: string,
  variant: string,
  graphKind = "search_trace",
): Promise<import("./types").GraphNode[]> {
  return query<import("./types").GraphNode>(
    `SELECT * FROM graph_nodes
     WHERE run_key = '${esc(runKey)}' AND theorem = '${esc(theorem)}'
       AND variant = '${esc(variant)}' AND graph_kind = '${esc(graphKind)}'
     ORDER BY node_id`,
  );
}

export async function getGraphEdges(
  runKey: string,
  theorem: string,
  variant: string,
  graphKind = "search_trace",
): Promise<import("./types").GraphEdge[]> {
  return query<import("./types").GraphEdge>(
    `SELECT * FROM graph_edges
     WHERE run_key = '${esc(runKey)}' AND theorem = '${esc(theorem)}'
       AND variant = '${esc(variant)}' AND graph_kind = '${esc(graphKind)}'
     ORDER BY edge_idx`,
  );
}

export async function getGraphVariants(
  runKey: string,
  theorem: string,
): Promise<string[]> {
  return (
    await query<{ variant: string }>(
      `SELECT DISTINCT variant FROM graph_nodes
       WHERE ${runFilterSql(runKey)} AND theorem = '${esc(theorem)}'
       ORDER BY variant`,
    )
  ).map((r) => r.variant);
}

export async function getGraphTheorems(runKey: string): Promise<string[]> {
  return (
    await query<{ theorem: string }>(
      `SELECT theorem FROM graph_nodes
       WHERE ${runFilterSql(runKey)}
       GROUP BY theorem
       HAVING count(DISTINCT CASE WHEN variant <> 'wild_type' THEN variant END) > 0
       ORDER BY theorem`,
    )
  ).map((r) => r.theorem);
}
