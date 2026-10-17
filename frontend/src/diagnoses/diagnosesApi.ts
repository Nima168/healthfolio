/** Diagnoses and Conditions (api_contract_spec.md Section 6.14). */
import { apiGet } from '../api/client'

export type IssueKind = 'diagnosis' | 'assessment' | 'impression'

export interface Mention {
  /** Exactly as written in the document. */
  text: string
  kind: IssueKind
  document_id: string
  document_title: string | null
  date: string | null
}

export interface HealthIssue {
  /** The most recent wording. */
  name: string
  kinds: IssueKind[]
  first_seen: string | null
  last_seen: string | null
  profile: 'in_profile' | 'to_review' | 'not_in_profile'
  condition_status: 'active' | 'resolved' | 'unknown' | null
  /** Reports nothing wrong ("Normal heart size."): shown apart, never a written diagnosis. */
  normal: boolean
  /** Newest first. */
  mentions: Mention[]
}

export const diagnosesApi = {
  list: () => apiGet<{ items: HealthIssue[] }>('/diagnoses'),
}
