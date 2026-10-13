import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { useAuth } from '../../auth/AuthContext'
import { toFormErrors, type FormErrors } from '../../auth/formErrors'
import { safeNextPath } from '../../auth/navigation'
import { FormField } from '../../components/FormField'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({ fields: {} })
    try {
      await login(email, password)
      navigate(safeNextPath(searchParams.get('next')), { replace: true })
    } catch (error) {
      setErrors(toFormErrors(error))
      setPassword('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <h1>Log in</h1>
      {errors.general && (
        <p role="alert" className="form-alert">
          {errors.general}
        </p>
      )}
      <form onSubmit={handleSubmit} noValidate>
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
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.fields.password}
        />
        <button type="submit" className="button button-block" disabled={submitting}>
          {submitting ? 'Logging in…' : 'Log in'}
        </button>
      </form>
      <p className="auth-links">
        <Link to="/forgot-password">Forgot your password?</Link>
        <span>
          New here? <Link to="/register">Create an account</Link> or <Link to="/welcome">see what Healthfolio does</Link>
        </span>
      </p>
    </>
  )
}
