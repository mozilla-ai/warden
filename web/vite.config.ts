import { fileURLToPath } from "node:url"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// The gateway serves this bundle from the plugin's package directory at
// /plugins/agent-gates/ui/, so the build lands inside the Python package and
// every asset URL is rooted there.
const outDir = fileURLToPath(
  new URL("../src/otari_agent_gates/static", import.meta.url),
)

// `pnpm dev` serves only the SPA; API calls are proxied to a running gateway.
const apiTarget = process.env.OTARI_DEV_API ?? "http://localhost:8000"

export default defineConfig({
  base: "/plugins/agent-gates/ui/",
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api/v1": { target: apiTarget, changeOrigin: true },
    },
  },
  build: {
    outDir,
    emptyOutDir: true,
  },
})
