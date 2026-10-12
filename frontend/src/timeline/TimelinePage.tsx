import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { toFormErrors } from '../auth/formErrors'
import { FormField } from '../components/FormField'
import { HelperNote } from '../components/HelperNote'
import { formatDayMonthYear } from '../documents/format'
import {
  TIMELINE_CATEGORIES,
  timelineApi,
  type TimelineCategory,
  type TimelineEntry,
  type TimelineFilters,
  type Trust,
} from './timelineApi'

const CATEGORY_LABELS: Record<TimelineCategory, string> = {
  lab_results: 'Lab results',
  imaging: 'Imaging',
  test_reports: 'Test reports',
  consultations: 'Consultations',
  hospital_stays: 'Hospital stays',
  prescriptions: 'Prescriptions',
  medications: 'Medications',
  follow_ups: 'Follow-ups',
  documents: 'Other documents',
}

const TRUST_LABELS: Record<Trust, string> = {
  from_document: 'From document (not checked by you)',
  confirmed_by_you: 'Confirmed by you',
  edited_by_you: 'Edited by you',
  added_by_you: 'Added by you',
}

const MONTH = new Intl.DateTimeFormat('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' })

/** Show only as much of the date as is known. */
function dateHeading(entry: TimelineEntry): string {
  if (!entry.date) return 'No date'
  const [year, month] = entry.date.split('-').map(Number)
  if (entry.date_precision === 'year') return String(year)
  if (entry.date_precision === 'month') return MONTH.format(new Date(Date.UTC(year, month - 1, 1)))
  return formatDayMonthYear(entry.date)
}

/** Filters live in the address (?cat=…&from=&to=), so refresh and Back keep them. */
function readFilters(params: URLSearchParams): TimelineFilters {
  return {
    categories: params.getAll('cat').filter((c): c is TimelineCategory => (TIMELINE_CATEGORIES as readonly string[]).includes(c)),
    dateFrom: params.get('from') ?? '',
    dateTo: params.get('to') ?? '',
  }
}

function writeFilters(filters: TimelineFilters): URLSearchParams {
  const params = new URLSearchParams()
  for (const category of filters.categories) params.append('cat', category)
  if (filters.dateFrom) params.set('from', filters.dateFrom)
  if (filters.dateTo) params.set('to', filters.dateTo)
  return params
}

function Entry({ entry }: { entry: TimelineEntry }) {
  const tagClass = entry.tag && /outside range|Overdue/.test(entry.tag) ? ' timeline-tag-alert' : ''
  return (
    <li className={`timeline-entry timeline-${entry.category}`}>
      <p className="timeline-entry-head">
        <span className="timeline-category">{CATEGORY_LABELS[entry.category]}</span>
        {entry.link ? (
          <Link to={entry.link} className="timeline-title">
            {entry.title}
          </Link>
        ) : (
          <span className="timeline-title">{entry.title}</span>
        )}
        {entry.tag && <span className={`timeline-tag${tagClass}`}>{entry.tag}</span>}
      </p>
      {entry.lines.length > 0 && (
        <ul className="timeline-lines">
          {entry.lines.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ul>
      )}
      <p className="document-meta">
        <span className={`trust trust-${entry.trust}`}>{TRUST_LABELS[entry.trust]}</span>
        {entry.source_document_title && entry.source_document_id && (
          <>
            {' · Source: '}
            <Link to={`/documents/${entry.source_document_id}`}>{entry.source_document_title}</Link>
          </>
        )}
      </p>
    </li>
  )
}

export function TimelinePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const query = searchParams.toString()
  const filters = useMemo(() => readFilters(new URLSearchParams(query)), [query])
  const datesInOrder = !filters.dateFrom || !filters.dateTo || filters.dateFrom <= filters.dateTo

  const [entries, setEntries] = useState<TimelineEntry[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(
    async (cursor: string | null, signal?: AbortSignal) => {
      setLoading(true)
      try {
        const page = await timelineApi.list(filters, cursor)
        if (signal?.aborted) return
        setEntries((current) => (cursor ? [...current, ...page.items] : page.items))
        setNextCursor(page.next_cursor)
        setError(null)
      } catch (e) {
        if (!signal?.aborted) setError(toFormErrors(e, 'Your timeline could not be loaded.').general ?? null)
      } finally {
        if (!signal?.aborted) setLoading(false)
      }
    },
    [filters],
  )

  useEffect(() => {
    if (!datesInOrder) return
    const controller = new AbortController()
    // Loading from the backend is an external sync; state is only set after the request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void load(null, controller.signal)
    return () => controller.abort()
  }, [load, datesInOrder])

  function change(next: Partial<TimelineFilters>) {
    setSearchParams(writeFilters({ ...filters, ...next }), { replace: true })
  }

  function toggle(category: TimelineCategory) {
    const chosen = filters.categories.includes(category)
      ? filters.categories.filter((c) => c !== category)
      : [...filters.categories, category]
    change({ categories: TIMELINE_CATEGORIES.filter((c) => chosen.includes(c)) })
  }

  // One heading per date; entries keep the server's order (newest first, undated last).
  const days: { heading: string; entries: TimelineEntry[] }[] = []
  for (const entry of entries) {
    const heading = dateHeading(entry)
    const last = days[days.length - 1]
    if (last && last.heading === heading) last.entries.push(entry)
    else days.push({ heading, entries: [entry] })
  }
  const filtered = filters.categories.length > 0 || filters.dateFrom || filters.dateTo

  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">Health Timeline</h1>
      <HelperNote>All your records in date order, newest first. Each date stays separate.</HelperNote>

      <div className="card timeline-filters" role="search" aria-label="Filter the timeline">
        <fieldset className="timeline-categories">
          <legend>Show</legend>
          {TIMELINE_CATEGORIES.map((category) => (
            <label key={category} className="checkbox-label">
              <input type="checkbox" checked={filters.categories.includes(category)} onChange={() => toggle(category)} />{' '}
              {CATEGORY_LABELS[category]}
            </label>
          ))}
        </fieldset>
        <div className="timeline-dates">
          <FormField label="From" type="date" value={filters.dateFrom} onChange={(e) => change({ dateFrom: e.target.value })} />
          <FormField
            label="To"
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
        </div>
        <p className="document-meta filters-note">
          No boxes ticked shows everything.
          {(filters.dateFrom || filters.dateTo) && ' Records without a date are not shown while a date filter is set.'}
        </p>
      </div>

      {error && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}

      {!loading && !error && datesInOrder && entries.length === 0 && (
        <div className="card empty-state">
          {filtered ? (
            <p>
              <strong>Nothing matches these filters.</strong>
            </p>
          ) : (
            <>
              <p>
                <strong>Your timeline is empty.</strong>
              </p>
              <p>
                Upload a report in <Link to="/documents">Medical Documents</Link> and it will appear here once read.
              </p>
            </>
          )}
        </div>
      )}

      {days.map((day, index) => {
        const headingId = `timeline-day-${index}`
        return (
          <section key={`${day.heading}-${index}`} className="timeline-day" aria-labelledby={headingId}>
            <h2 id={headingId} className="timeline-date">
              {day.heading}
            </h2>
            <ul className="timeline-list">
              {day.entries.map((entry) => (
                <Entry key={entry.id} entry={entry} />
              ))}
            </ul>
          </section>
        )
      })}

      {loading && <p role="status">Loading timeline…</p>}

      {nextCursor && !loading && (
        <button type="button" className="button button-secondary" onClick={() => void load(nextCursor)}>
          Load more
        </button>
      )}
    </section>
  )
}
