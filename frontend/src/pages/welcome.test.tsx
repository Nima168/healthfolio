import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { LOGGED_IN, LOGGED_OUT, renderAt, stubFetch } from '../test/helpers'

describe('Welcome page', () => {
  it('greets signed-out visitors at the home address and leads to the login page', async () => {
    stubFetch(LOGGED_OUT)
    renderAt('/')

    expect(await screen.findByRole('heading', { level: 1, name: 'Healthfolio' })).toBeInTheDocument()
    for (const heading of ['What you can do', 'How it works', 'How to access Healthfolio', 'Built to be trusted']) {
      expect(screen.getByRole('heading', { level: 2, name: heading })).toBeInTheDocument()
    }
    expect(screen.getByText(/gives information, not medical advice/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Create an account' })).toHaveAttribute('href', '/register')

    const hero = screen.getByRole('region', { name: 'Healthfolio' })
    await userEvent.click(within(hero).getByRole('link', { name: 'Log in' }))
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
  })

  it('links back from the login page', async () => {
    stubFetch(LOGGED_OUT)
    renderAt('/login')

    expect(await screen.findByRole('link', { name: 'see what Healthfolio does' })).toHaveAttribute('href', '/welcome')
  })

  it('opens from the app logo after signing in', async () => {
    stubFetch(LOGGED_IN)
    renderAt('/documents')

    const logo = await screen.findByRole('link', { name: /Healthfolio/ })
    expect(logo).toHaveAttribute('href', '/welcome')
    await userEvent.click(logo)
    expect(await screen.findByRole('heading', { level: 2, name: 'What you can do' })).toBeInTheDocument()
  })

  it('offers the dashboard to someone already signed in', async () => {
    stubFetch(LOGGED_IN)
    renderAt('/welcome')

    const hero = await screen.findByRole('region', { name: 'Healthfolio' })
    expect(await within(hero).findByRole('link', { name: 'Open your dashboard' })).toHaveAttribute('href', '/')
    expect(screen.queryByRole('link', { name: 'Create an account' })).not.toBeInTheDocument()
  })

  it('shows each step as a screenshot that opens full size', async () => {
    stubFetch(LOGGED_OUT)
    renderAt('/welcome')

    const tour = await screen.findByRole('region', { name: 'See it in action' })
    const shots = within(tour).getAllByRole('img')
    expect(shots).toHaveLength(7)
    expect(shots[0]).toHaveAttribute('src', '/welcome/upload.webp')
    expect(shots[0]).toHaveAttribute('loading', 'lazy')
    expect(shots.every((img) => (img.getAttribute('alt') ?? '').length > 20)).toBe(true)
    expect(within(tour).getByRole('heading', { name: 'Check what was read' })).toBeInTheDocument()

    await userEvent.click(within(tour).getAllByRole('button', { name: /Open full size/ })[0])
    const dialog = screen.getByRole('dialog', { name: 'Upload a report' })
    await userEvent.keyboard('{Escape}')
    expect(dialog).not.toBeInTheDocument()
  })

  it('ends with only a way back to the top', async () => {
    const scrollTo = vi.fn()
    vi.stubGlobal('scrollTo', scrollTo)
    stubFetch(LOGGED_IN)
    renderAt('/welcome')

    const end = await screen.findByRole('navigation', { name: 'End of page' })
    expect(within(end).queryByRole('link')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Welcome back' })).not.toBeInTheDocument()
    await userEvent.click(within(end).getByRole('button', { name: '↑ Back to top' }))
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' })
  })
})
