import { defineConfig } from "vite";

export default defineConfig({
  root: ".",
  base: "/dashboards/wonton-soup/build/",
  build: {
    outDir: "build",
    target: "es2022",
    rollupOptions: {
      input: "src/main.ts",
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
  optimizeDeps: {
    exclude: ["@duckdb/duckdb-wasm"],
  },
});
