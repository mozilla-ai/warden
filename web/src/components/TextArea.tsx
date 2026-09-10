import { Description, FieldError, TextArea as HeroTextArea, Label, TextField } from "@heroui/react"
import type { ReactNode } from "react"
import { FieldMessages } from "./FieldMessages"

export function TextArea({
  label,
  value,
  onChange,
  onBlur,
  placeholder,
  rows = 4,
  description,
  isRequired,
  isInvalid,
  errorMessage,
  reserveMessage,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
  placeholder?: string
  rows?: number
  description?: ReactNode
  isRequired?: boolean
  isInvalid?: boolean
  errorMessage?: string
  reserveMessage?: boolean
}) {
  return (
    <TextField
      value={value}
      onChange={onChange}
      onBlur={onBlur}
      isRequired={isRequired}
      isInvalid={isInvalid}
      className="flex flex-col gap-1"
    >
      <Label className="text-body">{label}</Label>
      <HeroTextArea rows={rows} placeholder={placeholder} />
      <FieldMessages reserve={reserveMessage}>
        {description ? <Description className="text-muted">{description}</Description> : null}
        {errorMessage ? <FieldError className="text-danger">{errorMessage}</FieldError> : null}
      </FieldMessages>
    </TextField>
  )
}
