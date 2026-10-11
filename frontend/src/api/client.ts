/**
 * Single API client for all backend calls (frontend_spec.md Sections 3 and 14).
 * - Errors are normalised to the standard error format (api_contract_spec.md Section 8).
 * - The access token lives only in memory and is sent as a Bearer header.
 * - /auth/* calls include cookies (HttpOnly refresh token) and the CSRF header.
 * - A 401 on an authenticated call triggers one shared refresh, then a single retry.
 */
import { config } from '../config'

export interface ErrorDetail {
  field: string
  issue: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: ErrorDetail[]
  readonly requestId: string | null

  constructor(status: number, code: string, message: string, details: ErrorDetail[] = [], requestId: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string; details?: ErrorDetail[]; request_id?: string }
}

// ---------- auth wiring (set by AuthProvider) ----------

let accessToken: string | null = null
let refreshHandler: (() => Promise<string | null>) | null = null
let refreshInFlight: Promise<string | null> | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
}

/** The handler returns a fresh access token, or null if the session cannot be renewed. */
export function setRefreshHandler(handler: (() => Promise<string | null>) | null): void {
  refreshHandler = handler
}

/** Concurrent callers share one refresh request, so the refresh cookie is rotated only once. */
export function refreshAccessToken(): Promise<string | null> {
  if (!refreshHandler) return Promise.resolve(null)
  refreshInFlight ??= refreshHandler().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

// ---------- requests ----------

interface RequestOptions {
  body?: unknown
  signal?: AbortSignal
  /** Send the Bearer token and retry once after a refresh on 401. Default true. */
  authenticated?: boolean
}

function errorFromBody(status: number, text: string, headerRequestId: string | null): ApiError {
  try {
    const error = (JSON.parse(text) as ErrorBody).error ?? {}
    return new ApiError(
      status,
      error.code ?? 'HTTP_ERROR',
      error.message ?? 'The request could not be completed.',
      error.details ?? [],
      error.request_id ?? headerRequestId,
    )
  } catch {
    return new ApiError(status, 'HTTP_ERROR', 'The request could not be completed.', [], headerRequestId)
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  return errorFromBody(response.status, await response.text(), response.headers.get('X-Request-ID'))
}

const networkError = () => new ApiError(0, 'NETWORK_ERROR', 'The server could not be reached.')

async function send(method: string, path: string, options: RequestOptions, token: string | null): Promise<Response> {
  const isAuthEndpoint = path.startsWith('/auth/')
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  if (isAuthEndpoint) headers['X-CSRF-Protection'] = '1'

  try {
    return await fetch(`${config.apiBaseUrl}${path}`, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: isAuthEndpoint ? 'include' : 'omit',
      signal: options.signal,
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw networkError()
  }
}

/** Send with the current token; on 401, refresh once and retry. Returns a successful response or throws. */
async function sendWithRetry(method: string, path: string, options: RequestOptions): Promise<Response> {
  const authenticated = options.authenticated ?? true
  let response = await send(method, path, options, authenticated ? accessToken : null)

  if (response.status === 401 && authenticated && accessToken) {
    const renewed = await refreshAccessToken()
    if (renewed) response = await send(method, path, options, renewed)
  }

  if (!response.ok) throw await toApiError(response)
  return response
}

async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const response = await sendWithRetry(method, path, options)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function apiGet<T>(path: string, options: Omit<RequestOptions, 'body'> = {}): Promise<T> {
  return request<T>('GET', path, options)
}

export function apiPost<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'body'> = {}): Promise<T> {
  return request<T>('POST', path, { ...options, body })
}

export function apiPatch<T>(path: string, body: unknown, options: Omit<RequestOptions, 'body'> = {}): Promise<T> {
  return request<T>('PATCH', path, { ...options, body })
}

export function apiDelete(path: string, options: Omit<RequestOptions, 'body'> = {}): Promise<void> {
  return request<void>('DELETE', path, options)
}

/** Fetch binary content (e.g. a document) through the authenticated API. */
export async function apiGetBlob(path: string, options: Omit<RequestOptions, 'body'> = {}): Promise<Blob> {
  const response = await sendWithRetry('GET', path, options)
  return response.blob()
}

// ---------- uploads (XMLHttpRequest, for progress events) ----------

export interface UploadOptions {
  /** Called with a value from 0 to 1 as the request body is sent. */
  onProgress?: (fraction: number) => void
  signal?: AbortSignal
}

function uploadOnce<T>(path: string, form: FormData, token: string | null, options: UploadOptions) {
  return new Promise<{ status: number; body: string; requestId: string | null }>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${config.apiBaseUrl}${path}`)
    xhr.setRequestHeader('Accept', 'application/json')
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) options.onProgress?.(event.loaded / event.total)
    }
    xhr.onload = () => resolve({ status: xhr.status, body: xhr.responseText, requestId: xhr.getResponseHeader('X-Request-ID') })
    xhr.onerror = () => reject(networkError())
    xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'))
    options.signal?.addEventListener('abort', () => xhr.abort(), { once: true })
    xhr.send(form)
  }).then(({ status, body, requestId }) => {
    if (status >= 200 && status < 300) return { ok: true as const, value: JSON.parse(body) as T }
    return { ok: false as const, status, error: errorFromBody(status, body, requestId) }
  })
}

/** Upload multipart form data with progress; refreshes the session once on 401, like other calls. */
export async function apiUpload<T>(path: string, form: FormData, options: UploadOptions = {}): Promise<T> {
  let result = await uploadOnce<T>(path, form, accessToken, options)
  if (!result.ok && result.status === 401 && accessToken) {
    const renewed = await refreshAccessToken()
    if (renewed) {
      options.onProgress?.(0)
      result = await uploadOnce<T>(path, form, renewed, options)
    }
  }
  if (!result.ok) throw result.error
  return result.value
}
