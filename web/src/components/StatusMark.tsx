import { FiCheckCircle, FiMinusCircle, FiXCircle } from "react-icons/fi"

export type MarkState = "success" | "failure" | "neutral"

const ICONS = {
  success: FiCheckCircle,
  failure: FiXCircle,
  neutral: FiMinusCircle,
}
const COLORS = {
  success: "text-success",
  failure: "text-danger",
  neutral: "text-warning",
}

export function StatusMark({
  state,
  label,
  title,
}: {
  state: MarkState
  label: string
  title?: string
}) {
  const Icon = ICONS[state]
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 font-medium ${COLORS[state]}`}
    >
      <Icon aria-hidden className="h-4 w-4 shrink-0" />
      {label}
    </span>
  )
}

// A run passed, failed, or was reported passing only because its judge was
// unreachable under on_unavailable: monitor. The third is not the same claim
// as a judge that looked and found nothing, so it gets its own mark.
export function RunStatusMark({ checked, compliant }: { checked: boolean; compliant: boolean }) {
  if (!checked) {
    return (
      <StatusMark
        state="neutral"
        label="Unverified"
        title="The judge was unreachable; reported passing only because the policy's on_unavailable is monitor."
      />
    )
  }
  return (
    <StatusMark state={compliant ? "success" : "failure"} label={compliant ? "Passed" : "Failed"} />
  )
}
