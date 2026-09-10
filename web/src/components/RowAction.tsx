import type { ReactNode } from "react"

// An action inside a table row: a caption-weight text button, not a Button.
export function RowAction({
  onPress,
  isDanger,
  isDisabled,
  ariaLabel,
  children,
}: {
  onPress: () => void
  isDanger?: boolean
  isDisabled?: boolean
  ariaLabel?: string
  children: ReactNode
}) {
  return (
    <button
      type="button"
      disabled={isDisabled}
      aria-label={ariaLabel}
      onClick={onPress}
      className={`text-caption whitespace-nowrap transition-colors motion-reduce:transition-none disabled:opacity-(--disabled-opacity) ${
        isDanger ? "text-danger" : "hover:text-foreground"
      }`}
    >
      {children}
    </button>
  )
}

export function RowActionRow({ children }: { children: ReactNode }) {
  return <div className="flex items-center justify-end gap-4">{children}</div>
}
