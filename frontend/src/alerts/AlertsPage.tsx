import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { toFormErrors } from '../auth/formErrors'
import { FormField } from '../components/FormField'
import { SelectField } from '../components/SelectField'
import type { Category } from '../documents/documentsApi'
import { CATEGORY_LABELS, formatDayMonthYear, formatTimestamp } from '../documents/format'
import { alertsApi, type AlertHistoryEvent, type AlertStatus, type SafetyAlert } from './alertsApi'
import { HelperNote } from '../components/HelperNote'

const SEVERITY_LABELS: Record<SafetyAlert['severity'], string> = {
  urgent: 'Urgent',
  warning: 'For review',
  info: 'Information',
}

const EVENT_LABELS: Record<AlertHistoryEvent['event'], string> = {
  raised: 'Raised',
  acknowledged: 'Acknowledged',
  resolved: 'Resolved',
  reopened: 'Reopened',
}

const GROUPS: { status: AlertStatus; title: string }[] = [
  { status: 'open', title: 'Open' },
  { status: 'acknowledged', title: 'Acknowledged' },
  { status: 'resolved', title: 'Resolved' },
]

/** Report types as read (test_report is not an upload type), else the upload type's label. */
function typeLabel(type: string | null): string {
  if (!type) return 'Deleted document'
  if (type === 'test_report') return 'Test report (ECG etc.)'
  return CATEGORY_LABELS[type as Category] ?? type
}

interface AlertFilters {
  type: string
  dateFrom: string
  dateTo: string
}

/** A date filter leaves out alerts whose report has no known date. */
function matches(alert: SafetyAlert, filters: AlertFilters): boolean {
  if (filters.type && (alert.report_type ?? '') !== filters.type) return false
  if (filters.dateFrom && (!alert.report_date || alert.report_date < filters.dateFrom)) return false
  if (filters.dateTo && (!alert.report_date || alert.report_date > filters.dateTo)) return false
  return true
}

const reportName = (alert: SafetyAlert) => alert.source_document_title ?? 'Deleted document'

/** Alerts from the same report sit together; reports A to Z, then by result. */
const byReport = (a: SafetyAlert, b: SafetyAlert) =>
  reportName(a).localeCompare(reportName(b)) || a.title.localeCompare(b.title)

type Panel = { id: string; mode: 'details' | 'resolve' } | null

function DetailsPanel({ alert }: { alert: SafetyAlert }) {
  return (
    <div className="alert-panel">
      <p>{alert.reason}</p>
      {alert.explanation_text && (
        <p>
          <strong>AI explanation (generated, not a rule):</strong> {alert.explanation_text}
        </p>
      )}
      {alert.status === 'resolved' && (
        <p className="document-meta">
          {alert.resolved_by === 'system' ? `Resolved automatically: ${alert.resolution_note ?? ''}` : 'Resolved by you'}
          {alert.resolved_by === 'user' && alert.resolution_note ? `: ${alert.resolution_note}` : ''} Resolving an alert does
          not mean the result is normal.
        </p>
      )}
      <ul className="history-list">
        {alert.history.map((event, index) => (
          <li key={index}>
            <span className="mono">{formatTimestamp(event.occurred_at)}</span> · {EVENT_LABELS[event.event]}{' '}
            {event.actor === 'system' ? '(automatically)' : '(by you)'}
            {event.note ? ` — ${event.note}` : ''}
          </li>
        ))}
      </ul>
      <p className="document-meta">
        Rule <span className="mono">{alert.rule_code} v{alert.rule_version}</span>: {alert.rule_description}
      </p>
    </div>
  )
}

function ResolvePanel({ onResolve, onCancel }: { onResolve: (note: string) => Promise<void>; onCancel: () => void }) {
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  return (
    <div className="alert-panel" role="group" aria-label="Resolve this alert">
      <p>Mark this alert as resolved once you have dealt with it. This does not mean the result is normal.</p>
      <FormField label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} />
      <div className="button-row">
        <button
          type="button"
          className="button button-small"
          disabled={saving}
          onClick={() => {
            setSaving(true)
            void onResolve(note.trim()).finally(() => setSaving(false))
          }}
        >
          Resolve
        </button>
        <button type="button" className="button button-small button-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}

function AlertRows({
  alert,
  panel,
  setPanel,
  update,
}: {
  alert: SafetyAlert
  panel: Panel
  setPanel: (panel: Panel) => void
  update: (status: 'acknowledged' | 'resolved', note?: string) => Promise<void>
}) {
  const open = panel?.id === alert.id ? panel.mode : null
  const toggle = (mode: 'details' | 'resolve') => setPanel(open === mode ? null : { id: alert.id, mode })
  return (
    <>
      <tr>
        <th scope="row">
          <span className="alert-result">{alert.title}</span>
        </th>
        <td>
          {alert.source_document_id && alert.source_document_title ? (
            <Link to={`/documents/${alert.source_document_id}`}>{alert.source_document_title}</Link>
          ) : (
            <span className="document-meta">Deleted document</span>
          )}
        </td>
        <td className="mono">{alert.report_date ? formatDayMonthYear(alert.report_date) : '—'}</td>
        <td>
          <span className={`alert-severity alert-severity-${alert.severity}`}>{SEVERITY_LABELS[alert.severity]}</span>
        </td>
        <td className="mono">{formatDayMonthYear(alert.created_at.slice(0, 10))}</td>
        <td>
          <div className="alert-actions">
            {alert.status === 'open' && (
              <button type="button" className="button button-small" onClick={() => void update('acknowledged')}>
                Acknowledge
              </button>
            )}
            {alert.status !== 'resolved' && (
              <button
                type="button"
                className="button button-small button-secondary"
                aria-expanded={open === 'resolve'}
                onClick={() => toggle('resolve')}
              >
                Resolve
              </button>
            )}
            <button
              type="button"
              className="button button-small button-secondary"
              aria-expanded={open === 'details'}
              onClick={() => toggle('details')}
            >
              Details
            </button>
          </div>
        </td>
      </tr>
      {open && (
        <tr className="alert-panel-row">
          <td colSpan={6}>
            {open === 'details' ? (
              <DetailsPanel alert={alert} />
            ) : (
              <ResolvePanel
                onResolve={async (note) => {
                  await update('resolved', note || undefined)
                  setPanel(null)
                }}
                onCancel={() => setPanel(null)}
              />
            )}
          </td>
        </tr>
      )}
    </>
  )
}

function AlertTable({
  alerts,
  caption,
  panel,
  setPanel,
  update,
}: {
  alerts: SafetyAlert[]
  caption: string
  panel: Panel
  setPanel: (panel: Panel) => void
  update: (id: string, status: 'acknowledged' | 'resolved', note?: string) => Promise<void>
}) {
  return (
    <div className="card document-table-wrap">
      <table className="document-table alert-table">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Result</th>
            <th scope="col">Report</th>
            <th scope="col">Report date</th>
            <th scope="col">Type</th>
            <th scope="col">Raised</th>
            <th scope="col">
              <span className="visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {[...alerts].sort(byReport).map((alert) => (
            <AlertRows
              key={alert.id}
              alert={alert}
              panel={panel}
              setPanel={setPanel}
              update={(status, note) => update(alert.id, status, note)}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function AlertsPage() {
  const [items, setItems] = useState<SafetyAlert[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [panel, setPanel] = useState<Panel>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const query = searchParams.toString()
  const filters: AlertFilters = useMemo(() => {
    const params = new URLSearchParams(query)
    return { type: params.get('type') ?? '', dateFrom: params.get('from') ?? '', dateTo: params.get('to') ?? '' }
  }, [query])
  const datesInOrder = !filters.dateFrom || !filters.dateTo || filters.dateFrom <= filters.dateTo
  const filtered = Boolean(filters.type || filters.dateFrom || filters.dateTo)

  function change(next: Partial<AlertFilters>) {
    const merged = { ...filters, ...next }
    const params = new URLSearchParams()
    if (merged.type) params.set('type', merged.type)
    if (merged.dateFrom) params.set('from', merged.dateFrom)
    if (merged.dateTo) params.set('to', merged.dateTo)
    setSearchParams(params, { replace: true })
  }

  // Only the report types that have alerts are offered.
  const types = [...new Set((items ?? []).map((item) => item.report_type ?? ''))].sort((a, b) =>
    typeLabel(a || null).localeCompare(typeLabel(b || null)),
  )
  const shown = (items ?? []).filter((item) => datesInOrder && matches(item, filters))

  const load = useCallback(async () => {
    try {
      setItems((await alertsApi.list()).items)
      setError(null)
    } catch (e) {
      setError(toFormErrors(e, 'Your alerts could not be loaded.').general ?? null)
    }
  }, [])

  useEffect(() => {
    // Loading from the backend is an external sync; state is only set after the request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void load()
  }, [load])

  async function update(id: string, status: 'acknowledged' | 'resolved', note?: string) {
    try {
      const updated = await alertsApi.update(id, status, note)
      setItems((current) => current?.map((item) => (item.id === id ? updated : item)) ?? null)
      setError(null)
    } catch (e) {
      setError(toFormErrors(e, 'The alert could not be updated.').general ?? null)
    }
  }

  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">Alerts</h1>
      <HelperNote>Flags results outside their report's printed range, for review with your doctor.</HelperNote>
      {/* Always shown, never generated: urgent guidance must not wait for anything. */}
      <div className="alert-safety-note" role="note">
        <p>
          <strong>If you feel very unwell or think it may be an emergency, call your local emergency number now.</strong> Having
          no alerts does not mean you are healthy.
        </p>
      </div>

      {error && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}
      {items === null && !error && <p role="status">Loading alerts…</p>}

      {items !== null && items.length > 0 && (
        <div className="card document-filters" role="search" aria-label="Filter alerts">
          <SelectField
            label="Report type"
            value={filters.type}
            onChange={(e) => change({ type: e.target.value })}
            options={[{ value: '', label: 'All types' }, ...types.map((type) => ({ value: type, label: typeLabel(type || null) }))]}
          />
          <FormField label="Report date from" type="date" value={filters.dateFrom} onChange={(e) => change({ dateFrom: e.target.value })} />
          <FormField
            label="Report date to"
            type="date"
            value={filters.dateTo}
            onChange={(e) => change({ dateTo: e.target.value })}
            error={datesInOrder ? undefined : 'The end date cannot be before the start date.'}
          />
          {filtered && (
            <button type="button" className="button button-secondary filters-clear" onClick={() => setSearchParams(new URLSearchParams(), { replace: true })}>
              Clear filters
            </button>
          )}
          {(filters.dateFrom || filters.dateTo) && (
            <p className="document-meta filters-note">Alerts whose report has no known date are not shown while a date filter is set.</p>
          )}
        </div>
      )}

      {items !== null && items.length > 0 && filtered && shown.length === 0 && (
        <div className="card empty-state">
          <p>
            <strong>No alerts match these filters.</strong>
          </p>
        </div>
      )}

      {items !== null && items.length === 0 && (
        <div className="card empty-state">
          <p>
            <strong>No alerts.</strong>
          </p>
          <p>The rules found nothing to flag in your records. This is not a health check.</p>
        </div>
      )}

      {items !== null &&
        GROUPS.map((group) => {
          const alerts = shown.filter((item) => item.status === group.status)
          if (alerts.length === 0) return null
          const headingId = `alerts-${group.status}`
          const table = (
            <AlertTable alerts={alerts} caption={`${group.title} alerts`} panel={panel} setPanel={setPanel} update={update} />
          )
          return (
            <section key={group.status} className="alert-group" aria-labelledby={headingId}>
              <h2 id={headingId}>
                {group.title} <span className="count">({alerts.length})</span>
              </h2>
              {group.status === 'resolved' ? (
                <details>
                  <summary>Show resolved alerts</summary>
                  {table}
                </details>
              ) : (
                table
              )}
            </section>
          )
        })}
    </section>
  )
}
