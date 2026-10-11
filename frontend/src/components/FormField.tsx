import { useId, type InputHTMLAttributes } from 'react'

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  hint?: string
  error?: string
}

/** Labelled input with hint and error text linked for screen readers (frontend_spec.md Section 17). */
export function FormField({ label, hint, error, ...inputProps }: FormFieldProps) {
  const id = useId()
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined

  return (
    <div className="form-field">
      <label htmlFor={id}>{label}</label>
      {hint && (
        <p id={hintId} className="form-hint">
          {hint}
        </p>
      )}
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={[hintId, errorId].filter(Boolean).join(' ') || undefined}
        {...inputProps}
      />
      {error && (
        <p id={errorId} className="form-error">
          {error}
        </p>
      )}
    </div>
  )
}
