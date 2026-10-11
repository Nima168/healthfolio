import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SECTIONS } from '../sections'
import { renderAt } from '../test/helpers'

describe('AppShell', () => {
  it('lists every primary section plus System Status in the main navigation', () => {
    renderAt('/documents')
    const nav = screen.getByRole('navigation', { name: 'Main' })

    for (const section of SECTIONS) {
      expect(within(nav).getByRole('link', { name: new RegExp(section.label) })).toBeInTheDocument()
    }
    expect(within(nav).getByRole('link', { name: 'System Status' })).toBeInTheDocument()
  })

  it('marks planned sections as coming soon', () => {
    renderAt('/documents')

    expect(screen.getByRole('heading', { level: 1, name: 'Medical Documents' })).toBeInTheDocument()
    expect(screen.getByText(/planned and not available yet/i)).toBeInTheDocument()
  })

  it('highlights the current section', () => {
    renderAt('/alerts')
    const nav = screen.getByRole('navigation', { name: 'Main' })

    expect(within(nav).getByRole('link', { name: /Alerts/ })).toHaveAttribute('aria-current', 'page')
  })

  it('offers a skip link to the main content', () => {
    renderAt('/')

    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute('href', '#main-content')
  })

  it('shows a not-found page for unknown routes', () => {
    renderAt('/nope')

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})
