import type { ReactNode } from "react"
import { Section } from "./Section"

// The dashboard's metrics band: ruled above and below, cells divided by a
// hairline, an overline label over a mono figure over one meta line.
export function KpiStrip({ children }: { children: ReactNode }) {
  return (
    <Section className="border-y border-border" contentClassName="grid grid-cols-1 sm:grid-cols-3">
      {children}
    </Section>
  )
}

export function KpiCell({ label, value, subline }: { label: string; value: string; subline: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 border-border px-7 py-[1.125rem] max-sm:not-last:border-b sm:not-last:border-r">
      <span className="text-overline">{label}</span>
      <span className="text-mono-figure font-normal text-foreground">{value}</span>
      <span className="min-h-[1.125rem] truncate text-xs text-muted" title={subline}>
        {subline}
      </span>
    </div>
  )
}
