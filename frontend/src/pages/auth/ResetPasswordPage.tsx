import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { authApi, PASSWORD_HINT, PASSWORD_MIN_LENGTH } from '../../auth/authApi'
import { useAuth } from '../../auth/AuthContext'
import { toFormErrors, type FormErrors } from '../../auth/formErrors'
import { FormField } from '../../components/FormField'

/** The token arrives in the URL fragment (#token=…), which browsers never send to servers. */
function tokenFromHash(hash: string): string | null {
  return new URLSearchParams(hash.replace(/^#/, '')).get('token')
}

export function ResetPasswordPage() {
  const { status, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  // Read once on first render; the fragment is removed from the address bar right after.
  const [token] = useState(() => tokenFromHash(location.hash))
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (location.hash) navigate(location.pathname, { replace: true })
  }, [location.hash, location.pathname, navigate])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const fields: Record<string, string> = {}
    if (password.length < PASSWORD_MIN_LENGTH) fields.new_password = `Password must be at least ${PASSWORD_MIN_LENGTH} characters.`
    if (confirm !== password) fields.confirm = 'Passwords do not match.'
    if (Object.keys(fields).length > 0) {
      setErrors({ fields })
      return
    }

    setSubmitting(true)
    setErrors({ fields: {} })
    try {
      await authApi.resetPassword(token ?? '', password)
      // The reset ends every session, including this browser's.
      if (status === 'authenticated') await logout()
      setDone(true)
    } catch (error) {
      setErrors(toFormErrors(error))
    } finally {
      setSubmitting(false)
    }
  }

  if (!token) {
    return (
      <>
        <h1>Reset link missing</h1>
        <p>This page needs the link from your password reset email. Request a new link if it has expired.</p>
        <p className="auth-links">
          <Link to="/forgot-password">Request a new link</Link>
        </p>
      </>
    )
  }

  if (done) {
    return (
      <>
        <h1>Password changed</h1>
        <p role="status">Your password has been changed and you have been logged out everywhere.</p>
        <p className="auth-links">
          <Link to="/login">Log in with your new password</Link>
        </p>
      </>
    )
  }

  return (
    <>
      <h1>Choose a new password</h1>
      {errors.general && (
        <p role="alert" className="form-alert">
          {errors.general}{' '}
          {errors.general.includes('expired') && <Link to="/forgot-password">Request a new link</Link>}
        </p>
      )}
      <form onSubmit={handleSubmit} noValidate>
        <FormField
          label="New password"
          type="password"
          autoComplete="new-password"
          required
          hint={PASSWORD_HINT}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.fields.new_password}
        />
        <FormField
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.fields.confirm}
        />
        <button type="submit" className="button button-block" disabled={submitting}>
          {submitting ? 'Saving…' : 'Change password'}
        </button>
      </form>
    </>
  )
}
