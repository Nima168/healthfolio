/**
 * Environment-based configuration (frontend_spec.md Section 3).
 * Only public values belong here: anything in a VITE_ variable ships to the browser.
 */
const DEV_API_BASE_URL = 'http://localhost:8000/api/v1'

function readApiBaseUrl(): string {
  const value = import.meta.env.VITE_API_BASE_URL as string | undefined
  if (value) return value.replace(/\/+$/, '')
  if (import.meta.env.DEV) return DEV_API_BASE_URL
  throw new Error('VITE_API_BASE_URL must be set for production builds.')
}

export const config = {
  apiBaseUrl: readApiBaseUrl(),
}
