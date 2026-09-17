import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * The dev server proxies the API rather than talking to it cross-origin.
 *
 * Same-origin in development means the app exercises the same request path it
 * uses in production behind nginx — no CORS preflight that exists only on a
 * developer's machine, and no API URL baked into the bundle. `npm run dev`
 * expects the pipeline on PORT_API (5696 by default, see .env).
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5697,
    strictPort: true,
    proxy: {
      "/client": { target: "http://localhost:5696", changeOrigin: true },
      "/pipeline": { target: "http://localhost:5696", changeOrigin: true },
      "/workers": { target: "http://localhost:5696", changeOrigin: true },
      "/swagger.json": { target: "http://localhost:5696", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    // The budget that matters is the gzipped size; Rollup's default warning
    // counts uncompressed bytes and flags a bundle that is fine over the wire.
    chunkSizeWarningLimit: 1000,
  },
});
