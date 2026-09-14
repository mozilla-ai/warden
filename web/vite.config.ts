import { fileURLToPath } from "node:url"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"

// The gateway serves this bundle from the plugin's package directory at
// /plugins/warden/ui/, so the build lands inside the Python package and
// every asset URL is rooted there.
const outDir = fileURLToPath(
  new URL("../src/otari_warden/static", import.meta.url),
)

// `pnpm dev` serves only the SPA; API calls are proxied to a running gateway.
const apiTarget = process.env.OTARI_DEV_API ?? "http://localhost:8000"

// The gateway serves the dashboard's compiled stylesheet at /dashboard.css:
// tokens, fonts, HeroUI component styles. It has to come after this bundle's
// own stylesheet so the deployment's theme is what wins, and Vite appends its
// own <link> to <head> during the build, so this runs in the post phase.
const dashboardStylesheet: Plugin = {
  name: "otari-dashboard-stylesheet",
  transformIndexHtml: {
    order: "post",
    handler: () => [
      {
        tag: "link",
        attrs: { rel: "stylesheet", href: "/dashboard.css" },
        injectTo: "head",
      },
    ],
  },
}

export default defineConfig({
  base: "/plugins/warden/ui/",
  plugins: [react(), tailwindcss(), dashboardStylesheet],
  server: {
    proxy: {
      "/api/v1": { target: apiTarget, changeOrigin: true },
      "/dashboard.css": { target: apiTarget, changeOrigin: true },
      "/fonts": { target: apiTarget, changeOrigin: true },
    },
  },
  build: {
    outDir,
    emptyOutDir: true,
  },
})
