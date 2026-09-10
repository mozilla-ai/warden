import { Button } from "@heroui/react"
import type { ReactNode } from "react"

// For a destination the operator has never filled: says what the thing is
// and offers the one action. A filtered-empty list gets EmptyMessage instead.
export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
  children,
}: {
  title: string
  description?: string
  actionLabel?: string
  onAction?: () => void
  children?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-4 border border-border p-6">
      <div>
        <h2 className="text-heading">{title}</h2>
        {description ? <p className="mt-1 max-w-prose text-sm text-muted">{description}</p> : null}
      </div>
      {children}
      {actionLabel && onAction ? (
        <div>
          <Button variant="primary" onPress={onAction}>
            {actionLabel}
          </Button>
        </div>
      ) : null}
    </div>
  )
}
