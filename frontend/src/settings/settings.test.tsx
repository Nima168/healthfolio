import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { errorResponse, LOGGED_IN, renderAt, stubFetch, stubObjectUrls } from '../test/helpers'

const sent = (fetchMock: ReturnType<typeof stubFetch>, path: string) =>
  fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith(path) && init?.method === 'POST')

describe('Account and Privacy Settings', () => {
  it('shows the account and changes the password', async () => {
    const fetchMock = stubFetch({ ...LOGGED_IN, 'POST /auth/password/change': () => new Response(null, { status: 204 }) })
    renderAt('/settings')

    const account = await screen.findByRole('region', { name: 'Account' })
    expect(within(account).getByText('asha@example.com')).toBeInTheDocument()
    const form = screen.getByRole('form', { name: 'Change password' })
    await userEvent.click(within(form).getByRole('button', { name: 'Change password' }))
    expect(within(form).getByText('Enter your current password.')).toBeInTheDocument()
    expect(sent(fetchMock, '/auth/password/change')).toHaveLength(0)

    await userEvent.type(within(form).getByLabelText('Current password'), 'a long enough passphrase')
    await userEvent.type(within(form).getByLabelText(/^New password/), 'a brand new passphrase')
    await userEvent.type(within(form).getByLabelText('Confirm new password'), 'a brand new passphrase')
    await userEvent.click(within(form).getByRole('button', { name: 'Change password' }))

    expect(await within(form).findByText(/Other devices have been signed out/)).toBeInTheDocument()
    const [[, init]] = sent(fetchMock, '/auth/password/change')
    expect(JSON.parse(String(init?.body))).toEqual({
      current_password: 'a long enough passphrase',
      new_password: 'a brand new passphrase',
    })
  })

  it('shows a wrong current password next to the field', async () => {
    stubFetch({
      ...LOGGED_IN,
      'POST /auth/password/change': () =>
        errorResponse(422, 'VALIDATION_ERROR', 'Invalid', [{ field: 'current_password', issue: 'This password is not correct.' }]),
    })
    renderAt('/settings')
    const form = await screen.findByRole('form', { name: 'Change password' })

    await userEvent.type(within(form).getByLabelText('Current password'), 'wrong password here')
    await userEvent.type(within(form).getByLabelText(/^New password/), 'a brand new passphrase')
    await userEvent.type(within(form).getByLabelText('Confirm new password'), 'a brand new passphrase')
    await userEvent.click(within(form).getByRole('button', { name: 'Change password' }))

    expect(await within(form).findByText('This password is not correct.')).toBeInTheDocument()
  })

  it('downloads each export and reports a failure', async () => {
    const created = stubObjectUrls()
    stubFetch({
      ...LOGGED_IN,
      'GET /account/export/pdf': () => new Response(new Blob(['%PDF-1.4']), { status: 200 }),
      'GET /account/export/json': () => errorResponse(429, 'RATE_LIMITED', 'Too many requests. Please try again later.'),
    })
    renderAt('/settings')
    const section = await screen.findByRole('region', { name: 'Export your data' })
    const row = (label: string) => within(section).getByText(label).closest('li') as HTMLElement

    expect(within(section).getByText(/Only your own records are included/)).toBeInTheDocument()
    await userEvent.click(within(row('PDF health summary')).getByRole('button', { name: 'Download' }))
    expect(await within(section).findByRole('status')).toHaveTextContent('PDF health summary downloaded.')
    expect(created).toHaveLength(1)

    await userEvent.click(within(row('All data (JSON)')).getByRole('button', { name: 'Download' }))
    expect(await within(section).findByRole('alert')).toHaveTextContent('Too many attempts')
  })

  it('deletes the account only after the password and the word DELETE, then signs out', async () => {
    const fetchMock = stubFetch({ ...LOGGED_IN, 'POST /auth/account/delete': () => new Response(null, { status: 204 }) })
    renderAt('/settings')
    const section = await screen.findByRole('region', { name: 'Delete account' })

    expect(within(section).getByText(/backups may still hold your data until they expire, within 30 days/)).toBeInTheDocument()
    await userEvent.click(within(section).getByRole('button', { name: 'Delete my Account' }))
    const form = within(section).getByRole('form', { name: 'Confirm account deletion' })
    await userEvent.type(within(form).getByLabelText('Your password'), 'a long enough passphrase')
    await userEvent.type(within(form).getByLabelText('Type DELETE to confirm'), 'delete')
    await userEvent.click(within(form).getByRole('button', { name: 'Permanently delete my account' }))
    expect(within(form).getByText('Type DELETE to confirm.')).toBeInTheDocument()
    expect(sent(fetchMock, '/auth/account/delete')).toHaveLength(0)

    await userEvent.clear(within(form).getByLabelText('Type DELETE to confirm'))
    await userEvent.type(within(form).getByLabelText('Type DELETE to confirm'), 'DELETE')
    await userEvent.click(within(form).getByRole('button', { name: 'Permanently delete my account' }))

    expect(await screen.findByRole('heading', { name: 'Your account has been deleted' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument() // signed out here
    const [[, init]] = sent(fetchMock, '/auth/account/delete')
    expect(JSON.parse(String(init?.body))).toEqual({ password: 'a long enough passphrase', confirmation: 'DELETE' })
  })

  it('keeps the account when the password is wrong', async () => {
    stubFetch({
      ...LOGGED_IN,
      'POST /auth/account/delete': () =>
        errorResponse(422, 'VALIDATION_ERROR', 'Invalid', [{ field: 'current_password', issue: 'This password is not correct.' }]),
    })
    renderAt('/settings')
    const section = await screen.findByRole('region', { name: 'Delete account' })

    await userEvent.click(within(section).getByRole('button', { name: 'Delete my Account' }))
    await userEvent.type(within(section).getByLabelText('Your password'), 'wrong password here')
    await userEvent.type(within(section).getByLabelText('Type DELETE to confirm'), 'DELETE')
    await userEvent.click(within(section).getByRole('button', { name: 'Permanently delete my account' }))

    expect(await within(section).findByText('This password is not correct.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Account and Privacy Settings' })).toBeInTheDocument()
  })
})
