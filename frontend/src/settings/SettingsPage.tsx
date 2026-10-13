import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { authApi, PASSWORD_HINT, PASSWORD_MIN_LENGTH } from '../auth/authApi'
import { toFormErrors, type FormErrors } from '../auth/formErrors'
import { FormField } from '../components/FormField'
import { HelperNote } from '../components/HelperNote'
import { formatTimestamp } from '../documents/format'
import { accountApi, EXPORTS, type ExportKind } from './accountApi'

const CONFIRM_WORD = 'DELETE'

function ChangePassword() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [saving, setSaving] = useState(false)
  const [done, setDone] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setDone(false)
    const missing: FormErrors = { fields: {} }
    if (!current) missing.fields.current_password = 'Enter your current password.'
    if (next.length < PASSWORD_MIN_LENGTH) missing.fields.new_password = PASSWORD_HINT
    if (next !== confirm) missing.fields.confirm = 'The new passwords do not match.'
    if (Object.keys(missing.fields).length) return setErrors(missing)

    setSaving(true)
    try {
      await authApi.changePassword(current, next)
      setErrors({ fields: {} })
      setCurrent('')
      setNext('')
      setConfirm('')
      setDone(true)
    } catch (error) {
      setErrors(toFormErrors(error, 'Your password could not be changed.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate aria-label="Change password" className="settings-form">
      <h3>Change password</h3>
      {errors.general && (
        <p role="alert" className="form-alert">
          {errors.general}
        </p>
      )}
      <FormField
        label="Current password"
        type="password"
        autoComplete="current-password"
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        error={errors.fields.current_password}
      />
      <FormField
        label="New password"
        type="password"
        autoComplete="new-password"
        hint={PASSWORD_HINT}
        value={next}
        onChange={(e) => setNext(e.target.value)}
        error={errors.fields.new_password}
      />
      <FormField
        label="Confirm new password"
        type="password"
        autoComplete="new-password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        error={errors.fields.confirm}
      />
      <button type="submit" className="button" disabled={saving}>
        {saving ? 'Saving…' : 'Change password'}
      </button>
      {done && (
        <p role="status" className="form-success">
          Password changed. Other devices have been signed out; this one stays signed in.
        </p>
      )}
    </form>
  )
}

function Exports() {
  const [busy, setBusy] = useState<ExportKind | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  async function download(kind: ExportKind, label: string, filename: string) {
    setBusy(kind)
    setMessage(null)
    try {
      const url = URL.createObjectURL(await accountApi.export(kind))
      const link = window.document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setMessage({ ok: true, text: `${label} downloaded.` })
    } catch (error) {
      setMessage({ ok: false, text: toFormErrors(error, `${label} could not be prepared. Please try again.`).general ?? '' })
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="card" aria-labelledby="export-title">
      <h2 id="export-title">Export your data</h2>
      <p>
        Only your own records are included. Values read from documents are as read and not checked by a clinician.
        Each file is prepared when you click and downloaded straight to this device; nothing is kept on the server.
      </p>
      <ul className="export-list">
        {EXPORTS.map((item) => (
          <li key={item.kind}>
            <div>
              <strong>{item.label}</strong>
              <p className="document-meta">{item.description}</p>
            </div>
            <button
              type="button"
              className="button button-small button-secondary"
              onClick={() => void download(item.kind, item.label, item.filename)}
              disabled={busy !== null}
            >
              {busy === item.kind ? 'Preparing…' : 'Download'}
            </button>
          </li>
        ))}
      </ul>
      <div aria-live="polite">
        {message && (
          <p role={message.ok ? 'status' : 'alert'} className={message.ok ? 'form-success' : 'form-alert'}>
            {message.text}
          </p>
        )}
      </div>
      <p className="document-meta">
        Downloaded files are no longer protected by this app: keep them somewhere safe, and delete them from shared
        computers.
      </p>
    </section>
  )
}

function DeleteAccount() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [word, setWord] = useState('')
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [deleting, setDeleting] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const missing: FormErrors = { fields: {} }
    if (!password) missing.fields.current_password = 'Enter your password.'
    if (word.trim() !== CONFIRM_WORD) missing.fields.confirmation = `Type ${CONFIRM_WORD} to confirm.`
    if (Object.keys(missing.fields).length) return setErrors(missing)

    setDeleting(true)
    try {
      await authApi.deleteAccount(password, word)
      // The next page ends the session once it is showing, so the sign-in guard does not send us to login first.
      navigate('/account-deleted', { replace: true })
    } catch (error) {
      setErrors(toFormErrors(error, 'Your account could not be deleted. Please try again.'))
      setDeleting(false)
    }
  }

  return (
    <section className="card danger-zone" aria-labelledby="delete-title">
      <h2 id="delete-title">Delete account</h2>
      <p>Deleting your account is permanent and cannot be undone. It removes:</p>
      <ul>
        <li>every document you uploaded, and the files themselves;</li>
        <li>everything read from them, your medicines, follow-ups, alerts, Health Profile, vital signs, and AI summaries;</li>
        <li>your sign-in: you are signed out on every device.</li>
      </ul>
      <p>
        Download an export first if you want to keep anything. A short security log of past sign-ins and changes is
        kept for 90 days without your name, email, or health information. Database backups may still hold your data
        until they expire, within 30 days.
      </p>
      {!open ? (
        <button type="button" className="button button-danger" onClick={() => setOpen(true)}>
          Delete my Account
        </button>
      ) : (
        <form onSubmit={submit} noValidate aria-label="Confirm account deletion" className="settings-form">
          {errors.general && (
            <p role="alert" className="form-alert">
              {errors.general}
            </p>
          )}
          <FormField
            label="Your password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={errors.fields.current_password}
          />
          <FormField
            label={`Type ${CONFIRM_WORD} to confirm`}
            autoComplete="off"
            value={word}
            onChange={(e) => setWord(e.target.value)}
            error={errors.fields.confirmation}
          />
          <div className="settings-actions">
            <button type="submit" className="button button-danger" disabled={deleting}>
              {deleting ? 'Deleting…' : 'Permanently delete my account'}
            </button>
            <button type="button" className="button button-secondary" onClick={() => setOpen(false)} disabled={deleting}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

/** Account and Privacy Settings (frontend_spec.md Sections 15–16). */
export function SettingsPage() {
  const { user } = useAuth()
  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">Account and Privacy Settings</h1>
      <HelperNote>Your account details, a copy of your data, and deleting your account.</HelperNote>

      <section className="card" aria-labelledby="account-title">
        <h2 id="account-title">Account</h2>
        <dl className="account-details">
          <dt>Email</dt>
          <dd>{user?.email}</dd>
          <dt>Account created</dt>
          <dd>{user ? formatTimestamp(user.created_at) : ''}</dd>
        </dl>
        <ChangePassword />
      </section>

      <Exports />
      <DeleteAccount />
    </section>
  )
}

/** Shown after the account is deleted (outside the signed-in area). Forgets the session on this device. */
export function AccountDeletedPage() {
  const { endSession } = useAuth()
  useEffect(() => endSession(), [endSession])

  return (
    <>
      <h1>Your account has been deleted</h1>
      <p>
        Your documents, records, and sign-in have been removed and you have been signed out. Database backups may
        still hold your data until they expire, within 30 days.
      </p>
      <p>
        <Link to="/register">Create a new account</Link>
      </p>
    </>
  )
}
