import type { Category, CopyType, DatePrecision, MedicalDocument } from './documentsApi'

/** Report type names. The stored values are unchanged, so documents already uploaded keep their type. */
export const CATEGORY_LABELS: Record<Category, string> = {
  lab_report: 'Laboratory reports',
  prescription: 'Prescription',
  discharge_summary: 'Discharge summary',
  consultation_note: 'Consultation note',
  imaging_report: 'Text-based imaging reports',
  pathology_report: 'Pathology reports',
  specialist_report: 'Specialist reports',
  other: 'Other', // no longer offered on upload; documents may still have it
  unknown: 'Not set',
}

/** The report types in the order they are offered; clinical documents and the other reports under headings. */
export const REPORT_TYPE_OPTIONS: { value: Exclude<Category, 'unknown' | 'other'>; label: string; group?: string }[] = [
  { value: 'lab_report', label: CATEGORY_LABELS.lab_report },
  { value: 'imaging_report', label: CATEGORY_LABELS.imaging_report },
  { value: 'prescription', label: CATEGORY_LABELS.prescription, group: 'Clinical Documents' },
  { value: 'discharge_summary', label: CATEGORY_LABELS.discharge_summary, group: 'Clinical Documents' },
  { value: 'consultation_note', label: CATEGORY_LABELS.consultation_note, group: 'Clinical Documents' },
  { value: 'pathology_report', label: CATEGORY_LABELS.pathology_report, group: 'Other' },
  { value: 'specialist_report', label: CATEGORY_LABELS.specialist_report, group: 'Other' },
]

export const PRECISION_LABELS: Record<DatePrecision, string> = {
  day: 'Exact day',
  month: 'Month only',
  year: 'Year only',
  unknown: 'Unsure',
}

/** Shown wherever a report leaves a value out. Nothing is assumed or filled in. */
export const NOT_MENTIONED = 'Not mentioned'
/** Printed in the document but not readable reliably: never replaced by a guess (backend readability rules). */
export const NOT_IDENTIFIED = 'Not identified'

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Show only as much of a date as is actually known, so a month is never shown as an exact day. */
export function formatPreciseDate(value: string | null, precision: DatePrecision | null): string {
  if (!value) return 'Not set'
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  const options: Intl.DateTimeFormatOptions =
    precision === 'year'
      ? { year: 'numeric', timeZone: 'UTC' }
      : precision === 'month'
        ? { year: 'numeric', month: 'long', timeZone: 'UTC' }
        : { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }
  const text = date.toLocaleDateString('en-GB', options)
  return precision === 'unknown' ? `${text} (unsure)` : text
}

export function formatDocumentDate(document: Pick<MedicalDocument, 'document_date' | 'document_date_precision'>): string {
  return formatPreciseDate(document.document_date, document.document_date_precision)
}

export function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
}

export function typeLabel(mediaType: string): string {
  return mediaType === 'application/pdf' ? 'PDF' : mediaType === 'image/png' ? 'PNG image' : 'JPEG image'
}

/** A known calendar day as "07-Oct-2026" (summaries); `value` is YYYY-MM-DD. */
export function formatDayMonthYear(value: string): string {
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  const monthName = date.toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' }).slice(0, 3)
  return `${String(day).padStart(2, '0')}-${monthName}-${year}`
}

/** Today's date in the user's time zone, as YYYY-MM-DD. */
export function todayIso(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

/** The upload question: digital PDF (text copied) or scanned copy (read with OCR). */
export const COPY_TYPE_LABELS: Record<CopyType, string> = {
  digital: 'Digital PDF',
  scanned: 'Scanned copy or photo',
}

const DOSE_TIMES = ['morning', 'afternoon', 'night'] as const
// "1-0-1": morning, afternoon, night; 1 = take it then, 0 = don't (dosing notation agreed 2026-10-17).
const DOSE_PATTERN = /(?<![\d.-]\s*)([01])\s*-\s*([01])\s*-\s*([01])(?!\s*-?\s*[\d.])/g

/** "1-0-1 after food" → "1-0-1 (morning and night) after food". Text is otherwise kept exactly as written. */
export function explainDosing(text: string): string {
  return text.replace(DOSE_PATTERN, (match, ...digits: string[]) => {
    const times = DOSE_TIMES.filter((_, index) => digits[index] === '1')
    if (times.length === 0) return match
    const meaning =
      times.length === 1
        ? `${times[0]} only`
        : times.length === 2
          ? `${times[0]} and ${times[1]}`
          : 'morning, afternoon, and night'
    return `${match} (${meaning})`
  })
}
