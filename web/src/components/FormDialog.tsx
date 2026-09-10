import { Button, Modal, Spinner } from "@heroui/react"
import { type ReactNode, useEffect, useRef, useState } from "react"
import { FiX } from "react-icons/fi"
import { ErrorBanner } from "./ErrorBanner"

export type FormDialogSize = "sm" | "md" | "lg"

// The dashboard's create-and-edit surface. Its width comes from the
// `otari-form-dialog--*` rules the dashboard stylesheet carries.
export function FormDialog({
  isOpen,
  onOpenChange,
  title,
  description,
  size = "md",
  submitLabel,
  onSubmit,
  isPending,
  error,
  isDirty = false,
  children,
}: {
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
  title: string
  description?: ReactNode
  size?: FormDialogSize
  submitLabel: string
  onSubmit: () => void
  isPending: boolean
  error?: unknown
  isDirty?: boolean
  children: ReactNode
}) {
  const [isGuarding, setIsGuarding] = useState(false)
  const [isScrolled, setIsScrolled] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!isOpen) {
      setIsGuarding(false)
      setIsScrolled(false)
    }
  }, [isOpen])
  useEffect(() => {
    if (error == null) return
    if (bodyRef.current) bodyRef.current.scrollTop = 0
    setIsScrolled(false)
  }, [error])

  const requestClose = () => {
    if (isPending) return
    if (isDirty) {
      setIsGuarding(true)
      return
    }
    onOpenChange(false)
  }

  return (
    <Modal
      isOpen={isOpen}
      onOpenChange={(next) => {
        if (next) {
          onOpenChange(true)
          return
        }
        requestClose()
      }}
    >
      {/* Driven from state, so the trigger slot is hidden rather than absent. */}
      <Modal.Trigger className="hidden">{submitLabel}</Modal.Trigger>
      <Modal.Backdrop isDismissable={!isPending}>
        <Modal.Container placement="top" className="p-0 sm:px-4 sm:pt-[7.5rem] sm:pb-[7.5rem]">
          <Modal.Dialog className={`otari-form-dialog otari-form-dialog--${size} flex flex-col p-0`}>
            <header
              className={`flex shrink-0 items-start justify-between gap-4 px-6 pt-5 pb-4 ${
                isScrolled ? "border-border border-b" : ""
              }`}
            >
              <div className="flex flex-col gap-1">
                <Modal.Heading className="text-heading">{title}</Modal.Heading>
                {description ? <p className="text-body text-muted">{description}</p> : null}
              </div>
              <Button
                aria-label="Close"
                variant="ghost"
                isIconOnly
                size="sm"
                className="relative -top-1 shrink-0 before:absolute before:-inset-1.5 before:content-['']"
                isDisabled={isPending}
                onPress={requestClose}
              >
                <FiX aria-hidden className="size-3.5 text-muted" />
              </Button>
            </header>
            <form
              onSubmit={(event) => {
                event.preventDefault()
                if (!isPending && !isGuarding) onSubmit()
              }}
              onKeyDown={(event) => {
                if (event.key !== "Enter") return
                if (!event.metaKey && !event.ctrlKey) return
                event.preventDefault()
                if (!isPending && !isGuarding) event.currentTarget.requestSubmit()
              }}
              aria-busy={isPending}
              className="flex min-h-0 flex-col"
            >
              <div
                ref={bodyRef}
                onScroll={(event) => setIsScrolled(event.currentTarget.scrollTop > 0)}
                className="flex min-h-0 flex-col gap-4 overflow-y-auto px-6 pt-1 pb-6"
              >
                <ErrorBanner error={error} />
                {children}
              </div>
              <footer className="border-border flex shrink-0 items-center justify-between gap-2 border-t px-6 py-3">
                {isGuarding ? (
                  <>
                    <p className="text-caption">Unsaved changes</p>
                    <div className="flex items-center gap-2">
                      <Button variant="ghost" onPress={() => setIsGuarding(false)}>
                        Keep editing
                      </Button>
                      <Button
                        variant="danger"
                        onPress={() => {
                          setIsGuarding(false)
                          onOpenChange(false)
                        }}
                      >
                        Discard
                      </Button>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="min-w-0" />
                    <div className="flex shrink-0 items-center gap-2">
                      <Button variant="ghost" isDisabled={isPending} onPress={requestClose}>
                        Cancel
                      </Button>
                      {/* Working, not refused: the fill stays and the press is
                          blocked by hand, with the spinner replacing the label
                          in place so the footer keeps its height. */}
                      <Button
                        type="submit"
                        variant="primary"
                        className={`relative ${isPending ? "pointer-events-none" : ""}`}
                      >
                        <span className={isPending ? "opacity-0" : undefined}>{submitLabel}</span>
                        {isPending ? (
                          <span className="absolute inset-0 flex items-center justify-center">
                            <Spinner size="sm" color="current" aria-hidden="true" />
                          </span>
                        ) : null}
                      </Button>
                    </div>
                  </>
                )}
              </footer>
            </form>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </Modal>
  )
}
