import { Chip, type ChipTone } from "./Chip"
import { formatRelative } from "../helpers/format"

// A run passed, failed, gave up, or was reported passing only because its
// judge was unreachable under on_unavailable: monitor. The last is not the
// same claim as a judge that looked and found nothing, so it is its own word.
export function runStatus({
  checked,
  compliant,
  gaveUp = false,
}: {
  checked: boolean
  compliant: boolean
  gaveUp?: boolean
}): { tone: ChipTone; label: string; title?: string } {
  if (gaveUp) {
    return {
      tone: "warning",
      label: "Gave up",
      title: "The Stop hook's retry-attempt cap was reached; the session ended without a final passing check.",
    }
  }
  if (!checked) {
    return {
      tone: "info",
      label: "Unverified",
      title: "The judge was unreachable; reported passing only because the policy's on_unavailable is monitor.",
    }
  }
  return compliant ? { tone: "success", label: "Passed" } : { tone: "danger", label: "Failed" }
}

export function RunStatusChip({
  checked,
  compliant,
  gaveUp,
  dismissedAt,
}: {
  checked: boolean
  compliant: boolean
  gaveUp?: boolean
  dismissedAt?: string | null
}) {
  const status = runStatus({ checked, compliant, gaveUp })
  const chip = (
    <Chip tone={status.tone} title={status.title}>
      {status.label}
    </Chip>
  )
  if (!dismissedAt) return chip
  return (
    <span className="inline-flex items-center gap-1.5">
      {chip}
      <Chip tone="neutral" title={`Dismissed ${formatRelative(dismissedAt)}`}>
        Dismissed
      </Chip>
    </span>
  )
}

export function GateStatusChip({ passed, skipped }: { passed: boolean; skipped: boolean }) {
  if (skipped) return <Chip tone="neutral">Skipped</Chip>
  return passed ? <Chip tone="success">Passed</Chip> : <Chip tone="danger">Failed</Chip>
}
