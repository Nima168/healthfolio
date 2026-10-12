/** Safety alerts (api_contract_spec.md Section 6.8). */
import { apiGet, apiPatch } from '../api/client'

export type AlertStatus = 'open' | 'acknowledged' | 'resolved'

export interface AlertHistoryEvent {
  event: 'raised' | 'acknowledged' | 'resolved' | 'reopened'
  actor: 'user' | 'system'
  note: string | null
  occurred_at: string
}

export interface SafetyAlert {
  id: string
  rule_code: string
  rule_version: number
  rule_description: string
  severity: 'info' | 'warning' | 'urgent'
  status: AlertStatus
  title: string
  /** Rule-based, deterministic. */
  reason: string
  uncertainty: string | null
  next_steps: string
  /** AI explanation, labelled; not generated yet. */
  explanation_text: string | null
  source_document_id: string | null
  /** null when the document was deleted. */
  source_document_title: string | null
  /** How the report was read (e.g. lab_report), or its upload type; null when deleted. */
  report_type: string | null
  /** The result's own date, else the report's date (YYYY-MM-DD); null when unknown. */
  report_date: string | null
  created_at: string
  acknowledged_at: string | null
  resolved_at: string | null
  resolved_by: 'user' | 'system' | null
  resolution_note: string | null
  history: AlertHistoryEvent[]
}

export const alertsApi = {
  list: () => apiGet<{ items: SafetyAlert[] }>('/alerts'),
  update: (id: string, status: 'acknowledged' | 'resolved', note?: string) =>
    apiPatch<SafetyAlert>(`/alerts/${encodeURIComponent(id)}`, note ? { status, note } : { status }),
}
