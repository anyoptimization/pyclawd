/// <reference types="node" />
// Vite config — builds the SPA straight into ../web/static so the FastAPI app can
// serve it from the wheel, and proxies /api to the running backend during dev.
import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// The backend dev server (pyclawd web serve). Override with PYCLAWD_WEB_DEV_API.
const API_TARGET = process.env.PYCLAWD_WEB_DEV_API ?? "http://127.0.0.1:8801";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    // Ship into the Python package; emptied on each build.
    outDir: fileURLToPath(new URL("../web/static", import.meta.url)),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
    },
  },
});
