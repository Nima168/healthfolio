import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { SECTIONS } from '../sections'
import { LOGGED_IN, LOGGED_OUT, renderAt, stubFetch } from '../test/helpers'

describe('AppShell', () => {
  it('lists every primary section plus System Status in the main navigation', async () => {
    stubFetch(LOGGED_IN)
    renderAt('/documents')
    const nav = await screen.findByRole('navigation', { name: 'Main' })

    for (const section of SECTIONS) {
      expect(within(nav).getByRole('link', { name: new RegExp(section.label) })).toBeInTheDocument()
    }
    expect(within(nav).getByRole('link', { name: 'System Status' })).toBeInTheDocument()
  })

  it('marks planned sections as coming soon', async () => {
    stubFetch(LOGGED_IN)
    renderAt('/settings')

    expect(await screen.findByRole('heading', { level: 1, name: 'Account and Privacy Settings' })).toBeInTheDocument()
    expect(screen.getByText(/planned and not available yet/i)).toBeInTheDocument()
  })

  it('highlights the current section', async () => {
    stubFetch(LOGGED_IN)
    renderAt('/alerts')
    const nav = await screen.findByRole('navigation', { name: 'Main' })

    expect(await within(nav).findByRole('link', { name: /Alerts/ })).toHaveAttribute('aria-current', 'page')
  })

  it('offers a skip link to the main content', async () => {
    stubFetch(LOGGED_IN)
    renderAt('/')

    expect(await screen.findByRole('link', { name: 'Skip to main content' })).toHaveAttribute('href', '#main-content')
  })

  it('shows a not-found page for unknown routes', async () => {
    stubFetch(LOGGED_OUT)
    renderAt('/nope')

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })

  it('shows the signed-in user and logs out', async () => {
    const fetchMock = stubFetch({ ...LOGGED_IN, 'POST /auth/logout': () => new Response(null, { status: 204 }) })
    renderAt('/')

    expect(await screen.findByText('asha@example.com')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Log out' }))

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/auth/logout'))).toBe(true)
  })
})
