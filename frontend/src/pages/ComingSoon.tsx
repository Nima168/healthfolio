import { Link } from 'react-router-dom'

import type { Section } from '../sections'
import { HelperNote } from '../components/HelperNote'

/** Placeholder for planned sections, clearly marked as not yet available (frontend_spec.md Section 4). */
export function ComingSoon({ section }: { section: Section }) {
  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">{section.label}</h1>
      <HelperNote>{section.description}</HelperNote>
      <div className="card">
        <p>
          <strong>Coming soon.</strong> This section is planned and not available yet.
        </p>
        <p>
          You can check that the application is running on the <Link to="/status">System Status</Link> page.
        </p>
      </div>
    </section>
  )
}

export function NotFound() {
  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">Page not found</h1>
      <p className="page-intro">
        This page does not exist. Go back to the <Link to="/">Dashboard</Link>.
      </p>
    </section>
  )
}
