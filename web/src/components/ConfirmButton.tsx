import { Button } from "@heroui/react"
import { type ReactNode, useState } from "react"

// Two-click confirm: the first press swaps in a danger button carrying the
// confirm label, with a cancel beside it. No modal, since these are small,
// in-row actions.
export function ConfirmButton({
  children,
  confirmLabel,
  isPending,
  onConfirm,
}: {
  children: ReactNode
  confirmLabel: string
  isPending?: boolean
  onConfirm: () => void
}) {
  const [armed, setArmed] = useState(false)
  if (!armed) {
    return (
      <Button variant="ghost" size="sm" isDisabled={isPending} onPress={() => setArmed(true)}>
        {children}
      </Button>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <Button
        variant="danger"
        size="sm"
        isPending={isPending}
        onPress={() => {
          setArmed(false)
          onConfirm()
        }}
      >
        {confirmLabel}
      </Button>
      <Button variant="ghost" size="sm" isDisabled={isPending} onPress={() => setArmed(false)}>
        Cancel
      </Button>
    </span>
  )
}
