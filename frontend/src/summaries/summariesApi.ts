/** AI summaries (api_contract_spec.md Section 6.12). */
import { apiGet, apiPost } from '../api/client'

export interface SummarySentence {
  text: string
  /** "record" restates the records; "interpretation" is the AI's cautious reading of them. */
  kind: 'record' | 'interpretation'
  fact_ids: string[]
}

export interface SummarySection {
  key: string
  title: string
  sentences: SummarySentence[]
}

export interface SourceRef {
  kind: string
  title: string
  date: string | null
  trust: string | null
  source_document_id: string | null
  source_document_title: string | null
  link: string | null
}

export interface AiSummary {
  id: string
  scope: 'history' | 'document'
  created_at: string
  model_version: string
  sections: SummarySection[]
  /** General medical knowledge, not drawn from the records. */
  explanations: { term: string; text: string; fact_ids: string[] }[]
  /** Gaps found by fixed rules, not by the AI. */
  insights: { id: string; text: string; link: string | null }[]
  sources: Record<string, SourceRef>
  dropped_count: number
}

export interface SummaryState {
  enabled: boolean
  can_create: boolean
  summary: AiSummary | null
  stale: boolean
}

export const summariesApi = {
  history: () => apiGet<SummaryState>('/summaries/history'),
  createHistory: () => apiPost<SummaryState>('/summaries/history'),
  document: (documentId: string) => apiGet<SummaryState>(`/documents/${documentId}/summary`),
  createDocument: (documentId: string) => apiPost<SummaryState>(`/documents/${documentId}/summary`),
}
