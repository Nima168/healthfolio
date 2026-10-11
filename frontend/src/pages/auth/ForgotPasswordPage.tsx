import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { authApi } from '../../auth/authApi'
import { toFormErrors, type FormErrors } from '../../auth/formErrors'
import { FormField } from '../../components/FormField'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null)
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({ fields: {} })
    try {
      // The backend answers the same way whether or not the account exists.
      await authApi.forgotPassword(email)
      setSubmittedEmail(email.trim())
    } catch (error) {
      setErrors(toFormErrors(error))
    } finally {
      setSubmitting(false)
    }
  }

  if (submittedEmail) {
    // Shown for every address, so the page never reveals whether an account exists.
    return (
      <>
        <h1>Check your email</h1>
        <p role="status">
          If <strong>{submittedEmail}</strong> has an account, you'll receive a reset link within a few minutes.
        </p>
        <p>Check the address is correct — no email is sent if there's no account.</p>
        <p>The link is valid for 30 minutes and can be used once.</p>
        <p className="auth-links">
          <button type="button" className="link-button" onClick={() => setSubmittedEmail(null)}>
            Use a different email
          </button>
          <Link to="/login">Back to log in</Link>
        </p>
      </>
    )
  }

  return (
    <>
      <h1>Reset your password</h1>
      <p className="page-intro">Enter your email and we'll send you a link to choose a new password.</p>
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
        <button type="submit" className="button button-block" disabled={submitting}>
          {submitting ? 'Sending…' : 'Send reset link'}
        </button>
      </form>
      <p className="auth-links">
        <Link to="/login">Back to log in</Link>
      </p>
    </>
  )
}
