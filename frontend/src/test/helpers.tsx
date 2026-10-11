import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import App from '../App'
import { AuthProvider } from '../auth/AuthContext'

export function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

export function jsonResponse(status: number, body: unknown, requestId = 'req-123') {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': requestId },
  })
}

export function errorResponse(status: number, code: string, message = 'Error', details: unknown[] = []) {
  return jsonResponse(status, { error: { code, message, details, request_id: 'req-err' } })
}

export const TEST_USER = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'asha@example.com',
  display_name: 'Asha',
  created_at: '2026-10-11T08:00:00Z',
}

export function tokenResponse(accessToken = 'access-1') {
  return jsonResponse(200, { access_token: accessToken, token_type: 'bearer', expires_in: 900, user: TEST_USER })
}

type Handler = (init: RequestInit | undefined) => Response | Promise<Response>

/**
 * Stub fetch with handlers keyed by "METHOD /path" or "/path" (any method), matched on the URL suffix.
 * Unmatched requests fail like a network error.
 */
export function stubFetch(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = (init?.method ?? 'GET').toUpperCase()
    const key = Object.keys(routes).find((candidate) => {
      const [first, second] = candidate.split(' ')
      const [routeMethod, suffix] = second ? [first, second] : [undefined, first]
      return (!routeMethod || routeMethod === method) && url.endsWith(suffix)
    })
    if (!key) throw new TypeError(`Unexpected fetch: ${method} ${url}`)
    return routes[key](init)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Routes for a user who is already logged in (session restored via the refresh cookie). */
export const LOGGED_IN = { 'POST /auth/refresh': () => tokenResponse() }

/** Routes for a visitor without a session. */
export const LOGGED_OUT = { 'POST /auth/refresh': () => errorResponse(401, 'UNAUTHENTICATED') }

// ---------- XMLHttpRequest fake (uploads) ----------

export interface FakeUploadRequest {
  method: string
  url: string
  headers: Record<string, string>
  body: FormData
}

type UploadReply = { status: number; body: unknown; requestId?: string }

/** Replace XMLHttpRequest; each send() is answered by `reply` after reporting 50% and 100% progress. */
export function stubUploads(reply: (request: FakeUploadRequest) => UploadReply) {
  const requests: FakeUploadRequest[] = []

  class FakeXMLHttpRequest {
    upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null }
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    onabort: (() => void) | null = null
    status = 0
    responseText = ''
    private request: FakeUploadRequest = { method: '', url: '', headers: {}, body: new FormData() }
    private responseRequestId = 'req-upload'

    open(method: string, url: string) {
      this.request.method = method
      this.request.url = url
    }
    setRequestHeader(name: string, value: string) {
      this.request.headers[name] = value
    }
    getResponseHeader(name: string) {
      return name.toLowerCase() === 'x-request-id' ? this.responseRequestId : null
    }
    abort() {
      this.onabort?.()
    }
    send(body: FormData) {
      this.request.body = body
      requests.push(this.request)
      const answer = reply(this.request)
      setTimeout(() => {
        for (const loaded of [50, 100]) {
          this.upload.onprogress?.({ lengthComputable: true, loaded, total: 100 } as ProgressEvent)
        }
        this.status = answer.status
        this.responseText = JSON.stringify(answer.body)
        this.responseRequestId = answer.requestId ?? 'req-upload'
        this.onload?.()
      }, 0)
    }
  }

  vi.stubGlobal('XMLHttpRequest', FakeXMLHttpRequest)
  return requests
}

/** jsdom has no object URLs; return predictable fake ones. */
export function stubObjectUrls() {
  const created: Blob[] = []
  vi.stubGlobal('URL', Object.assign(URL, {
    createObjectURL: vi.fn((blob: Blob) => {
      created.push(blob)
      return `blob:fake-${created.length}`
    }),
    revokeObjectURL: vi.fn(),
  }))
  return created
}
