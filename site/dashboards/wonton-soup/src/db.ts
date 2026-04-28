import * as duckdb from "@duckdb/duckdb-wasm";
import duckdb_wasm from "@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url";
import mvp_worker from "@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url";
import duckdb_wasm_eh from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";
import eh_worker from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import type { Manifest, ManifestTable } from "./types";

const DATA_BASE_URL =
  import.meta.env.VITE_DATA_URL ?? "https://specterlab.org/data/wonton-soup";

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
      `SELECT DISTINCT theorem FROM mcts_tree_nodes
       WHERE run_key = '${esc(runKey)}'
       ORDER BY theorem`,
    )
  ).map((r) => r.theorem);
}

export async function getInterventions(runKey: string, theorem: string): Promise<string[]> {
  return (
    await query<{ intervention: string }>(
      `SELECT DISTINCT intervention FROM theorem_intervention
       WHERE run_key = '${esc(runKey)}' AND theorem = '${esc(theorem)}'
       ORDER BY intervention`,
    )
  ).map((r) => r.intervention);
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
       WHERE run_key = '${esc(runKey)}' AND theorem = '${esc(theorem)}'
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
       WHERE run_key = '${esc(runKey)}' AND theorem = '${esc(theorem)}'
       ORDER BY variant`,
    )
  ).map((r) => r.variant);
}

export async function getGraphTheorems(runKey: string): Promise<string[]> {
  return (
    await query<{ theorem: string }>(
      `SELECT DISTINCT theorem FROM graph_nodes
       WHERE run_key = '${esc(runKey)}'
       ORDER BY theorem`,
    )
  ).map((r) => r.theorem);
}
