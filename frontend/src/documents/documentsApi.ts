/** Document endpoints (api_contract_spec.md Section 6.1.1). */
import { apiDelete, apiGet, apiGetBlob, apiPatch, apiUpload, type UploadOptions } from '../api/client'

export const CATEGORIES = [
  'lab_report',
  'prescription',
  'discharge_summary',
  'consultation_note',
  'imaging_report',
  'other',
  'unknown',
] as const
export type Category = (typeof CATEGORIES)[number]

export const DATE_PRECISIONS = ['day', 'month', 'year', 'unknown'] as const
export type DatePrecision = (typeof DATE_PRECISIONS)[number]

export interface MedicalDocument {
  id: string
  title: string
  original_filename: string | null
  media_type: 'application/pdf' | 'image/jpeg' | 'image/png'
  size_bytes: number
  category: Category
  document_date: string | null
  document_date_precision: DatePrecision | null
  provider_name: string | null
  processing_status: string
  created_at: string
  updated_at: string
}

export interface DocumentPage {
  items: MedicalDocument[]
  pagination: { limit: number; next_cursor: string | null }
}

export interface DocumentMetadata {
  title?: string
  category?: Category | null
  document_date?: string | null
  document_date_precision?: DatePrecision | null
  provider_name?: string | null
}

export const ACCEPTED_TYPES = ['application/pdf', 'image/jpeg', 'image/png']
export const ACCEPT_ATTRIBUTE = '.pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png'
export const MAX_UPLOAD_MB = 20
export const TITLE_MAX_LENGTH = 200

export const documentsApi = {
  list: (params: { cursor?: string | null; category?: Category | ''; limit?: number } = {}) => {
    const query = new URLSearchParams()
    if (params.limit) query.set('limit', String(params.limit))
    if (params.cursor) query.set('cursor', params.cursor)
    if (params.category) query.set('category', params.category)
    const suffix = query.toString() ? `?${query}` : ''
    return apiGet<DocumentPage>(`/documents${suffix}`)
  },
  get: (id: string) => apiGet<MedicalDocument>(`/documents/${encodeURIComponent(id)}`),
  upload: (file: File, metadata: DocumentMetadata, options?: UploadOptions) => {
    const form = new FormData()
    form.append('file', file)
    // Only send fields the user filled in.
    for (const [key, value] of Object.entries(metadata)) {
      if (value) form.append(key, value)
    }
    return apiUpload<MedicalDocument>('/documents', form, options)
  },
  update: (id: string, changes: DocumentMetadata) =>
    apiPatch<MedicalDocument>(`/documents/${encodeURIComponent(id)}`, changes),
  remove: (id: string) => apiDelete(`/documents/${encodeURIComponent(id)}`),
  file: (id: string, signal?: AbortSignal) => apiGetBlob(`/documents/${encodeURIComponent(id)}/file`, { signal }),
}
