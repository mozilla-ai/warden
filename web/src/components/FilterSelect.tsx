import { Label, ListBox, ListBoxItem, Select } from "@heroui/react"

// Keys carry a prefix so an empty string ("all") is a real key.
const PREFIX = "v:"
const optionKey = (value: string) => `${PREFIX}${value}`
const optionValue = (key: string) => key.slice(PREFIX.length)

export function FilterSelect({
  id,
  label,
  ariaLabel,
  value,
  onChange,
  options,
  disabled,
}: {
  id?: string
  label?: string
  ariaLabel?: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  disabled?: boolean
}) {
  // A value that arrived by URL and is not among the options still shows.
  const items = options.some((option) => option.value === value)
    ? options
    : [{ value, label: value }, ...options]
  return (
    <Select.Root
      aria-label={label ? undefined : ariaLabel}
      isDisabled={disabled}
      selectedKey={optionKey(value)}
      onSelectionChange={(key) => {
        if (key != null) onChange(optionValue(String(key)))
      }}
    >
      {label ? <Label className="text-caption">{label}</Label> : null}
      <Select.Trigger id={id}>
        <Select.Value />
        <Select.Indicator />
      </Select.Trigger>
      <Select.Popover>
        <ListBox items={items} className="max-h-72 overflow-auto">
          {(option: { value: string; label: string }) => (
            <ListBoxItem id={optionKey(option.value)} textValue={option.label}>
              {option.label}
            </ListBoxItem>
          )}
        </ListBox>
      </Select.Popover>
    </Select.Root>
  )
}
