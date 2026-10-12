/** Vital sign readings (api_contract_spec.md Section 6.10). */
import { apiDelete, apiGet, apiPost } from '../api/client'

export interface VitalReading {
  id: string
  measured_on: string
  /** HH:MM:SS, or null when no time was entered. */
  measured_time: string | null
  systolic: number | null
  diastolic: number | null
  heart_rate: number | null
  context: string | null
}

export interface NewVitalReading {
  measured_on: string
  measured_time?: string
  systolic?: number
  diastolic?: number
  heart_rate?: number
  context?: string
}

export const vitalsApi = {
  list: () => apiGet<{ items: VitalReading[] }>('/vitals'),
  add: (reading: NewVitalReading) => apiPost<VitalReading>('/vitals', reading),
  remove: (id: string) => apiDelete(`/vitals/${encodeURIComponent(id)}`),
}
