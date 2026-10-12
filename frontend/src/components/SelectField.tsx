import { useId, type SelectHTMLAttributes } from 'react'

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  options: { value: string; label: string }[]
  error?: string
}

export function SelectField({ label, options, error, 'aria-describedby': describedBy, ...selectProps }: SelectFieldProps) {
  const id = useId()
  const errorId = error ? `${id}-error` : undefined
  // The error and any extra description (e.g. a note under the field) are both announced.
  const descriptionIds = [errorId, describedBy].filter(Boolean).join(' ') || undefined

  return (
    <div className="form-field">
      <label htmlFor={id}>{label}</label>
      <select id={id} aria-invalid={error ? true : undefined} aria-describedby={descriptionIds} {...selectProps}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error && (
        <p id={errorId} className="form-error">
          {error}
        </p>
      )}
    </div>
  )
}
