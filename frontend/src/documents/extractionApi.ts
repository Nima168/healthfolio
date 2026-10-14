/** Extracted results: lab summary and prescription summary (api_contract_spec.md Sections 6.2, 6.3). */
import { apiGet, apiPost } from '../api/client'
import type { CopyType, DatePrecision } from './documentsApi'

export type JobStatus = 'pending' | 'running' | 'completed' | 'completed_with_warnings' | 'failed' | 'cancelled'

export interface Observation {
  id: string
  name: string
  value_text: string
  value_numeric: string | null
  unit: string | null
  reference_range_text: string | null
  reference_low: string | null
  reference_high: string | null
  observed_at: string | null
  observed_at_precision: DatePrecision | null
  page: number | null
  source_snippet: string | null
  confidence: 'high' | 'medium' | 'low' | null
  needs_review: boolean
  validation_findings: string[]
  notes: string | null
}

export interface SummaryLine {
  name: string
  value_text: string
  unit: string | null
  reference_range_text: string | null
  /** For example "Unusually far outside the range: check the original." */
  note?: string | null
}

/** Results judged only against the reference range printed in the report (backend rules, not the AI). */
export interface LabSummary {
  report_date: string | null
  above: SummaryLine[]
  below: SummaryLine[]
  normal: SummaryLine[]
  /** Results that could not be judged (no range, not a single number, or unclear); shown as written. */
  invalid: (SummaryLine & { reason: string })[]
}

export interface MedicationLine {
  name: string
  strength: string | null
  instructions: string | null
  duration_text: string | null
  /** Hard to read or incomplete: shown with "(unclear – check original)"; `reason` says why. */
  unclear: boolean
  reason: string | null
}

export interface FollowUpLine {
  /** Null for an approximate timing (see when_text, e.g. "Mid-January 2027") or an unclear one. */
  due_date: string | null
  description: string
  unclear: boolean
  reason: string | null
  /** The timing exactly as written ("after 4 weeks", "02/09/26"); shown instead of a reformatted date. */
  when_text: string | null
  /** due_date was counted from the document date ("after 4 weeks"), not printed. */
  calculated: boolean
}

/** Medicines, follow-ups grouped by date, and what needs review (backend rules; the AI only reads). */
export interface PrescriptionSummary {
  prescribed_on: string | null
  date_text: string | null
  prescriber_name: string | null
  medications: MedicationLine[]
  follow_ups: FollowUpLine[]
  /** "available": can be added to Checkups and Follow-ups; "added": already added; "none": nothing to add. */
  reminders: 'available' | 'added' | 'none'
}

export interface KeyResult {
  name: string
  /** Shown as "first → last" when the test was done more than once. */
  first_value: string | null
  last_value: string
  unit: string | null
  reference_range_text: string | null
  /** Against the printed range; null for text results. */
  flag: 'high' | 'low' | null
  /** The first value was outside the range on the same side. */
  still: boolean
  /** Set when the last test was before the discharge date. */
  last_tested: string | null
  unclear: boolean
}

/** Stay, diagnoses (as written), key results, medicines, follow-ups, warning signs (backend rules). */
export interface DischargeSummary {
  facility_name: string | null
  admitted_on: string | null
  admitted_text: string | null
  discharged_on: string | null
  discharged_text: string | null
  stay_days: number | null
  diagnoses: string[]
  key_results: KeyResult[]
  medications: MedicationLine[]
  follow_ups: FollowUpLine[]
  reminders: 'available' | 'added' | 'none'
  warning_signs: string[]
}

/** Consultation note, exactly as written. */
export interface ConsultationSummary {
  visit_date: string | null
  visit_text: string | null
  clinician_name: string | null
  symptoms: string[]
  observations: string[]
  assessment: string[]
  plan: string[]
  follow_ups: FollowUpLine[]
  reminders: 'available' | 'added' | 'none'
}

/** The written imaging report, exactly as written; scan images are not read. */
export interface ImagingSummary {
  is_written_report: boolean
  exam_name: string | null
  report_id: string | null
  facility_name: string | null
  exam_date: string | null
  exam_text: string | null
  report_date: string | null
  report_text: string | null
  body_region: string | null
  findings: string[]
  impression: string[]
  uncertainty: string[]
}

export interface Measurement {
  name: string
  value_text: string
  unit: string | null
  reference_range_text: string | null
  /** Against the printed range; null when in range or no range is printed. */
  flag: 'high' | 'low' | null
  unclear: boolean
}

/** Another test report (e.g. ECG): measurements, interpretations by source, visual content not read. */
export interface TestReportSummary {
  test_type: string | null
  test_name: string | null
  report_id: string | null
  facility_name: string | null
  report_form: 'typed' | 'handwritten' | 'machine printout' | 'unknown'
  test_date: string | null
  test_text: string | null
  measurements: Measurement[]
  interpretations: { source: 'machine' | 'physician' | 'other'; confirmed: boolean; text: string }[]
  visual_content: string[]
}

export type DocumentKind =
  | 'lab_report'
  | 'prescription'
  | 'discharge_summary'
  | 'consultation_note'
  | 'imaging_report'
  | 'test_report'
  | 'other'

/** How the text was obtained: the PDF's own text, OCR, OCR with some pages read from the image, or only images. */
export type ReadingMethod = 'digital' | 'ocr' | 'ocr+vision' | 'vision'

export interface ExtractionJob {
  status: JobStatus
  attempts: number
  error_category: string | null
  updated_at: string
  reading_method?: ReadingMethod | null
  /** Average OCR confidence over the pages read with OCR, 0–100. */
  ocr_confidence?: number | null
}

export interface DocumentExtraction {
  extraction_enabled: boolean
  media_type: string
  copy_type: CopyType | null
  job: ExtractionJob | null
  /** What the document was read as; null until extraction completes. */
  document_kind: DocumentKind | null
  items: Observation[]
  summary: LabSummary | null
  prescription: PrescriptionSummary | null
  discharge: DischargeSummary | null
  consultation: ConsultationSummary | null
  imaging: ImagingSummary | null
  test_report: TestReportSummary | null
}

const documentPath = (id: string) => `/documents/${encodeURIComponent(id)}`

export const extractionApi = {
  get: (documentId: string) => apiGet<DocumentExtraction>(`${documentPath(documentId)}/observations`),
  /** Read (again); a PDF can be switched to the other copy type. */
  request: (documentId: string, copyType?: CopyType | null) =>
    apiPost<DocumentExtraction>(`${documentPath(documentId)}/extract`, copyType ? { copy_type: copyType } : undefined),
  /** "Add as reminders": track the prescription's follow-ups on the Checkups and Follow-ups page. */
  addFollowUps: (documentId: string) => apiPost<DocumentExtraction>(`${documentPath(documentId)}/follow-ups`),
}

/** Plain-language reasons for a failed extraction (error_category values from the backend). */
export const FAILURE_MESSAGES: Record<string, string> = {
  ai_unavailable: 'The AI service was temporarily unavailable.',
  ai_not_configured: 'AI extraction is not set up on this server.',
  ai_refused: 'The AI service declined to process this document.',
  ai_request_rejected: 'The AI service could not accept this document.',
  ai_output_too_long: 'The document has more results than can be read in one pass.',
  ai_invalid_output: 'The AI response could not be understood.',
  ai_empty_output: 'Nothing could be read this time, although the document has content. Use Refresh analysis to try again.',
  image_too_large: 'This image is too large to process. Try a smaller photo or a PDF scan.',
  unreadable_image: 'This image could not be opened.',
  discharge_too_many_pages:
    'Discharge summaries can be one page only, due to AI reading limits. Please upload just the page with the diagnosis and discharge medicines.',
  too_many_pages: 'This scanned PDF has too many pages to read (the limit is 30).',
  document_too_long: 'This document is too long to read in one pass.',
  unreadable_pdf: 'This PDF could not be opened.',
  pdf_password_protected: 'This PDF is password-protected.',
  file_unavailable: 'The stored file could not be opened.',
  internal_error: 'Something went wrong while reading this document.',
}
