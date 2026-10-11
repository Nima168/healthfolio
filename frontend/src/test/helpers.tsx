import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import App from '../App'

export function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

export function jsonResponse(status: number, body: unknown, requestId = 'req-123') {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': requestId },
  })
}

/** Stub fetch with a handler keyed by URL suffix, e.g. { '/health/live': () => jsonResponse(...) }. */
export function stubFetch(routes: Record<string, () => Response | Promise<Response>>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const match = Object.keys(routes).find((suffix) => url.endsWith(suffix))
    if (!match) throw new Error(`Unexpected fetch: ${url}`)
    return routes[match]()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
