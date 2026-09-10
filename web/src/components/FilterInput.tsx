import { Input, Label, TextField } from "@heroui/react"

// A free-text filter above a table, labeled like FilterSelect beside it.
export function FilterInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
}) {
  return (
    <TextField value={value} onChange={onChange} className="flex w-48 flex-col gap-1">
      <Label className="text-caption">{label}</Label>
      <Input placeholder={placeholder} />
    </TextField>
  )
}
