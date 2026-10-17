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

/** The shared demo account shown on the login page; both set at build time, or no note is shown. */
function readDemoAccount(): { email: string; password: string } | null {
  const email = (import.meta.env.VITE_DEMO_EMAIL as string | undefined)?.trim()
  const password = import.meta.env.VITE_DEMO_PASSWORD as string | undefined
  return email && password ? { email, password } : null
}

export const config = {
  apiBaseUrl: readApiBaseUrl(),
  demoAccount: readDemoAccount(),
}
