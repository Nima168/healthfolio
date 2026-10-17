import { useId, type SelectHTMLAttributes } from 'react'

interface SelectOption {
  value: string
  label: string
  /** Options next to each other with the same group are shown under that heading. */
  group?: string
}

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  options: SelectOption[]
  error?: string
}

function grouped(options: SelectOption[]): { group?: string; options: SelectOption[] }[] {
  const runs: { group?: string; options: SelectOption[] }[] = []
  for (const option of options) {
    const last = runs.at(-1)
    if (last && option.group && last.group === option.group) last.options.push(option)
    else runs.push({ group: option.group, options: [option] })
  }
  return runs
}

export function SelectField({ label, options, error, 'aria-describedby': describedBy, ...selectProps }: SelectFieldProps) {
  const id = useId()
  const errorId = error ? `${id}-error` : undefined
  // The error and any extra description (e.g. a note under the field) are both announced.
  const descriptionIds = [errorId, describedBy].filter(Boolean).join(' ') || undefined
  const render = (option: SelectOption) => (
    <option key={option.value} value={option.value}>
      {option.label}
    </option>
  )

  return (
    <div className="form-field">
      <label htmlFor={id}>{label}</label>
      <select id={id} aria-invalid={error ? true : undefined} aria-describedby={descriptionIds} {...selectProps}>
        {grouped(options).map((run) =>
          run.group ? (
            <optgroup key={run.group} label={run.group}>
              {run.options.map(render)}
            </optgroup>
          ) : (
            run.options.map(render)
          ),
        )}
      </select>
      {error && (
        <p id={errorId} className="form-error">
          {error}
        </p>
      )}
    </div>
  )
}
