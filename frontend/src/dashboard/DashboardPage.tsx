import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { toFormErrors } from '../auth/formErrors'
import { HelperNote } from '../components/HelperNote'
import { CATEGORY_LABELS, formatDayMonthYear } from '../documents/format'
import { dashboardApi, type Dashboard, type LatestVital } from './dashboardApi'

const READING_LABELS: Record<string, string> = {
  pending: 'Waiting to be read',
  running: 'Being read',
  completed: 'Read',
  completed_with_warnings: 'Read',
  failed: 'Could not be read',
  cancelled: 'Not read',
}

const MISSING_LABELS: Record<string, string> = {
  date_of_birth: 'date of birth',
  sex: 'sex',
  blood_group: 'blood group',
  height: 'height',
  weight: 'weight',
}

const BMI_LABELS: Record<string, string> = {
  underweight: 'Underweight',
  healthy: 'Healthy weight',
  overweight: 'Overweight',
  obesity_1: 'Obesity (class 1)',
  obesity_2: 'Obesity (class 2)',
  obesity_3: 'Obesity (class 3, severe)',
}

const ACTIVITY_LABELS: Record<string, string> = {
  lab_results: 'Lab results',
  imaging: 'Imaging',
  test_reports: 'Test report',
  consultations: 'Consultation',
  hospital_stays: 'Hospital stay',
  prescriptions: 'Prescription',
  medications: 'Medication',
  follow_ups: 'Follow-up',
  vitals: 'Vital signs',
  documents: 'Document',
}

function Card({ title, link, linkLabel, children }: { title: string; link: string; linkLabel: string; children: ReactNode }) {
  const id = `card-${title.toLowerCase().replace(/[^a-z]+/g, '-')}`
  return (
    <section className="card dashboard-card" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      <div className="dashboard-card-body">{children}</div>
      <Link to={link} className="dashboard-card-link">
        {linkLabel} →
      </Link>
    </section>
  )
}

function vitalText(vital: LatestVital) {
  return (
    <>
      <strong>
        {vital.value} {vital.unit}
      </strong>{' '}
      <span className="mono">
        {formatDayMonthYear(vital.measured_on)}
        {vital.measured_time ? ` ${vital.measured_time}` : ''}
      </span>
    </>
  )
}

export function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await dashboardApi.get())
      setError(null)
    } catch (e) {
      setError(toFormErrors(e, 'Your overview could not be loaded.').general ?? null)
    }
  }, [])

  useEffect(() => {
    // Loading from the backend is an external sync; state is only set after the request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void load()
  }, [load])

  if (!data) {
    return (
      <section aria-labelledby="page-title">
        <h1 id="page-title">Dashboard</h1>
        {error ? (
          <p role="alert" className="form-alert">
            {error}
          </p>
        ) : (
          <p role="status">Loading your overview…</p>
        )}
      </section>
    )
  }

  const reviewItems: { text: string; link: string }[] = [
    ...(data.profile_suggestions
      ? [{ text: `${data.profile_suggestions} diagnosis suggestion${data.profile_suggestions === 1 ? '' : 's'} from your documents`, link: '/profile#suggestions-title' }]
      : []),
    ...(data.unconfirmed_medicines
      ? [{ text: `${data.unconfirmed_medicines} medicine${data.unconfirmed_medicines === 1 ? '' : 's'} not yet confirmed as taking or stopped`, link: '/medications' }]
      : []),
    ...data.follow_ups_to_add.map((d) => ({
      text: `${d.count} follow-up${d.count === 1 ? '' : 's'} to add from “${d.title ?? 'a document'}”`,
      link: `/documents/${d.id}`,
    })),
    ...data.failed_documents.map((d) => ({ text: `“${d.title ?? 'A document'}” could not be read`, link: `/documents/${d.id}` })),
  ]

  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">Dashboard</h1>
      <HelperNote>A quick overview of your records and what needs your attention.</HelperNote>

      {data.alerts_urgent > 0 && (
        <Link to="/alerts" className="dashboard-urgent" role="alert">
          {data.alerts_urgent} urgent alert{data.alerts_urgent === 1 ? '' : 's'}: open Alerts now →
        </Link>
      )}

      {data.documents_total === 0 && (
        <div className="card empty-state dashboard-start">
          <p>
            <strong>Get started by uploading a medical report.</strong>
          </p>
          <p>
            Go to <Link to="/documents">Medical Documents</Link> and upload reports.
          </p>
        </div>
      )}

      <div className="dashboard-grid">
        <Card title="Alerts" link="/alerts" linkLabel="View alerts">
          {data.alerts_open === 0 ? (
            <p>
              No open alerts.{' '}
              <span className="document-meta">This is not a health check; only the listed rules are applied.</span>
            </p>
          ) : (
            <>
              <p className="dashboard-count">
                <strong>{data.alerts_open}</strong> open{data.alerts_acknowledged ? ` · ${data.alerts_acknowledged} acknowledged` : ''}
              </p>
              <ul className="dashboard-list">
                {data.top_alerts.map((alert) => (
                  <li key={alert.id}>
                    {alert.severity === 'urgent' && <span className="dashboard-tag dashboard-tag-alert">Urgent</span>} {alert.title}
                    {alert.source_document_title && <span className="document-meta"> · {alert.source_document_title}</span>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>

        <Card title="To review" link="/profile" linkLabel="Open health profile">
          {reviewItems.length === 0 ? (
            <p>Nothing to review right now.</p>
          ) : (
            <ul className="dashboard-list">
              {reviewItems.map((item) => (
                <li key={item.text}>
                  <Link to={item.link}>{item.text}</Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Checkups and follow-ups" link="/follow-ups" linkLabel="View follow-ups">
          {data.overdue_follow_ups.length === 0 && data.upcoming_follow_ups.length === 0 ? (
            <p>Nothing overdue or due in the next 30 days.</p>
          ) : (
            <ul className="dashboard-list">
              {data.overdue_follow_ups.map((f) => (
                <li key={f.id}>
                  <span className="dashboard-tag dashboard-tag-alert">Overdue</span> <span className="mono">{formatDayMonthYear(f.due_date)}</span> · {f.title}
                </li>
              ))}
              {data.upcoming_follow_ups.map((f) => (
                <li key={f.id}>
                  <span className="mono">{formatDayMonthYear(f.due_date)}</span> · {f.title}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Recent documents" link="/documents" linkLabel="All documents">
          {data.recent_documents.length === 0 ? (
            <p>No documents yet.</p>
          ) : (
            <>
              {data.documents_reading > 0 && (
                <p className="document-meta">
                  {data.documents_reading} document{data.documents_reading === 1 ? ' is' : 's are'} being read.
                </p>
              )}
              <ul className="dashboard-list">
                {data.recent_documents.map((d) => (
                  <li key={d.id}>
                    <Link to={`/documents/${d.id}`}>{d.title ?? 'Untitled'}</Link>{' '}
                    <span className="document-meta">· {CATEGORY_LABELS[d.category]}</span>{' '}
                    <span className={`dashboard-tag${d.reading_status === 'failed' ? ' dashboard-tag-alert' : ''}`}>
                      {d.reading_status ? (READING_LABELS[d.reading_status] ?? d.reading_status) : 'Not read'}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>

        <Card title="Health profile" link="/profile" linkLabel="Open health profile">
          <ul className="dashboard-list dashboard-facts">
            <li>
              Personal data: <strong>{data.profile_filled} of {data.profile_total}</strong> filled
              {data.profile_missing.length > 0 && (
                <span className="document-meta"> · missing {data.profile_missing.map((m) => MISSING_LABELS[m] ?? m).join(', ')}</span>
              )}
            </li>
            <li>
              Allergies:{' '}
              {data.allergies.length ? <strong className="dashboard-allergies">{data.allergies.join(', ')}</strong> : <span className="document-meta">none recorded</span>}
            </li>
            <li>
              BMI:{' '}
              {data.bmi !== null ? (
                <>
                  <strong>{data.bmi.toFixed(1)}</strong>
                  {data.bmi_category && <span className="document-meta"> · {BMI_LABELS[data.bmi_category]}</span>}
                </>
              ) : (
                <span className="document-meta">needs height and weight</span>
              )}
            </li>
            <li>Blood pressure: {data.latest_blood_pressure ? vitalText(data.latest_blood_pressure) : <span className="document-meta">no reading</span>}</li>
            <li>Heart rate: {data.latest_heart_rate ? vitalText(data.latest_heart_rate) : <span className="document-meta">no reading</span>}</li>
            <li>
              {data.conditions} condition{data.conditions === 1 ? '' : 's'} · {data.active_medications} active medicine
              {data.active_medications === 1 ? '' : 's'}
            </li>
          </ul>
        </Card>

        <Card title="Recent activity" link="/timeline" linkLabel="Open timeline">
          {data.recent_activity.length === 0 ? (
            <p>Nothing recorded yet.</p>
          ) : (
            <ul className="dashboard-list">
              {data.recent_activity.map((entry) => (
                <li key={entry.id}>
                  <span className="mono">{entry.date ? formatDayMonthYear(entry.date) : '—'}</span>{' '}
                  <span className="document-meta">{ACTIVITY_LABELS[entry.category] ?? entry.category}</span> ·{' '}
                  {entry.link ? <Link to={entry.link}>{entry.title}</Link> : entry.title}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </section>
  )
}
