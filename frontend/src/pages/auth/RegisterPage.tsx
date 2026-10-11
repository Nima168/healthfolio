import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuth } from '../../auth/AuthContext'
import { PASSWORD_HINT, PASSWORD_MIN_LENGTH } from '../../auth/authApi'
import { toFormErrors, type FormErrors } from '../../auth/formErrors'
import { FormField } from '../../components/FormField'

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    // Quick client-side checks for fast feedback; the backend remains the authority.
    const fields: Record<string, string> = {}
    if (password.length < PASSWORD_MIN_LENGTH) fields.password = `Password must be at least ${PASSWORD_MIN_LENGTH} characters.`
    if (confirm !== password) fields.confirm = 'Passwords do not match.'
    if (Object.keys(fields).length > 0) {
      setErrors({ fields })
      return
    }

    setSubmitting(true)
    setErrors({ fields: {} })
    try {
      await register(email, password, displayName.trim() || undefined)
      navigate('/', { replace: true })
    } catch (error) {
      setErrors(toFormErrors(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <h1>Create your account</h1>
      {errors.general && (
        <p role="alert" className="form-alert">
          {errors.general}
        </p>
      )}
      <form onSubmit={handleSubmit} noValidate>
        <FormField
          label="Name (optional)"
          autoComplete="name"
          maxLength={100}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          error={errors.fields.display_name}
        />
        <FormField
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.fields.email}
        />
        <FormField
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          hint={PASSWORD_HINT}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.fields.password}
        />
        <FormField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.fields.confirm}
        />
        <button type="submit" className="button button-block" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <p className="auth-links">
        <span>
          Already have an account? <Link to="/login">Log in</Link>
        </span>
      </p>
    </>
  )
}
