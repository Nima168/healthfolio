import { afterEach, describe, expect, it } from 'vitest'

import { errorResponse, jsonResponse, stubFetch } from '../test/helpers'
import { ApiError, apiGet, apiPost, setAccessToken, setRefreshHandler } from './client'

afterEach(() => {
  setAccessToken(null)
  setRefreshHandler(null)
})

function headersOf(init: RequestInit | undefined): Record<string, string> {
  return (init?.headers ?? {}) as Record<string, string>
}

describe('apiGet', () => {
  it('returns parsed JSON on success and calls the configured base URL', async () => {
    const fetchMock = stubFetch({ '/health/live': () => jsonResponse(200, { status: 'alive' }) })

    await expect(apiGet('/health/live')).resolves.toEqual({ status: 'alive' })
    expect(String(fetchMock.mock.calls[0][0])).toBe('http://localhost:8000/api/v1/health/live')
  })

  it('converts the standard error format into an ApiError', async () => {
    stubFetch({ '/health/ready': () => errorResponse(503, 'SERVICE_UNAVAILABLE', 'Unavailable') })

    const error = await apiGet('/health/ready').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 503, code: 'SERVICE_UNAVAILABLE', requestId: 'req-err' })
  })

  it('falls back to the response header request ID when the body is not JSON', async () => {
    stubFetch({ '/x': () => new Response('oops', { status: 502, headers: { 'X-Request-ID': 'hdr-1' } }) })

    await expect(apiGet('/x')).rejects.toMatchObject({ status: 502, code: 'HTTP_ERROR', requestId: 'hdr-1' })
  })

  it('reports a network failure as NETWORK_ERROR', async () => {
    stubFetch({})

    await expect(apiGet('/health/live')).rejects.toMatchObject({ status: 0, code: 'NETWORK_ERROR' })
  })
})

describe('authentication handling', () => {
  it('sends the access token as a Bearer header and omits cookies on normal calls', async () => {
    const fetchMock = stubFetch({ '/users/me': () => jsonResponse(200, { id: 'u1' }) })
    setAccessToken('access-1')

    await apiGet('/users/me')

    const init = fetchMock.mock.calls[0][1]
    expect(headersOf(init).Authorization).toBe('Bearer access-1')
    expect(init?.credentials).toBe('omit')
  })

  it('sends cookies and the CSRF header to /auth endpoints', async () => {
    const fetchMock = stubFetch({ '/auth/logout': () => new Response(null, { status: 204 }) })

    await apiPost('/auth/logout', undefined, { authenticated: false })

    const init = fetchMock.mock.calls[0][1]
    expect(init?.credentials).toBe('include')
    expect(headersOf(init)['X-CSRF-Protection']).toBe('1')
    expect(headersOf(init).Authorization).toBeUndefined()
  })

  it('refreshes once on 401 and retries with the new token', async () => {
    const fetchMock = stubFetch({
      '/users/me': (init) =>
        headersOf(init).Authorization === 'Bearer fresh'
          ? jsonResponse(200, { id: 'u1' })
          : errorResponse(401, 'UNAUTHENTICATED'),
    })
    setAccessToken('expired')
    let refreshes = 0
    setRefreshHandler(async () => {
      refreshes += 1
      setAccessToken('fresh')
      return 'fresh'
    })

    await expect(apiGet('/users/me')).resolves.toEqual({ id: 'u1' })
    expect(refreshes).toBe(1)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('shares one refresh between concurrent 401s', async () => {
    stubFetch({
      '/users/me': (init) =>
        headersOf(init).Authorization === 'Bearer fresh'
          ? jsonResponse(200, { id: 'u1' })
          : errorResponse(401, 'UNAUTHENTICATED'),
    })
    setAccessToken('expired')
    let refreshes = 0
    setRefreshHandler(async () => {
      refreshes += 1
      await new Promise((resolve) => setTimeout(resolve, 10))
      setAccessToken('fresh')
      return 'fresh'
    })

    await Promise.all([apiGet('/users/me'), apiGet('/users/me'), apiGet('/users/me')])
    expect(refreshes).toBe(1)
  })

  it('gives up with the 401 when the session cannot be renewed', async () => {
    stubFetch({ '/users/me': () => errorResponse(401, 'UNAUTHENTICATED') })
    setAccessToken('expired')
    setRefreshHandler(async () => null)

    await expect(apiGet('/users/me')).rejects.toMatchObject({ status: 401, code: 'UNAUTHENTICATED' })
  })
})
