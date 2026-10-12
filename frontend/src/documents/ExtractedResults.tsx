import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { toFormErrors } from '../auth/formErrors'
import {
  extractionApi,
  FAILURE_MESSAGES,
  type ConsultationSummary,
  type DischargeSummary,
  type DocumentExtraction,
  type FollowUpLine,
  type ImagingSummary,
  type KeyResult,
  type JobStatus,
  type LabSummary,
  type MedicationLine,
  type PrescriptionSummary,
  type SummaryLine,
  type TestReportSummary,
} from './extractionApi'
import { formatDayMonthYear, todayIso } from './format'

const TITLES = {
  lab_report: 'Extracted lab results',
  prescription: 'Prescription summary',
  discharge_summary: 'Discharge summary',
  consultation_note: 'Consultation summary',
  imaging_report: 'Imaging summary',
  test_report: 'Test report summary',
  other: 'Extracted information',
}

const POLL_MS = 3000
const ACTIVE: JobStatus[] = ['pending', 'running']

// ---------- summary in the agreed plain-text format ----------

function ValueLines({ lines, critical = false }: { lines: SummaryLine[]; critical?: boolean }) {
  if (lines.length === 0) return <p className="summary-none">None</p>
  return (
    <ul className={`summary-lines${critical ? ' summary-critical' : ''}`}>
      {lines.map((line, index) => (
        <li key={`${line.name}-${index}`}>
          {line.name}: {line.value_text}
          {line.unit && ` ${line.unit}`} (Reference: {line.reference_range_text ?? 'not printed'})
        </li>
      ))}
    </ul>
  )
}

function SummaryBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="summary-block">
      <p className="summary-heading">{title}:</p>
      {children}
    </div>
  )
}

function LabSummaryText({ summary }: { summary: LabSummary }) {
  return (
    <div className="lab-summary">
      <p className="summary-heading">Report Date: {summary.report_date ?? 'Not available'}</p>
      <SummaryBlock title="Values Above Range">
        <ValueLines lines={summary.above} critical />
      </SummaryBlock>
      <SummaryBlock title="Values Below Range">
        <ValueLines lines={summary.below} critical />
      </SummaryBlock>
      <SummaryBlock title="Normal Values">
        <ValueLines lines={summary.normal} />
      </SummaryBlock>
      {summary.invalid.length > 0 && (
        <SummaryBlock title="Invalid Records">
          <ValueLines lines={summary.invalid} />
        </SummaryBlock>
      )}
    </div>
  )
}

// ---------- prescription summary in the agreed plain-text format ----------

function UnclearTag({ reason }: { reason: string | null }) {
  return (
    <span className="unclear-tag" title={reason ?? undefined}>
      {' '}
      (unclear – check original)
    </span>
  )
}

/** Medicine name and strength stand out; how and how long follow in plain text. */
function MedicationText({ line }: { line: MedicationLine }) {
  const name = line.strength && !line.name.endsWith(line.strength) ? `${line.name} ${line.strength}` : line.name
  const details = [line.instructions, line.duration_text].filter(Boolean).join(', ')
  return (
    <>
      <strong>{name}</strong>
      {details && `: ${details}`}
      {line.unclear && <UnclearTag reason={line.reason} />}
    </>
  )
}

function prescriptionHeading(summary: PrescriptionSummary): string {
  const date = summary.prescribed_on
    ? formatDayMonthYear(summary.prescribed_on)
    : (summary.date_text ?? 'Date not available')
  return `PRESCRIPTION SUMMARY — ${date}${summary.prescriber_name ? ` (${summary.prescriber_name})` : ''}`
}

function MedicationsBlock({ title, lines }: { title: string; lines: MedicationLine[] }) {
  return (
    <div className="summary-block">
      <p className="summary-heading">{title}</p>
      {lines.length === 0 ? (
        <p className="summary-none">None</p>
      ) : (
        <ul className="summary-lines">
          {lines.map((line, index) => (
            <li key={`${line.name}-${index}`}>
              <MedicationText line={line} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

interface AddFollowUps {
  reminders: 'available' | 'added' | 'none'
  onAdd: () => void
  adding: boolean
  addError: string | null
}

function FollowUpsBlock({
  lines,
  add,
  title = 'Upcoming Follow-Ups',
}: {
  lines: FollowUpLine[]
  add: AddFollowUps
  title?: string
}) {
  const today = todayIso()
  return (
    <div className="summary-block">
      <p className="summary-heading">{title}</p>
      {lines.length === 0 ? (
        <p className="summary-none">None</p>
      ) : (
        <ul className="summary-lines">
          {lines.map((line, index) => (
            <li key={`${line.due_date ?? 'undated'}-${index}`}>
              <strong>{line.due_date ? formatDayMonthYear(line.due_date) : (line.when_text ?? 'Date not clear')}</strong>:{' '}
              {line.description}
              {!line.due_date && !line.unclear && <span className="summary-past"> (no exact date)</span>}
              {line.due_date && line.due_date < today && <span className="summary-past"> (date has passed)</span>}
              {line.unclear && <UnclearTag reason={line.reason} />}
            </li>
          ))}
        </ul>
      )}
      {add.reminders === 'available' && (
        <p className="reminder-prompt">
          <button type="button" className="button button-small" onClick={add.onAdd} disabled={add.adding}>
            {add.adding ? 'Adding…' : 'Add to Checkups and Follow-ups'}
          </button>
          <span className="form-hint">Only clear, dated follow-ups are added.</span>
        </p>
      )}
      {add.reminders === 'added' && (
        <p className="reminder-prompt">
          ✓ Added to <Link to="/follow-ups">Checkups and Follow-ups</Link>
        </p>
      )}
      {add.addError && (
        <p role="alert" className="form-error">
          {add.addError}
        </p>
      )}
    </div>
  )
}

function PrescriptionSummaryText({ summary, add }: { summary: PrescriptionSummary; add: AddFollowUps }) {
  return (
    <div className="lab-summary prescription-summary">
      <p className="summary-title">{prescriptionHeading(summary)}</p>
      <MedicationsBlock title="Medications" lines={summary.medications} />
      <FollowUpsBlock lines={summary.follow_ups} add={add} />
    </div>
  )
}

// ---------- discharge summary in the agreed plain-text format ----------

/** "10-Aug" for "last tested" (the year is the stay's). */
function dayMonth(value: string): string {
  return formatDayMonthYear(value).slice(0, 6)
}

function stayLine(summary: DischargeSummary): string | null {
  const admitted = summary.admitted_on ? formatDayMonthYear(summary.admitted_on) : summary.admitted_text
  const discharged = summary.discharged_on ? formatDayMonthYear(summary.discharged_on) : summary.discharged_text
  if (!admitted && !discharged) return null
  const days = summary.stay_days ? ` (${summary.stay_days} ${summary.stay_days === 1 ? 'day' : 'days'})` : ''
  return `Admitted ${admitted ?? 'date not available'} → Discharged ${discharged ?? 'date not available'}${days}`
}

function KeyResultText({ result }: { result: KeyResult }) {
  const values = result.first_value ? `${result.first_value} → ${result.last_value}` : result.last_value
  const notes = [
    result.flag && `${result.still ? 'still ' : ''}${result.flag}`,
    result.last_tested && `last tested ${dayMonth(result.last_tested)}`,
  ].filter(Boolean)
  return (
    <>
      <strong>{result.name}</strong>: {values}
      {result.unit && ` ${result.unit}`}
      {result.reference_range_text && ` (ref ${result.reference_range_text})`}
      {notes.length > 0 && <span className="key-result-flag"> — {notes.join(', ')}</span>}
      {result.unclear && <UnclearTag reason="Part of this result was not clearly legible." />}
    </>
  )
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="summary-block">
      <p className="summary-heading">{title}</p>
      {items.length === 0 ? (
        <p className="summary-none">None</p>
      ) : (
        <ul className="summary-lines">
          {items.map((item, index) => (
            <li key={`${item}-${index}`}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function DischargeSummaryText({ summary, add }: { summary: DischargeSummary; add: AddFollowUps }) {
  const stay = stayLine(summary)
  return (
    <div className="lab-summary discharge-summary">
      <p className="summary-title">DISCHARGE SUMMARY{summary.facility_name ? ` — ${summary.facility_name}` : ''}</p>
      {stay && <p className="summary-stay">{stay}</p>}
      <ListBlock title="Diagnosis" items={summary.diagnoses} />
      <div className="summary-block">
        <p className="summary-heading">Key Results</p>
        {summary.key_results.length === 0 ? (
          <p className="summary-none">None</p>
        ) : (
          <ul className="summary-lines">
            {summary.key_results.map((result, index) => (
              <li key={`${result.name}-${index}`}>
                <KeyResultText result={result} />
              </li>
            ))}
          </ul>
        )}
      </div>
      <MedicationsBlock title="Discharge Medications" lines={summary.medications} />
      <FollowUpsBlock lines={summary.follow_ups} add={add} />
      {summary.warning_signs.length > 0 && (
        <div className="summary-block warning-signs">
          <p className="summary-heading">Return to Emergency If</p>
          <ul className="summary-lines">
            {summary.warning_signs.map((sign, index) => (
              <li key={`${sign}-${index}`}>{sign}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// ---------- consultation note, imaging report, other test report ----------

function datedHeading(title: string, iso: string | null, printed: string | null, who: string | null): string {
  const date = iso ? formatDayMonthYear(iso) : printed
  const parts = [date, who && `(${who})`].filter(Boolean).join(' ')
  return parts ? `${title} — ${parts}` : title
}

function ConsultationSummaryText({ summary, add }: { summary: ConsultationSummary; add: AddFollowUps }) {
  return (
    <div className="lab-summary consultation-summary">
      <p className="summary-title">
        {datedHeading('CONSULTATION SUMMARY', summary.visit_date, summary.visit_text, summary.clinician_name)}
      </p>
      <ListBlock title="Symptoms" items={summary.symptoms} />
      <ListBlock title="Observations" items={summary.observations} />
      <ListBlock title="Assessment" items={summary.assessment} />
      <ListBlock title="Plan" items={summary.plan} />
      <FollowUpsBlock title="Follow-Up" lines={summary.follow_ups} add={add} />
    </div>
  )
}

function ImagingSummaryText({ summary }: { summary: ImagingSummary }) {
  if (!summary.is_written_report) {
    return (
      <p className="field-note">
        This looks like scan images without a written report. Reading scan images is planned for a later update;
        please upload the radiologist's written report.
      </p>
    )
  }
  const source = [summary.report_id, summary.facility_name && `(${summary.facility_name})`].filter(Boolean).join(' ')
  const examDate = summary.exam_date ? formatDayMonthYear(summary.exam_date) : summary.exam_text
  const reportDate = summary.report_date ? formatDayMonthYear(summary.report_date) : summary.report_text
  return (
    <div className="lab-summary imaging-summary">
      <p className="summary-title">IMAGING SUMMARY{summary.exam_name ? ` — ${summary.exam_name}` : ''}</p>
      <p className="summary-stay">Source: Written report{source ? ` ${source}` : ''}</p>
      {examDate && (
        <p className="summary-stay">
          Examination Date: {examDate}
          {reportDate && reportDate !== examDate && ` (reported ${reportDate})`}
        </p>
      )}
      {summary.body_region && <p className="summary-stay">Body Region: {summary.body_region}</p>}
      <ListBlock title="Findings" items={summary.findings} />
      <ListBlock title="Impression" items={summary.impression} />
      <ListBlock title="Uncertainty" items={summary.uncertainty} />
    </div>
  )
}

const SOURCE_LABELS = { machine: 'Machine', physician: 'Physician', other: 'Other' } as const

function TestReportSummaryText({ summary }: { summary: TestReportSummary }) {
  const type = summary.test_type ? summary.test_type.toUpperCase() : 'TEST'
  const form = summary.report_form !== 'unknown' ? `${summary.report_form} report` : null
  const facility = summary.facility_name && `(${summary.facility_name})`
  const source = [[summary.report_id, facility].filter(Boolean).join(' '), form].filter(Boolean).join(', ')
  const date = summary.test_text ?? (summary.test_date ? formatDayMonthYear(summary.test_date) : null)
  return (
    <div className="lab-summary test-report-summary">
      <p className="summary-title">
        {type} SUMMARY{summary.test_name ? ` — ${summary.test_name}` : ''}
      </p>
      {source && <p className="summary-stay">Source: {source}</p>}
      {date && <p className="summary-stay">Date: {date}</p>}
      <div className="summary-block">
        <p className="summary-heading">Reported Measurements</p>
        {summary.measurements.length === 0 ? (
          <p className="summary-none">None</p>
        ) : (
          <ul className="summary-lines">
            {summary.measurements.map((m, index) => (
              <li key={`${m.name}-${index}`}>
                <strong>{m.name}</strong> {m.value_text}
                {m.unit && (m.unit === '°' ? m.unit : ` ${m.unit}`)} ({m.reference_range_text ?? 'no range given'})
                {m.flag && <span className="key-result-flag"> — {m.flag}</span>}
                {m.unclear && <UnclearTag reason="This value was not clearly legible." />}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="summary-block">
        <p className="summary-heading">Interpretation</p>
        {summary.interpretations.length === 0 ? (
          <p className="summary-none">None</p>
        ) : (
          <ul className="summary-lines">
            {summary.interpretations.map((item, index) => (
              <li key={`${item.source}-${index}`}>
                <strong>
                  {SOURCE_LABELS[item.source]}
                  {item.confirmed && ' (confirmed)'}
                </strong>
                : {item.text}
              </li>
            ))}
          </ul>
        )}
      </div>
      {summary.visual_content.length > 0 && (
        <div className="summary-block">
          <p className="summary-heading">Visual Content</p>
          <ul className="summary-lines">
            {summary.visual_content.map((item, index) => (
              <li key={`${item}-${index}`}>
                {item}: <span className="summary-past">not extracted (image only)</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function isEmptyPrescription(summary: PrescriptionSummary): boolean {
  return summary.medications.length === 0 && summary.follow_ups.length === 0
}

// ---------- section ----------

export function ExtractedResults({
  documentId,
  onStatusChange,
}: {
  documentId: string
  onStatusChange?: (status: JobStatus) => void
}) {
  const [data, setData] = useState<DocumentExtraction | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [requesting, setRequesting] = useState(false)
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)
  // Bumped to restart polling after a new extraction is requested.
  const [pollKey, setPollKey] = useState(0)

  const load = useCallback(async () => {
    try {
      const next = await extractionApi.get(documentId)
      setData(next)
      setLoadError(null)
      if (next.job) onStatusChange?.(next.job.status)
      return next
    } catch (error) {
      setLoadError(toFormErrors(error, 'Extracted results could not be loaded.').general ?? null)
      return null
    }
  }, [documentId, onStatusChange])

  // Load once, then keep refreshing while the job is waiting or running (and the server is extracting).
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    let active = true
    const tick = async () => {
      const next = await load()
      if (active && next?.job && ACTIVE.includes(next.job.status) && next.extraction_enabled) {
        timer = setTimeout(() => void tick(), POLL_MS)
      }
    }
    void tick()
    return () => {
      active = false
      if (timer) clearTimeout(timer)
    }
  }, [load, pollKey])

  async function requestExtraction() {
    setRequesting(true)
    try {
      const next = await extractionApi.request(documentId)
      setData(next)
      if (next.job) onStatusChange?.(next.job.status)
      setPollKey((key) => key + 1)
    } catch (error) {
      setLoadError(toFormErrors(error, 'Extraction could not be started.').general ?? null)
    } finally {
      setRequesting(false)
    }
  }

  async function addReminders() {
    setAdding(true)
    setAddError(null)
    try {
      setData(await extractionApi.addFollowUps(documentId))
    } catch (error) {
      setAddError(toFormErrors(error, 'The follow-ups could not be added.').general ?? null)
    } finally {
      setAdding(false)
    }
  }

  const job = data?.job
  const extractButton = (label: string) => (
    <button type="button" className="button button-small" onClick={() => void requestExtraction()} disabled={requesting}>
      {requesting ? 'Starting…' : label}
    </button>
  )

  // Reading varies from run to run, so an extraction that found nothing can be tried again.
  const emptyResult = (message: string) => (
    <div>
      <p>{message}</p>
      {data?.extraction_enabled && extractButton('Try again')}
    </div>
  )

  const addFollowUps: AddFollowUps = {
    reminders: data?.prescription?.reminders ?? 'none',
    onAdd: () => void addReminders(),
    adding,
    addError,
  }

  let body
  let showReadAgain = false
  if (!data) {
    body = loadError ? null : <p role="status">Loading extracted results…</p>
  } else if (!job) {
    body = data.extraction_enabled ? (
      <div>
        <p>Results have not been extracted from this document yet.</p>
        {extractButton('Extract results')}
      </div>
    ) : (
      <p>Automatic extraction is turned off on this server, so results are not read from documents yet.</p>
    )
  } else if (ACTIVE.includes(job.status)) {
    body = !data.extraction_enabled ? (
      <p role="status">Waiting to be read. Automatic extraction is currently turned off on this server.</p>
    ) : (
      <p role="status" className="processing-note">
        <span className="spinner" aria-hidden="true" />
        {job.status === 'running'
          ? 'Reading your document… This usually takes under a minute.'
          : job.attempts > 0
            ? 'Retrying after a temporary problem…'
            : 'Queued for reading…'}
      </p>
    )
  } else if (job.status === 'failed' || job.status === 'cancelled') {
    body = (
      <div>
        <p role="alert" className="form-alert">
          {job.status === 'cancelled'
            ? 'Extraction was cancelled.'
            : (FAILURE_MESSAGES[job.error_category ?? ''] ?? 'The results could not be extracted.')}
        </p>
        {extractButton('Try again')}
      </div>
    )
  } else if (data.document_kind === 'prescription' && data.prescription && !isEmptyPrescription(data.prescription)) {
    body = <PrescriptionSummaryText summary={data.prescription} add={addFollowUps} />
    showReadAgain = true
  } else if (data.document_kind === 'prescription') {
    body = emptyResult('No medicines or follow-ups were found in this prescription.')
  } else if (data.document_kind === 'discharge_summary' && data.discharge) {
    body = <DischargeSummaryText summary={data.discharge} add={{ ...addFollowUps, reminders: data.discharge.reminders }} />
    showReadAgain = true
  } else if (data.document_kind === 'consultation_note' && data.consultation) {
    body = (
      <ConsultationSummaryText summary={data.consultation} add={{ ...addFollowUps, reminders: data.consultation.reminders }} />
    )
    showReadAgain = true
  } else if (data.document_kind === 'imaging_report' && data.imaging) {
    body = <ImagingSummaryText summary={data.imaging} />
    showReadAgain = true
  } else if (data.document_kind === 'test_report' && data.test_report) {
    body = <TestReportSummaryText summary={data.test_report} />
    showReadAgain = true
  } else if (data.document_kind === 'other') {
    body = emptyResult(
      'This document does not look like a medical report the app can read yet, so nothing was extracted.',
    )
  } else if (data.items.length === 0) {
    body = emptyResult('No lab results were found in this document.')
  } else {
    body = data.summary ? <LabSummaryText summary={data.summary} /> : null
    showReadAgain = true
  }

  return (
    <section className="card extracted-results" aria-labelledby="results-title">
      <h2 id="results-title">{TITLES[data?.document_kind ?? 'lab_report']}</h2>
      {loadError && (
        <p role="alert" className="form-alert">
          {loadError}
        </p>
      )}
      {body}
      {showReadAgain && data?.extraction_enabled && (
        <p className="read-again">
          <button
            type="button"
            className="button button-small button-secondary"
            onClick={() => void requestExtraction()}
            disabled={requesting}
          >
            {requesting ? 'Starting…' : 'Read again'}
          </button>
          <span className="form-hint">
            Something missing? AI reading can vary, so the document can be read again. This replaces the summary;
            follow-ups you already added are kept.
          </span>
        </p>
      )}
    </section>
  )
}
