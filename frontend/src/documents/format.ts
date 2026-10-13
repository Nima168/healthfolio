import type { Category, DatePrecision, MedicalDocument } from './documentsApi'

export const CATEGORY_LABELS: Record<Category, string> = {
  lab_report: 'Lab report',
  prescription: 'Prescription',
  discharge_summary: 'Discharge summary',
  consultation_note: 'Consultation note',
  imaging_report: 'Imaging report',
  other: 'Other',
  unknown: 'Not set',
}

export const PRECISION_LABELS: Record<DatePrecision, string> = {
  day: 'Exact day',
  month: 'Month only',
  year: 'Year only',
  unknown: 'Unsure',
}

/** Shown wherever a report leaves a value out. Nothing is assumed or filled in. */
export const NOT_MENTIONED = 'Not mentioned'

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
