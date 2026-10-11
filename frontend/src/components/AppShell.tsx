import { NavLink, Outlet } from 'react-router-dom'

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
        </aside>
        <main id="main-content" className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </>
  )
}
