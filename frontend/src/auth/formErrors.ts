import { ApiError } from '../api/client'

export interface FormErrors {
  general?: string
  fields: Record<string, string>
}

/** Turn an API error into a general message plus per-field messages from `details`. */
export function toFormErrors(error: unknown, fallback = 'Something went wrong. Please try again.'): FormErrors {
  if (!(error instanceof ApiError)) return { general: fallback, fields: {} }

  const fields: Record<string, string> = {}
  for (const detail of error.details) fields[detail.field] = detail.issue

  if (error.code === 'NETWORK_ERROR') return { general: 'The server could not be reached. Check your connection.', fields }
  if (error.code === 'RATE_LIMITED') return { general: 'Too many attempts. Please wait a few minutes and try again.', fields }
  if (error.code === 'VALIDATION_ERROR' && Object.keys(fields).length > 0) return { fields }
  return { general: error.message, fields }
}
