import { useId } from "react"

// A closed set of alternatives to one value. Native radios underneath, so the
// semantics come free; the track is what says there are no other options.
export function Segmented({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { value: string; label: string }[]
  value: string
  onChange: (next: string) => void
}) {
  const name = useId()
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex w-fit max-w-full overflow-x-auto border border-control-border"
    >
      {options.map((option) => {
        const selected = option.value === value
        return (
          <label
            key={option.value}
            className={`shrink-0 cursor-pointer border-l border-control-border px-3 py-[0.3125rem] text-sm whitespace-nowrap transition-colors first:border-l-0 has-[:focus-visible]:otari-focus-ring motion-reduce:transition-none ${
              selected ? "bg-surface-subtle text-foreground" : "text-muted hover:text-foreground"
            }`}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={selected}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            {option.label}
          </label>
        )
      })}
    </div>
  )
}
