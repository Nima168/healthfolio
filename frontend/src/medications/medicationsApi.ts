/** Medication records (api_contract_spec.md Section 6.6). */
import { apiDelete, apiGet, apiPatch, apiPost } from '../api/client'

export type MedicationStatus = 'active' | 'stopped' | 'unknown'

export interface Medication {
  id: string
  name: string
  strength: string | null
  /** How and when to take it, as written or entered. */
  dosage_text: string | null
  duration_text: string | null
  prescriber_name: string | null
  start_date: string | null
  end_date: string | null
  notes: string | null
  status: MedicationStatus
  origin: 'user_entered' | 'document_extracted' | 'suggestion_accepted'
  /** The user marked it as taking or stopped (a document never does). */
  status_confirmed: boolean
  /** The user changed its details after it was read from a document. */
  edited: boolean
  /** Unclear in the document; cleared once the user edits it. */
  review_reason: string | null
  source_document_id: string | null
  source_document_title: string | null
  source_document_date: string | null
  source_document_deleted: boolean
  updated_at: string
}

/** The editable values; null clears an optional one. */
export interface MedicationFields {
  name: string
  strength: string | null
  dosage_text: string | null
  duration_text: string | null
  prescriber_name: string | null
  start_date: string | null
  end_date: string | null
  notes: string | null
  status: MedicationStatus
}

export type HistoryField = keyof MedicationFields

export interface MedicationHistoryEntry {
  id: string
  change: 'added' | 'edited' | 'status_changed' | 'removed'
  changed_at: string
  /** field: [before, after] */
  changes: Partial<Record<HistoryField, [string | null, string | null]>>
}

const path = (id: string) => `/medications/${encodeURIComponent(id)}`

export const medicationsApi = {
  list: () => apiGet<{ items: Medication[] }>('/medications'),
  create: (fields: MedicationFields) => apiPost<Medication>('/medications', fields),
  update: (id: string, fields: Partial<MedicationFields>) => apiPatch<Medication>(path(id), fields),
  remove: (id: string) => apiDelete(path(id)),
  history: (id: string) => apiGet<{ items: MedicationHistoryEntry[] }>(`${path(id)}/history`),
}
