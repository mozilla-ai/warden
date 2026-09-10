import { Description, Select as HeroSelect, Label, ListBox, ListBoxItem } from "@heroui/react"
import type { ReactNode } from "react"
import { FieldMessages } from "./FieldMessages"

export interface SelectOption {
  value: string
  label: string
}

const PREFIX = "v:"
const optionKey = (value: string) => `${PREFIX}${value}`
const optionValue = (key: string) => key.slice(PREFIX.length)

// A labeled select for a form, as opposed to FilterSelect above a table.
export function Select({
  label,
  value,
  onChange,
  options,
  description,
  isRequired,
  isDisabled,
  reserveMessage,
  className = "",
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: readonly SelectOption[]
  description?: ReactNode
  isRequired?: boolean
  isDisabled?: boolean
  reserveMessage?: boolean
  className?: string
}) {
  return (
    <HeroSelect.Root
      selectedKey={optionKey(value)}
      isRequired={isRequired}
      isDisabled={isDisabled}
      onSelectionChange={(key) => {
        if (key != null) onChange(optionValue(String(key)))
      }}
      className={`flex flex-col gap-1 ${className}`}
    >
      <Label className="text-body">{label}</Label>
      <HeroSelect.Trigger>
        <HeroSelect.Value />
        <HeroSelect.Indicator />
      </HeroSelect.Trigger>
      <HeroSelect.Popover>
        <ListBox items={options} className="max-h-72 overflow-auto">
          {(option: SelectOption) => (
            <ListBoxItem id={optionKey(option.value)} textValue={option.label}>
              {option.label}
            </ListBoxItem>
          )}
        </ListBox>
      </HeroSelect.Popover>
      <FieldMessages reserve={reserveMessage}>
        {description ? <Description className="text-muted">{description}</Description> : null}
      </FieldMessages>
    </HeroSelect.Root>
  )
}
