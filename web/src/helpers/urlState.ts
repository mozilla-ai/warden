import { useSearchParams } from "react-router"

// Filters and paging live in the hash route's search params so a view is
// linkable from the group pages and survives a reload.
export function useUrlState<const D extends Record<string, string>>(defaults: D) {
  const [params, setParams] = useSearchParams()

  function get(key: keyof D & string): string {
    return params.get(key) ?? defaults[key]
  }

  function getNumber(key: keyof D & string): number {
    const parsed = Number.parseInt(get(key), 10)
    return Number.isNaN(parsed) ? Number.parseInt(defaults[key], 10) : parsed
  }

  function patch(updates: Partial<Record<keyof D & string, string | number>>): void {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(updates)) {
      const text = value === undefined ? "" : String(value)
      if (text === "" || text === defaults[key]) {
        next.delete(key)
      } else {
        next.set(key, text)
      }
    }
    setParams(next, { replace: true })
  }

  return { get, getNumber, patch }
}
