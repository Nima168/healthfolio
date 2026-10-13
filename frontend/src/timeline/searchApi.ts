/** Record search (api_contract_spec.md Section 9.1). POST, so the query never appears in a URL. */
import { apiPost } from '../api/client'

export type RecordType =
  | 'document'
  | 'report_text'
  | 'lab_result'
  | 'medication'
  | 'diagnosis'
  | 'condition'
  | 'follow_up'
  | 'allergy'
  | 'surgery'
  | 'hospitalization'
  | 'family_history'

export interface SearchResult {
  record_type: RecordType
  id: string
  title: string
  date: string | null
  /** Which field matched the query, e.g. "Impression". */
  matched_field: string | null
  snippet: string | null
  source_document_id: string | null
  source_document_title: string | null
  link: string
}

export interface SearchCriteria {
  query?: string
  document_type?: string
  date_from?: string
  date_to?: string
  condition?: string
  provider?: string
}

export const searchApi = {
  search: (criteria: SearchCriteria, cursor: string | null = null) =>
    apiPost<{ items: SearchResult[]; total: number; next_cursor: string | null }>('/search', {
      ...criteria,
      ...(cursor ? { cursor } : {}),
    }),
}
