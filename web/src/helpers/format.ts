export function formatCost(value: number | null | undefined): string {
  const amount = value ?? 0
  const digits = amount !== 0 && Math.abs(amount) < 1 ? 4 : 2
  return `$${amount.toFixed(digits)}`
}

export function formatTokens(value: number | null | undefined): string {
  const count = value ?? 0
  if (Math.abs(count) >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`
  if (Math.abs(count) >= 1_000) return `${(count / 1_000).toFixed(1)}k`
  return String(count)
}

export function formatPct(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`
}

// null means "nothing in this run reported usage", a different fact than
// zero cost, so it is shown as a dash rather than $0.00.
export function formatOptionalCost(value: number | null | undefined): string {
  return value == null ? "—" : formatCost(value)
}

export function formatOptionalTokens(value: number | null | undefined): string {
  return value == null ? "—" : formatTokens(value)
}

export function formatRelative(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "never"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const seconds = Math.round((now - date.getTime()) / 1000)
  const future = seconds < 0
  const abs = Math.abs(seconds)
  const units: [number, string][] = [
    [60, "second"],
    [60, "minute"],
    [24, "hour"],
    [7, "day"],
    [4.35, "week"],
    [12, "month"],
  ]
  let value = abs
  let unit = "second"
  for (const [size, name] of units) {
    unit = name
    if (value < size) break
    value = value / size
  }
  if (value >= 12 && unit === "month") {
    value = value / 12
    unit = "year"
  }
  const rounded = Math.floor(value)
  if (unit === "second" && rounded < 10) return "just now"
  const label = `${rounded} ${unit}${rounded === 1 ? "" : "s"}`
  return future ? `in ${label}` : `${label} ago`
}
