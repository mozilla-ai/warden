import type { HTMLAttributes, ReactNode } from "react"

// A band of the page: its rules run the full width of the scroll area
// (`otari-bleed`, measured against <main>) while its content stays in the
// column. The pair is the dashboard's, so a band here lines up with one there.
export function Section({
  className = "",
  contentClassName = "",
  children,
  ...rest
}: {
  className?: string
  contentClassName?: string
  children: ReactNode
} & Omit<HTMLAttributes<HTMLElement>, "className" | "children">) {
  return (
    <section className={`otari-bleed ${className}`} {...rest}>
      <div className={`mx-auto w-full max-w-[112.5rem] px-4 md:px-6 ${contentClassName}`}>{children}</div>
    </section>
  )
}

// A section's heading row: title left, an optional action or link right.
export function SectionHeading({
  title,
  count,
  trailing,
}: {
  title: string
  count?: number
  trailing?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <h2 className="text-title">
        {title}
        {count === undefined ? null : <span className="font-normal text-subtle"> ({count})</span>}
      </h2>
      {trailing ? <div className="shrink-0">{trailing}</div> : null}
    </div>
  )
}
