// The dashboard frames this page and tells it the theme over postMessage
// ({type: "otari:theme", theme}) on load and on every change; that is the
// contract in Otari's docs/plugins.md. An older dashboard that frames without
// speaking is same-origin, so its <html> (`data-theme`, the `dark` class) can
// still be read and watched. Opened in its own tab there is no parent at all,
// and the page follows the viewer's system preference.

const DARK_QUERY = "(prefers-color-scheme: dark)"
const THEME_MESSAGE = "otari:theme"

type Theme = "light" | "dark"

function apply(resolved: Theme): void {
  const root = document.documentElement
  root.setAttribute("data-theme", resolved)
  root.classList.toggle("dark", resolved === "dark")
  root.style.colorScheme = resolved
}

function hostRoot(): HTMLElement | null {
  try {
    if (window.parent === window) return null
    return window.parent.document.documentElement
  } catch {
    // A cross-origin parent throws on access; there is nothing to read.
    return null
  }
}

function readHost(root: HTMLElement): Theme {
  const attr = root.getAttribute("data-theme")
  if (attr === "dark" || root.classList.contains("dark")) return "dark"
  if (attr === "light") return "light"
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light"
}

function listenToHost(): void {
  window.addEventListener("message", (event: MessageEvent) => {
    if (event.origin !== window.location.origin || event.source !== window.parent) return
    const data: unknown = event.data
    if (typeof data !== "object" || data === null) return
    const message = data as { type?: unknown; theme?: unknown }
    if (message.type !== THEME_MESSAGE) return
    if (message.theme === "dark" || message.theme === "light") apply(message.theme)
  })
}

export function mirrorHostTheme(): void {
  const host = hostRoot()
  if (host) {
    listenToHost()
    apply(readHost(host))
    new MutationObserver(() => apply(readHost(host))).observe(host, {
      attributes: true,
      attributeFilter: ["data-theme", "class"],
    })
    return
  }
  if (window.parent !== window) {
    // Framed by something this page cannot read: the message is all there is.
    listenToHost()
  }
  const media = window.matchMedia(DARK_QUERY)
  apply(media.matches ? "dark" : "light")
  media.addEventListener("change", (event) => apply(event.matches ? "dark" : "light"))
}

/** Ask the dashboard to move, for a link that leaves this page (a usage row, a key). */
export function navigateHost(to: string): void {
  if (window.parent === window) return
  window.parent.postMessage({ type: "otari:navigate", to }, window.location.origin)
}

/** Show a notice in the dashboard, above the frame. */
export function notifyHost(title: string, description?: string, variant: "success" | "danger" = "success"): void {
  if (window.parent === window) return
  window.parent.postMessage({ type: "otari:toast", title, description, variant }, window.location.origin)
}
