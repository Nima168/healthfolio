import { describe, expect, it } from 'vitest'

import { jsonResponse, stubFetch } from '../test/helpers'
import { ApiError, apiGet } from './client'

describe('apiGet', () => {
  it('returns parsed JSON on success and calls the configured base URL', async () => {
    const fetchMock = stubFetch({ '/health/live': () => jsonResponse(200, { status: 'alive' }) })

    await expect(apiGet('/health/live')).resolves.toEqual({ status: 'alive' })
    expect(String(fetchMock.mock.calls[0][0])).toBe('http://localhost:8000/api/v1/health/live')
  })

  it('converts the standard error format into an ApiError', async () => {
    stubFetch({
      '/health/ready': () =>
        jsonResponse(503, {
          error: {
            code: 'SERVICE_UNAVAILABLE',
            message: 'The service is temporarily unavailable.',
            details: [{ field: 'database', issue: 'unavailable' }],
            request_id: 'abc',
          },
        }),
    })

    const error = await apiGet('/health/ready').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 503, code: 'SERVICE_UNAVAILABLE', requestId: 'abc' })
  })

  it('falls back to the response header request ID when the body is not JSON', async () => {
    stubFetch({ '/x': () => new Response('oops', { status: 502, headers: { 'X-Request-ID': 'hdr-1' } }) })

    await expect(apiGet('/x')).rejects.toMatchObject({ status: 502, code: 'HTTP_ERROR', requestId: 'hdr-1' })
  })

  it('reports a network failure as NETWORK_ERROR', async () => {
    stubFetch({
      '/health/live': () => {
        throw new TypeError('Failed to fetch')
      },
    })

    await expect(apiGet('/health/live')).rejects.toMatchObject({ status: 0, code: 'NETWORK_ERROR' })
  })
})
