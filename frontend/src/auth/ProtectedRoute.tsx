import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from './AuthContext'

/** Renders child routes only for logged-in users; otherwise sends them to login and back afterwards. */
export function ProtectedRoute() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <p role="status" className="page-intro">
        Loading your session…
      </p>
    )
  }
  if (status === 'anonymous') {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return <Outlet />
}
