import { defineConfig } from "vite";

export default defineConfig({
  root: ".",
  base: "/dashboards/wonton-soup/",
  appType: "mpa",
  build: {
    outDir: "dist",
    target: "es2022",
  },
  optimizeDeps: {
    exclude: ["@duckdb/duckdb-wasm"],
  },
});
