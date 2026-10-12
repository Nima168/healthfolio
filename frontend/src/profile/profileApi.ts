/** Health profile (api_contract_spec.md Section 6.9). */
import { apiDelete, apiGet, apiPatch, apiPost } from '../api/client'

export const PERSONAL_FIELDS = ['date_of_birth', 'sex', 'blood_group', 'height', 'weight'] as const
export type PersonalField = (typeof PERSONAL_FIELDS)[number]
export type ConditionStatus = 'active' | 'resolved' | 'unknown'
export type AllergyCategory = 'drug' | 'food' | 'environmental' | 'other'
export type RecordKind = 'surgery' | 'hospitalization' | 'family'
export type BmiCategory = 'underweight' | 'healthy' | 'overweight' | 'obesity_1' | 'obesity_2' | 'obesity_3'

export interface ProfileValue {
  value: string
  unit: string | null
  updated_at: string
}

export interface Allergy {
  id: string
  name: string
  category: AllergyCategory | null
  reaction: string | null
  added_at: string
}

export interface RecordItem {
  id: string
  kind: RecordKind
  name: string
  occurred_on: string | null
  relation: string | null
  notes: string | null
}

/** A hospital stay read from a discharge summary, as written. */
export interface DocumentStay {
  source_document_id: string
  source_document_title: string | null
  facility_name: string | null
  admitted_on: string | null
  discharged_on: string | null
  diagnoses: string[]
}

export interface ActiveMedication {
  id: string
  name: string
  strength: string | null
  dosage_text: string | null
  kind: 'prescription' | 'over_the_counter' | 'supplement'
}

export interface ProfileCondition {
  id: string
  name: string
  status: ConditionStatus
  origin: 'user_entered' | 'suggestion_accepted'
  source_document_id: string | null
  source_document_title: string | null
}

export interface ConditionSuggestion {
  id: string
  /** Exactly as written in the document. */
  name: string
  source_document_id: string
  source_document_title: string | null
  source_document_date: string | null
}

export interface Profile {
  values: Record<PersonalField, ProfileValue | null>
  /** Calculated from height and weight. */
  bmi: number | null
  /** Adult category; null without a BMI or for an age under 18. */
  bmi_category: BmiCategory | null
  allergies: Allergy[]
  conditions: ProfileCondition[]
  suggestions: ConditionSuggestion[]
  surgeries: RecordItem[]
  hospitalizations: RecordItem[]
  document_stays: DocumentStay[]
  family_history: RecordItem[]
  active_medications: ActiveMedication[]
}

export interface NewRecord {
  kind: RecordKind
  name: string
  occurred_on?: string
  relation?: string
  notes?: string
}

export interface ProfileHistoryEntry {
  field: string
  change: 'added' | 'changed' | 'removed'
  previous_value: string | null
  new_value: string | null
  changed_at: string
}

export const profileApi = {
  get: () => apiGet<Profile>('/profile'),
  updateValues: (values: Partial<Record<PersonalField, string>>) => apiPatch<Profile>('/profile/values', values),
  history: () => apiGet<{ items: ProfileHistoryEntry[] }>('/profile/history'),
  addAllergy: (name: string, category?: AllergyCategory, reaction?: string) =>
    apiPost<Allergy>('/profile/allergies', { name, ...(category ? { category } : {}), ...(reaction ? { reaction } : {}) }),
  addRecord: (record: NewRecord) => apiPost<RecordItem>('/profile/records', record),
  removeRecord: (id: string) => apiDelete(`/profile/records/${encodeURIComponent(id)}`),
  removeAllergy: (id: string) => apiDelete(`/profile/allergies/${encodeURIComponent(id)}`),
  addCondition: (name: string, status: ConditionStatus) =>
    apiPost<ProfileCondition>('/profile/conditions', { name, status }),
  updateCondition: (id: string, changes: { name?: string; status?: ConditionStatus }) =>
    apiPatch<ProfileCondition>(`/profile/conditions/${encodeURIComponent(id)}`, changes),
  removeCondition: (id: string) => apiDelete(`/profile/conditions/${encodeURIComponent(id)}`),
  reviewSuggestion: (id: string, action: 'accept' | 'correct' | 'reject', name?: string) =>
    apiPost<Profile>(`/profile/suggestions/${encodeURIComponent(id)}`, name ? { action, name } : { action }),
}
