/** Dashboard overview (api_contract_spec.md Section 6.11). */
import { apiGet } from '../api/client'
import type { Category } from '../documents/documentsApi'
import type { BmiCategory } from '../profile/profileApi'
import type { TimelineEntry } from '../timeline/timelineApi'

export interface LatestVital {
  value: string
  unit: string
  measured_on: string
  measured_time: string | null
}

export interface DocumentCount {
  id: string
  title: string | null
  count: number
}

export interface Dashboard {
  documents_total: number
  documents_reading: number
  recent_documents: {
    id: string
    title: string | null
    category: Category
    uploaded_at: string
    reading_status: string | null
    read_as: string | null
  }[]
  overdue_follow_ups: { id: string; title: string; due_date: string; source_document_id: string | null }[]
  upcoming_follow_ups: { id: string; title: string; due_date: string; source_document_id: string | null }[]
  alerts_open: number
  alerts_acknowledged: number
  alerts_urgent: number
  top_alerts: { id: string; title: string; severity: 'info' | 'warning' | 'urgent'; source_document_title: string | null }[]
  profile_suggestions: number
  unconfirmed_medicines: number
  follow_ups_to_add: DocumentCount[]
  failed_documents: DocumentCount[]
  profile_filled: number
  profile_total: number
  profile_missing: string[]
  allergies: string[]
  conditions: number
  active_medications: number
  bmi: number | null
  bmi_category: BmiCategory | null
  latest_blood_pressure: LatestVital | null
  latest_heart_rate: LatestVital | null
  recent_activity: TimelineEntry[]
}

export const dashboardApi = {
  get: () => apiGet<Dashboard>('/dashboard'),
}
