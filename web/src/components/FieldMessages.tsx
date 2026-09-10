import type { ReactNode } from "react"

// The line under a control, reserved by default so an error can replace a
// description without moving what is below it.
export function FieldMessages({ children, reserve = true }: { children: ReactNode; reserve?: boolean }) {
  return (
    <div className={`text-caption ${reserve ? "min-h-[var(--text-caption-step--line-height)]" : ""}`}>
      {children}
    </div>
  )
}
