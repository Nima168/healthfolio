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

/** A digital PDF (its text is copied) or a scanned copy or photo (read with OCR). */
export type CopyType = 'digital' | 'scanned'

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
  /** Null for documents uploaded before the question existed. */
  copy_type: CopyType | null
  processing_status: string
  created_at: string
  updated_at: string
}

export interface DocumentPage {
  items: MedicalDocument[]
  pagination: { limit: number; next_cursor: string | null }
}

/** Filters for the documents list; dates are the report's own date (YYYY-MM-DD). */
export interface DocumentFilters {
  category: Category | ''
  dateFrom: string
  dateTo: string
  /** A hospital or clinic name, NO_PROVIDER, or '' for all. */
  provider: string
}

/** The "No hospital given" choice in the hospital filter. */
export const NO_PROVIDER = '__none__'

export interface ProviderList {
  /** Names as most often written; case and spacing variants are counted together. */
  items: { name: string; document_count: number }[]
  without_provider: number
}

export interface DocumentMetadata {
  title?: string
  category?: Category | null
  document_date?: string | null
  document_date_precision?: DatePrecision | null
  provider_name?: string | null
  copy_type?: CopyType | null
}

export const ACCEPTED_TYPES = ['application/pdf', 'image/jpeg', 'image/png']
export const ACCEPT_ATTRIBUTE = '.pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png'
export const MAX_UPLOAD_MB = 20
export const TITLE_MAX_LENGTH = 200

export const documentsApi = {
  list: (params: { cursor?: string | null; limit?: number } & Partial<DocumentFilters> = {}) => {
    const query = new URLSearchParams()
    if (params.limit) query.set('limit', String(params.limit))
    if (params.cursor) query.set('cursor', params.cursor)
    if (params.category) query.set('category', params.category)
    if (params.dateFrom) query.set('date_from', params.dateFrom)
    if (params.dateTo) query.set('date_to', params.dateTo)
    if (params.provider === NO_PROVIDER) query.set('provider_missing', 'true')
    else if (params.provider) query.set('provider', params.provider)
    const suffix = query.toString() ? `?${query}` : ''
    return apiGet<DocumentPage>(`/documents${suffix}`)
  },
  providers: () => apiGet<ProviderList>('/documents/providers'),
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
