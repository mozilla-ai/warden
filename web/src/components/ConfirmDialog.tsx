import { AlertDialog, Button } from "@heroui/react"
import type { ReactNode } from "react"
import { ErrorBanner } from "./ErrorBanner"

// Every delete of a record, and any destructive action that needs a sentence
// of context. It owns the pending and error state so the page does not build
// a second error surface behind the backdrop.
export function ConfirmDialog({
  isOpen,
  onOpenChange,
  heading,
  body,
  confirmLabel,
  confirmVariant = "danger",
  isConfirmDisabled = false,
  isPending,
  error,
  onConfirm,
}: {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  heading: string
  body: ReactNode
  confirmLabel: string
  confirmVariant?: "danger" | "primary"
  isConfirmDisabled?: boolean
  isPending: boolean
  error?: unknown
  onConfirm: () => void
}) {
  return (
    <AlertDialog isOpen={isOpen} onOpenChange={onOpenChange}>
      {isOpen ? (
        <AlertDialog.Backdrop isDismissable isKeyboardDismissDisabled={false}>
          <AlertDialog.Container placement="center" size="md">
            <AlertDialog.Dialog>
              <AlertDialog.Header>
                <AlertDialog.Heading>{heading}</AlertDialog.Heading>
              </AlertDialog.Header>
              <AlertDialog.Body className="flex flex-col gap-4">
                <div className="text-sm text-muted">{body}</div>
                <ErrorBanner error={error} />
              </AlertDialog.Body>
              <AlertDialog.Footer>
                <Button variant="ghost" isDisabled={isPending} onPress={() => onOpenChange(false)}>
                  Cancel
                </Button>
                <Button
                  variant={confirmVariant}
                  isDisabled={isConfirmDisabled}
                  isPending={isPending}
                  onPress={onConfirm}
                >
                  {confirmLabel}
                </Button>
              </AlertDialog.Footer>
            </AlertDialog.Dialog>
          </AlertDialog.Container>
        </AlertDialog.Backdrop>
      ) : null}
    </AlertDialog>
  )
}
