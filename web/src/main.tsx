import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { HashRouter } from "react-router"

import { App } from "./App"
import "./styles.css"

// Theme: an explicit ?theme=dark|light on the page URL wins (the host
// dashboard can pass it), otherwise follow the viewer's system preference.
function applyTheme(): void {
  const forced = new URLSearchParams(window.location.search).get("theme")
  const media = window.matchMedia("(prefers-color-scheme: dark)")
  const dark = forced ? forced === "dark" : media.matches
  document.documentElement.classList.toggle("dark", dark)
  if (!forced) {
    media.addEventListener("change", (event) => {
      document.documentElement.classList.toggle("dark", event.matches)
    })
  }
}
applyTheme()

const container = document.getElementById("root")
if (!container) {
  throw new Error("Root element #root not found")
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <App />
      </HashRouter>
    </QueryClientProvider>
  </StrictMode>,
)
