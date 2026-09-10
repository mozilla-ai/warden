import type { ReactNode } from "react"

export function EmptyMessage({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center justify-center px-4 py-10 text-center text-sm text-muted">{children}</div>
  )
}
