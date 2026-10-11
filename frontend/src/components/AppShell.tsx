import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { SECTIONS, STATUS_SECTION, type Section } from '../sections'

function NavItem({ section }: { section: Section }) {
  return (
    <li>
      <NavLink to={section.path} end={section.path === '/'} className="nav-link">
        <span>{section.label}</span>
        {!section.available && (
          <span className="soon-tag" aria-label="coming soon">
            Soon
          </span>
        )}
      </NavLink>
    </li>
  )
}

function AccountBox() {
  const { status, user, logout } = useAuth()
  const navigate = useNavigate()
  const [loggingOut, setLoggingOut] = useState(false)

  if (status !== 'authenticated' || !user) {
    return status === 'anonymous' ? (
      <div className="account-box">
        <Link to="/login" className="button button-small">
          Log in
        </Link>
      </div>
    ) : null
  }

  async function handleLogout() {
    setLoggingOut(true)
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="account-box">
      <p className="account-name">{user.display_name ?? 'Signed in'}</p>
      <p className="account-email">{user.email}</p>
      <button type="button" className="button button-small button-secondary" onClick={handleLogout} disabled={loggingOut}>
        {loggingOut ? 'Logging out…' : 'Log out'}
      </button>
    </div>
  )
}

export function AppShell() {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <div className="shell">
        <aside className="sidebar">
          <p className="brand">Health Records</p>
          <nav aria-label="Main">
            <ul className="nav-list">
              {SECTIONS.map((section) => (
                <NavItem key={section.path} section={section} />
              ))}
              <li aria-hidden="true">
                <hr className="nav-divider" />
              </li>
              <NavItem section={STATUS_SECTION} />
            </ul>
          </nav>
          <AccountBox />
        </aside>
        <main id="main-content" className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </>
  )
}
