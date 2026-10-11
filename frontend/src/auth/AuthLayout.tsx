import { Link, Navigate, Outlet, useLocation, useSearchParams } from 'react-router-dom'

import { useAuth } from './AuthContext'
import { safeNextPath } from './navigation'

/** Centered layout for login/register/password pages. Logged-in users are sent to the app. */
export function AuthLayout() {
  const { status } = useAuth()
  const { pathname } = useLocation()
  const [searchParams] = useSearchParams()

  // A logged-in user may still open a reset link (e.g. resetting from another device).
  // Otherwise go where they were headed, so this agrees with the login page's own redirect.
  if (status === 'authenticated' && pathname !== '/reset-password') {
    return <Navigate to={safeNextPath(searchParams.get('next'))} replace />
  }

  return (
    <div className="auth-page">
      <main className="auth-card card">
        <p className="brand">
          <Link to="/" className="brand-link">
            Health Records
          </Link>
        </p>
        <Outlet />
      </main>
      <p className="auth-footnote">
        Informational support only — not a substitute for professional medical care. <Link to="/status">System status</Link>
      </p>
    </div>
  )
}
