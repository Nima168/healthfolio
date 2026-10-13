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
    // The home address introduces the app; other pages go straight to login and come back afterwards.
    if (location.pathname === '/') return <Navigate to="/welcome" replace />
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return <Outlet />
}
