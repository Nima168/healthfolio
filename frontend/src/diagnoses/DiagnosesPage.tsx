import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { toFormErrors } from '../auth/formErrors'
import { HelperNote } from '../components/HelperNote'
import { SelectField } from '../components/SelectField'
import { formatDayMonthYear } from '../documents/format'
import { profileApi } from '../profile/profileApi'
import { diagnosesApi, type HealthIssue, type IssueKind } from './diagnosesApi'

const KIND_LABELS: Record<IssueKind, string> = {
  diagnosis: 'Diagnosis',
  assessment: 'Assessment',
  impression: 'Impression',
}
const KIND_SOURCES: Record<IssueKind, string> = {
  diagnosis: 'discharge summary',
  assessment: 'consultation note',
  impression: 'imaging report',
}
const STATUS_LABELS = { active: 'Active', resolved: 'Resolved', unknown: 'Status not set' } as const

const shownDate = (value: string | null) => (value ? formatDayMonthYear(value) : 'Date not mentioned')

function ProfileStatus({ issue, onAdd }: { issue: HealthIssue; onAdd: () => void }) {
  if (issue.profile === 'in_profile') {
    return (
      <span className="follow-up-tag">
        In Health Profile · {STATUS_LABELS[issue.condition_status ?? 'unknown']}
      </span>
    )
  }
  if (issue.profile === 'to_review') {
    return <Link to="/profile#suggestions-title">Review in Health Profile</Link>
  }
  return (
    <button type="button" className="button button-small button-secondary" onClick={onAdd}>
      Add to Health Profile
    </button>
  )
}

function IssueRow({ issue, onAdd }: { issue: HealthIssue; onAdd: () => void }) {
  const documents = new Set(issue.mentions.map((m) => m.document_id)).size
  const span =
    issue.first_seen && issue.last_seen && issue.first_seen !== issue.last_seen
      ? `${shownDate(issue.first_seen)} → ${shownDate(issue.last_seen)}`
      : shownDate(issue.last_seen)
  return (
    <li className="follow-up-row issue-row">
      <div className="issue-main">
        <p className="follow-up-title">{issue.name}</p>
        <p className="document-meta">
          {issue.kinds.map((kind) => (
            <span key={kind} className="timeline-category issue-kind">
              {KIND_LABELS[kind]}
            </span>
          ))}{' '}
          <span className="mono">{span}</span> · {documents} {documents === 1 ? 'document' : 'documents'}
        </p>
        <details className="issue-mentions">
          <summary>Where it is written</summary>
          <ul>
            {issue.mentions.map((mention, index) => (
              <li key={`${mention.document_id}-${index}`}>
                <span className="mono">{shownDate(mention.date)}</span> · {KIND_LABELS[mention.kind]} in{' '}
                <Link to={`/documents/${mention.document_id}`}>
                  {mention.document_title ?? `a ${KIND_SOURCES[mention.kind]}`}
                </Link>
                : “{mention.text}”
              </li>
            ))}
          </ul>
        </details>
      </div>
      <ProfileStatus issue={issue} onAdd={onAdd} />
    </li>
  )
}

export function DiagnosesPage() {
  const [items, setItems] = useState<HealthIssue[] | null>(null)
  const [kind, setKind] = useState<IssueKind | ''>('')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setItems((await diagnosesApi.list()).items)
      setError(null)
    } catch (e) {
      setError(toFormErrors(e, 'Your diagnoses and conditions could not be loaded.').general ?? null)
    }
  }, [])

  useEffect(() => {
    // Loading from the backend is an external sync; state is only set after the request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void load()
  }, [load])

  async function addToProfile(issue: HealthIssue) {
    try {
      // The document does not say whether it is ongoing, so the status is left for the user to set.
      await profileApi.addCondition(issue.name, 'unknown')
      await load()
    } catch (e) {
      setError(toFormErrors(e, 'It could not be added to your Health Profile.').general ?? null)
    }
  }

  // Normal findings ("Normal heart size.") are not health issues, so they are not listed (decision 2026-10-17).
  const issues = items?.filter((issue) => !issue.normal) ?? null
  const shown = issues?.filter((issue) => !kind || issue.kinds.includes(kind)) ?? null

  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">Diagnoses and Conditions</h1>
      <HelperNote>
        Health issues found in your documents, shown as written. The app does not diagnose; discuss them with your
        doctor.
      </HelperNote>

      {error && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}
      {items === null && !error && <p role="status">Loading diagnoses and conditions…</p>}

      {issues !== null && issues.length === 0 && (
        <div className="card empty-state">
          <p>
            <strong>No diagnoses or conditions found yet.</strong>
          </p>
          <p>
            They appear here once a discharge summary, consultation note, or imaging report is read in{' '}
            <Link to="/documents">Medical Documents</Link>.
          </p>
        </div>
      )}

      {issues !== null && issues.length > 0 && shown !== null && (
        <div className="card">
          <div className="issue-filters">
            <SelectField
              label="Show"
              value={kind}
              onChange={(e) => setKind(e.target.value as IssueKind | '')}
              options={[
                { value: '', label: 'All' },
                { value: 'diagnosis', label: 'Diagnoses (discharge summaries)' },
                { value: 'assessment', label: 'Assessments (consultation notes)' },
                { value: 'impression', label: 'Impressions (imaging reports)' },
              ]}
            />
          </div>
          {shown.length === 0 ? (
            <p className="document-meta">No health issues of this kind.</p>
          ) : (
            <ul className="follow-up-list" aria-label="Diagnoses and conditions">
              {shown.map((issue) => (
                <IssueRow key={issue.name} issue={issue} onAdd={() => void addToProfile(issue)} />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
