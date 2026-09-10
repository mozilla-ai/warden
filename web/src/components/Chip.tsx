import type { ReactNode } from "react"

export type ChipTone = "neutral" | "accent" | "success" | "warning" | "danger" | "info"

const TONE: Record<ChipTone, string> = {
  neutral: "bg-surface-subtle text-muted",
  accent: "bg-primary-subtle text-primary-subtle-foreground",
  success: "bg-success-subtle text-success",
  warning: "bg-warning-subtle text-warning",
  danger: "bg-danger-subtle text-danger",
  info: "bg-info-subtle text-info",
}

export function Chip({
  tone = "neutral",
  className = "",
  title,
  children,
}: {
  tone?: ChipTone
  className?: string
  title?: string
  children: ReactNode
}) {
  return (
    <span
      title={title}
      className={`inline-flex w-fit shrink-0 items-center gap-1 whitespace-nowrap px-1.5 py-0.5 text-xs ${TONE[tone]} ${className}`}
    >
      {children}
    </span>
  )
}
