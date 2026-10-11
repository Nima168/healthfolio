import { useId, type SelectHTMLAttributes } from 'react'

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  options: { value: string; label: string }[]
  error?: string
}

export function SelectField({ label, options, error, ...selectProps }: SelectFieldProps) {
  const id = useId()
  const errorId = error ? `${id}-error` : undefined

  return (
    <div className="form-field">
      <label htmlFor={id}>{label}</label>
      <select id={id} aria-invalid={error ? true : undefined} aria-describedby={errorId} {...selectProps}>
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
