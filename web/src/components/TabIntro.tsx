import type { ReactNode } from "react"

// The opening row of a tab: the dashboard's PageIntro without the title,
// since the tab above already names the surface and the dashboard's own
// heading sits over the frame. The sentence and the action keep their places.
export function TabIntro({ action, children }: { action?: ReactNode; children: ReactNode }) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <p className="max-w-[38.75rem] text-sm text-muted">{children}</p>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  )
}
