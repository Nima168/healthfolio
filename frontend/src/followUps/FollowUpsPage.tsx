import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { toFormErrors } from '../auth/formErrors'
import { formatDayMonthYear } from '../documents/format'
import { followUpsApi, type FollowUp, type FollowUpStatus } from './followUpsApi'
import { HelperNote } from '../components/HelperNote'

const KIND_LABELS: Record<FollowUp['kind'], string> = {
  investigation: 'Test',
  appointment: 'Doctor visit',
  checkup: 'Checkup',
}

const STATUS_LABELS: Record<Exclude<FollowUpStatus, 'scheduled'>, string> = {
  completed: 'Done',
  cancelled: 'Cancelled',
}

interface ReportGroup {
  key: string
  documentId: string | null
  title: string
  items: FollowUp[]
}

/** One group per source report; items in date order; the report with the soonest pending item first,
 * follow-ups from deleted reports last. */
function groupByReport(items: FollowUp[]): ReportGroup[] {
  const groups = new Map<string, ReportGroup>()
  for (const item of items) {
    const known = item.source_document_id && item.source_document_title
    const key = known ? (item.source_document_id as string) : 'none'
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        documentId: known ? item.source_document_id : null,
        title: known ? (item.source_document_title as string) : 'From a deleted document',
        items: [],
      })
    }
    groups.get(key)?.items.push(item)
  }
  const soonest = (group: ReportGroup) =>
    group.items.find((item) => item.status === 'scheduled')?.due_date ?? '9999-12-31'
  return [...groups.values()]
    .map((group) => ({ ...group, items: [...group.items].sort((a, b) => a.due_date.localeCompare(b.due_date)) }))
    .sort(
      (a, b) =>
        Number(a.documentId === null) - Number(b.documentId === null) || // deleted reports last
        soonest(a).localeCompare(soonest(b)) ||
        a.title.localeCompare(b.title),
    )
}

function FollowUpRow({ item, onChange }: { item: FollowUp; onChange: (status: FollowUpStatus) => void }) {
  const closed = item.status !== 'scheduled'
  return (
    <li className={`follow-up-row${item.overdue ? ' follow-up-overdue' : ''}${closed ? ' follow-up-closed' : ''}`}>
      <div>
        <p className="follow-up-title">
          <span className="mono">{formatDayMonthYear(item.due_date)}</span> · {item.title}
          {item.overdue && <span className="follow-up-tag follow-up-tag-overdue">Overdue</span>}
          {closed && <span className="follow-up-tag">{STATUS_LABELS[item.status as 'completed' | 'cancelled']}</span>}
        </p>
        <p className="document-meta">{KIND_LABELS[item.kind]}</p>
      </div>
      <div className="button-row">
        {closed ? (
          <button type="button" className="button button-small button-secondary" onClick={() => onChange('scheduled')}>
            Undo
          </button>
        ) : (
          <>
            <button type="button" className="button button-small" onClick={() => onChange('completed')}>
              Mark done
            </button>
            <button type="button" className="button button-small button-secondary" onClick={() => onChange('cancelled')}>
              Cancel
            </button>
          </>
        )}
      </div>
    </li>
  )
}

export function FollowUpsPage() {
  const [items, setItems] = useState<FollowUp[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setItems((await followUpsApi.list()).items)
      setError(null)
    } catch (e) {
      setError(toFormErrors(e, 'Your follow-ups could not be loaded.').general ?? null)
    }
  }, [])

  useEffect(() => {
    // Loading from the backend is an external sync; state is only set after the request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void load()
  }, [load])

  async function change(id: string, status: FollowUpStatus) {
    try {
      const updated = await followUpsApi.setStatus(id, status)
      setItems((current) => current?.map((item) => (item.id === id ? updated : item)) ?? null)
      setError(null)
    } catch (e) {
      setError(toFormErrors(e, 'The follow-up could not be updated.').general ?? null)
    }
  }

  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">Checkups and Follow-ups</h1>
      <HelperNote>Tests and visits added from your reports. Reminders are not sent yet, so check here.</HelperNote>

      {error && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}
      {items === null && !error && <p role="status">Loading follow-ups…</p>}

      {items !== null && items.length === 0 && (
        <div className="card empty-state">
          <p>
            <strong>No follow-ups yet.</strong>
          </p>
          <p>
            Open a prescription in <Link to="/documents">Medical Documents</Link> and choose “Add to Checkups and
            Follow-ups”.
          </p>
        </div>
      )}

      {items !== null &&
        groupByReport(items).map((group) => {
          const pending = group.items.filter((item) => item.status === 'scheduled').length
          const headingId = `report-${group.key}`
          return (
            <section key={group.key} className="card follow-up-group" aria-labelledby={headingId}>
              <h2 id={headingId}>
                {group.documentId ? <Link to={`/documents/${group.documentId}`}>{group.title}</Link> : group.title}{' '}
                <span className="count">
                  ({pending} pending of {group.items.length})
                </span>
              </h2>
              <ul className="follow-up-list">
                {group.items.map((item) => (
                  <FollowUpRow key={item.id} item={item} onChange={(status) => void change(item.id, status)} />
                ))}
              </ul>
            </section>
          )
        })}
    </section>
  )
}
