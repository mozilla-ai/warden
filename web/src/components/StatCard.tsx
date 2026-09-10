import { Link } from "react-router"

export function StatCard({
  label,
  value,
  hint,
  to,
}: {
  label: string
  value: string
  hint?: string
  to?: string
}) {
  const body = (
    <>
      <span className="text-xs font-medium uppercase tracking-wide text-muted">{label}</span>
      <span className="text-3xl font-semibold text-foreground">{value}</span>
      {hint ? <span className="text-xs text-muted">{hint}</span> : null}
    </>
  )
  const className =
    "flex flex-col gap-1 rounded-lg border border-border bg-surface p-4"
  if (to) {
    return (
      <Link to={to} className={`${className} hover:bg-surface-secondary`}>
        {body}
      </Link>
    )
  }
  return <div className={className}>{body}</div>
}
