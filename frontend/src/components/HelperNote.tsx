import type { ReactNode } from 'react'

/** One short line under a page title saying what the page does. */
export function HelperNote({ children }: { children: ReactNode }) {
  return (
    <p className="helper-note">
      <span className="helper-note-icon" aria-hidden="true">
        i
      </span>
      <span>{children}</span>
    </p>
  )
}
