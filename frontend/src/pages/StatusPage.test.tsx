import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { jsonResponse, renderAt, stubFetch } from '../test/helpers'

const LIVE_OK = () => jsonResponse(200, { status: 'alive' })
const READY_OK = () => jsonResponse(200, { status: 'ready', checks: { database: 'ok' } })
const READY_DOWN = () =>
  jsonResponse(503, {
    error: {
      code: 'SERVICE_UNAVAILABLE',
      message: 'The service is temporarily unavailable.',
      details: [{ field: 'database', issue: 'unavailable' }],
      request_id: 'req-503',
    },
  })

function row(name: string) {
  return within(screen.getByText(name).closest('li') as HTMLElement)
}

describe('StatusPage', () => {
  it('shows running and ready when both checks pass', async () => {
    stubFetch({ '/health/live': LIVE_OK, '/health/ready': READY_OK })
    renderAt('/status')

    expect(await row('Backend service').findByText('Running')).toBeInTheDocument()
    expect(await row('Database').findByText('Ready')).toBeInTheDocument()
  })

  it('shows the database as not ready with a request ID when readiness fails', async () => {
    stubFetch({ '/health/live': LIVE_OK, '/health/ready': READY_DOWN })
    renderAt('/status')

    expect(await row('Database').findByText('Not ready')).toBeInTheDocument()
    expect(screen.getByText('Request ID: req-503')).toBeInTheDocument()
    expect(row('Backend service').getByText('Running')).toBeInTheDocument()
  })

  it('shows the backend as unreachable and the database as unknown when the server is down', async () => {
    stubFetch({
      '/health/live': () => {
        throw new TypeError('Failed to fetch')
      },
      '/health/ready': () => {
        throw new TypeError('Failed to fetch')
      },
    })
    renderAt('/status')

    expect(await row('Backend service').findByText('Unreachable')).toBeInTheDocument()
    expect(row('Database').getByText('Unknown (backend unreachable)')).toBeInTheDocument()
  })

  it('re-runs the checks when "Check again" is pressed', async () => {
    const fetchMock = stubFetch({ '/health/live': LIVE_OK, '/health/ready': READY_OK })
    renderAt('/status')
    const button = await screen.findByRole('button', { name: 'Check again' })

    await userEvent.click(button)

    expect(await screen.findByRole('button', { name: 'Check again' })).toBeEnabled()
    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(4)
  })
})
