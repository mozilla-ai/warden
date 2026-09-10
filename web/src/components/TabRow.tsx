import type { ReactNode } from "react"

// The dashboard's own tab row: no track and no underline, the selected fill
// is the whole signal. Buttons, not a tablist, since these carry no
// roving-focus contract.
export function Tab({
  isActive,
  onPress,
  children,
}: {
  isActive: boolean
  onPress: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-pressed={isActive}
      onClick={onPress}
      className={`shrink-0 px-2.5 py-[0.3125rem] text-sm whitespace-nowrap transition-colors motion-reduce:transition-none ${
        isActive ? "bg-surface-subtle text-foreground" : "text-muted hover:text-foreground"
      }`}
    >
      {children}
    </button>
  )
}

export function TabRow({ children }: { children: ReactNode }) {
  return <div className="inline-flex max-w-full items-center gap-1 overflow-x-auto">{children}</div>
}
