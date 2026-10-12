/** Health timeline (api_contract_spec.md Section 6.7). */
import { apiGet } from '../api/client'

export const TIMELINE_CATEGORIES = [
  'lab_results',
  'imaging',
  'test_reports',
  'consultations',
  'hospital_stays',
  'prescriptions',
  'medications',
  'follow_ups',
  'documents',
] as const
export type TimelineCategory = (typeof TIMELINE_CATEGORIES)[number]

export type Trust = 'from_document' | 'confirmed_by_you' | 'edited_by_you' | 'added_by_you'

export interface TimelineEntry {
  id: string
  /** null: no date is known (never guessed). */
  date: string | null
  date_precision: 'day' | 'month' | 'year' | 'unknown' | null
  category: TimelineCategory
  title: string
  lines: string[]
  trust: Trust
  tag: string | null
  source_document_id: string | null
  source_document_title: string | null
  /** The page that shows this record (a document, Medications, or Follow-ups). */
  link: string | null
}

export interface TimelineFilters {
  categories: TimelineCategory[]
  dateFrom: string
  dateTo: string
}

export const timelineApi = {
  list: (filters: TimelineFilters, cursor: string | null = null) => {
    const query = new URLSearchParams()
    for (const category of filters.categories) query.append('category', category)
    if (filters.dateFrom) query.set('date_from', filters.dateFrom)
    if (filters.dateTo) query.set('date_to', filters.dateTo)
    if (cursor) query.set('cursor', cursor)
    const suffix = query.toString() ? `?${query}` : ''
    return apiGet<{ items: TimelineEntry[]; next_cursor: string | null }>(`/timeline${suffix}`)
  },
}
