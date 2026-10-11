/**
 * Single API client for all backend calls (frontend_spec.md Sections 3 and 14).
 * Errors are normalised to the standard error format (api_contract_spec.md Section 8).
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

async function toApiError(response: Response): Promise<ApiError> {
  const headerRequestId = response.headers.get('X-Request-ID')
  try {
    const body = (await response.json()) as ErrorBody
    const error = body.error ?? {}
    return new ApiError(
      response.status,
      error.code ?? 'HTTP_ERROR',
      error.message ?? 'The request could not be completed.',
      error.details ?? [],
      error.request_id ?? headerRequestId,
    )
  } catch {
    return new ApiError(response.status, 'HTTP_ERROR', 'The request could not be completed.', [], headerRequestId)
  }
}

export async function apiGet<T>(path: string, options: { signal?: AbortSignal } = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: options.signal,
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError(0, 'NETWORK_ERROR', 'The server could not be reached.')
  }

  if (!response.ok) throw await toApiError(response)
  return (await response.json()) as T
}
