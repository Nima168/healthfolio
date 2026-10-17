/** Checkups and follow-ups (api_contract_spec.md Section 6.3). */
import { apiDelete, apiGet, apiPatch } from '../api/client'

export type FollowUpStatus = 'scheduled' | 'completed' | 'cancelled'

export interface FollowUp {
  id: string
  title: string
  kind: 'investigation' | 'appointment' | 'checkup'
  due_date: string
  status: FollowUpStatus
  /** Scheduled and the due date has passed (computed by the server). */
  overdue: boolean
  completed_at: string | null
  source_document_id: string | null
  source_document_title: string | null
}

export const followUpsApi = {
  list: () => apiGet<{ items: FollowUp[] }>('/follow-ups'),
  setStatus: (id: string, status: FollowUpStatus) =>
    apiPatch<FollowUp>(`/follow-ups/${encodeURIComponent(id)}`, { status }),
  /** Permanent. */
  remove: (id: string) => apiDelete(`/follow-ups/${encodeURIComponent(id)}`),
}
