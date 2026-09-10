import { Description, FieldError, Input, Label, TextField } from "@heroui/react"
import type { ReactNode } from "react"

export function Field({
  label,
  value,
  onChange,
  placeholder,
  isRequired,
  isInvalid,
  errorMessage,
  description,
  autoFocus,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  isRequired?: boolean
  isInvalid?: boolean
  errorMessage?: string
  description?: ReactNode
  autoFocus?: boolean
}) {
  return (
    <TextField
      value={value}
      onChange={onChange}
      isRequired={isRequired}
      isInvalid={isInvalid}
      className="flex w-full max-w-md flex-col gap-1"
    >
      <Label className="text-sm text-foreground">{label}</Label>
      <Input placeholder={placeholder} autoFocus={autoFocus} />
      {description ? <Description className="text-xs text-muted">{description}</Description> : null}
      {errorMessage ? <FieldError className="text-xs text-danger">{errorMessage}</FieldError> : null}
    </TextField>
  )
}
