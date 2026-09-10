// The dashboard sets its theme on its own <html> (`data-theme`, the `dark`
// class, and an inline color-scheme) and this page is framed by it on the same
// origin, so the frame reads those straight off the parent document and keeps
// them in step. Opened in its own tab there is no parent to read, and the page
// follows the viewer's system preference instead.

const DARK_QUERY = "(prefers-color-scheme: dark)"

function apply(resolved: "light" | "dark"): void {
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
    // A cross-origin parent throws on access; there is nothing to mirror.
    return null
  }
}

function readHost(root: HTMLElement): "light" | "dark" {
  const attr = root.getAttribute("data-theme")
  if (attr === "dark" || root.classList.contains("dark")) return "dark"
  if (attr === "light") return "light"
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light"
}

export function mirrorHostTheme(): void {
  const host = hostRoot()
  if (host) {
    apply(readHost(host))
    new MutationObserver(() => apply(readHost(host))).observe(host, {
      attributes: true,
      attributeFilter: ["data-theme", "class"],
    })
    return
  }
  const media = window.matchMedia(DARK_QUERY)
  apply(media.matches ? "dark" : "light")
  media.addEventListener("change", (event) => apply(event.matches ? "dark" : "light"))
}
