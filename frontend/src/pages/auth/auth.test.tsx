import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import { safeNextPath } from '../../auth/navigation'
import { config } from '../../config'
import { errorResponse, jsonResponse, LOGGED_IN, LOGGED_OUT, renderAt, stubFetch, tokenResponse } from '../../test/helpers'

function bodyOf(init: RequestInit | undefined) {
  return JSON.parse(String(init?.body))
}

describe('route protection', () => {
  it('redirects visitors without a session to login', async () => {
    stubFetch(LOGGED_OUT)
    renderAt('/documents')

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
  })

  it('restores the session from the refresh cookie on load', async () => {
    stubFetch(LOGGED_IN)
    renderAt('/documents')

    expect(await screen.findByRole('heading', { name: 'Medical Documents' })).toBeInTheDocument()
  })

  it('keeps the status page public', async () => {
    stubFetch({ ...LOGGED_OUT, '/health/live': () => jsonResponse(200, {}), '/health/ready': () => jsonResponse(200, {}) })
    renderAt('/status')

    expect(await screen.findByRole('heading', { name: 'System Status' })).toBeInTheDocument()
  })

  it.each([
    ['/documents', '/documents'],
    ['//evil.example', '/'],
    ['https://evil.example', '/'],
    ['/\\evil.example', '/'],
    [null, '/'],
  ])('only follows safe "next" paths: %s', (next, expected) => {
    expect(safeNextPath(next)).toBe(expected)
  })
})

describe('LoginPage', () => {
  it('logs in and returns to the page the user wanted', async () => {
    const fetchMock = stubFetch({ ...LOGGED_OUT, 'POST /auth/login': () => tokenResponse() })
    renderAt('/login?next=%2Fmedications')

    await userEvent.type(await screen.findByLabelText('Email'), 'asha@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'a long enough passphrase')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('heading', { name: 'Medications' })).toBeInTheDocument()
    const loginCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/auth/login'))
    expect(bodyOf(loginCall?.[1])).toEqual({ email: 'asha@example.com', password: 'a long enough passphrase' })
  })

  it('shows the generic error and clears the password on failure', async () => {
    stubFetch({
      ...LOGGED_OUT,
      'POST /auth/login': () =>
        errorResponse(401, 'INVALID_CREDENTIALS', 'Email or password is incorrect, or the account is temporarily locked.'),
    })
    renderAt('/login')

    await userEvent.type(await screen.findByLabelText('Email'), 'asha@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong password value')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/incorrect, or the account is temporarily locked/)
    expect(screen.getByLabelText('Password')).toHaveValue('')
  })

  it('explains rate limiting in plain language', async () => {
    stubFetch({ ...LOGGED_OUT, 'POST /auth/login': () => errorResponse(429, 'RATE_LIMITED') })
    renderAt('/login')

    await userEvent.type(await screen.findByLabelText('Email'), 'asha@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/Too many attempts/)
  })
})

describe('Demo account note', () => {
  afterEach(() => {
    config.demoAccount = null
  })

  it('shows the demo account, asks not to change it, and fills the form', async () => {
    config.demoAccount = { email: 'demo@example.com', password: 'demo passphrase 1' }
    const fetchMock = stubFetch({ ...LOGGED_OUT, 'POST /auth/login': () => tokenResponse() })
    renderAt('/login')

    const note = await screen.findByRole('complementary', { name: 'Demo account' })
    expect(note).toHaveTextContent('Try the app and its AI features')
    expect(note).toHaveTextContent('demo@example.com')
    expect(note).toHaveTextContent('demo passphrase 1')
    expect(note).toHaveTextContent("Please don't change the demo account's email or password")

    await userEvent.click(screen.getByRole('button', { name: 'Use demo account' }))
    expect(screen.getByLabelText('Email')).toHaveValue('demo@example.com')
    expect(screen.getByLabelText('Password')).toHaveValue('demo passphrase 1')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    await screen.findByRole('heading', { name: 'Dashboard' })
    const loginCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/auth/login'))
    expect(bodyOf(loginCall?.[1])).toEqual({ email: 'demo@example.com', password: 'demo passphrase 1' })
  })

  it('is not shown when no demo account is configured', async () => {
    stubFetch(LOGGED_OUT)
    renderAt('/login')

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: 'Demo account' })).not.toBeInTheDocument()
  })
})

describe('RegisterPage', () => {
  it('checks password length and confirmation before calling the API', async () => {
    const fetchMock = stubFetch(LOGGED_OUT)
    renderAt('/register')

    await userEvent.type(await screen.findByLabelText('Email'), 'asha@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'short')
    await userEvent.type(screen.getByLabelText('Confirm password'), 'different')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(screen.getByText(/at least 12 characters\./)).toBeInTheDocument()
    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/auth/register'))).toBe(false)
  })

  it('shows field errors returned by the API', async () => {
    stubFetch({
      ...LOGGED_OUT,
      'POST /auth/register': () =>
        errorResponse(422, 'VALIDATION_ERROR', 'Invalid', [{ field: 'email', issue: 'Enter a valid email address.' }]),
    })
    renderAt('/register')

    await userEvent.type(await screen.findByLabelText('Email'), 'bad@x')
    await userEvent.type(screen.getByLabelText('Password'), 'a long enough passphrase')
    await userEvent.type(screen.getByLabelText('Confirm password'), 'a long enough passphrase')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
  })

  it('registers and lands on the dashboard', async () => {
    stubFetch({ ...LOGGED_OUT, 'POST /auth/register': () => tokenResponse() })
    renderAt('/register')

    await userEvent.type(await screen.findByLabelText('Email'), 'asha@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'a long enough passphrase')
    await userEvent.type(screen.getByLabelText('Confirm password'), 'a long enough passphrase')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
  })
})

describe('Password reset', () => {
  it('forgot-password shows the same confirmation regardless of the account', async () => {
    stubFetch({
      ...LOGGED_OUT,
      'POST /auth/password/forgot': () =>
        jsonResponse(202, { message: 'If an account exists for that email, a password reset link has been sent.' }),
    })
    renderAt('/forgot-password')

    await userEvent.type(await screen.findByLabelText('Email'), 'asha@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }))

    expect(await screen.findByRole('heading', { name: 'Check your email' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('If asha@example.com has an account')
    expect(screen.getByText(/no email is sent if there's no account/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Use a different email' }))
    expect(await screen.findByRole('button', { name: 'Send reset link' })).toBeInTheDocument()
  })

  it('reads the token from the link fragment, removes it from the URL, and resets', async () => {
    const fetchMock = stubFetch({ ...LOGGED_OUT, 'POST /auth/password/reset': () => new Response(null, { status: 204 }) })
    renderAt('/reset-password#token=abc123')

    await userEvent.type(await screen.findByLabelText('New password'), 'another long passphrase')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'another long passphrase')
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }))

    expect(await screen.findByRole('heading', { name: 'Password changed' })).toBeInTheDocument()
    const resetCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/auth/password/reset'))
    expect(bodyOf(resetCall?.[1])).toEqual({ token: 'abc123', new_password: 'another long passphrase' })
  })

  it('explains an expired link', async () => {
    stubFetch({
      ...LOGGED_OUT,
      'POST /auth/password/reset': () =>
        errorResponse(400, 'INVALID_OR_EXPIRED_TOKEN', 'This reset link is invalid or has expired.'),
    })
    renderAt('/reset-password#token=old')

    await userEvent.type(await screen.findByLabelText('New password'), 'another long passphrase')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'another long passphrase')
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid or has expired/)
    expect(screen.getByRole('link', { name: 'Request a new link' })).toBeInTheDocument()
  })

  it('asks for a new link when the page is opened without a token', async () => {
    stubFetch(LOGGED_OUT)
    renderAt('/reset-password')

    expect(await screen.findByRole('heading', { name: 'Reset link missing' })).toBeInTheDocument()
  })
})
