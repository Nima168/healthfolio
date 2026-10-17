import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { toFormErrors } from '../auth/formErrors'
import { FormField } from '../components/FormField'
import { SelectField } from '../components/SelectField'
import {
  CATEGORIES,
  documentsApi,
  NO_PROVIDER,
  type Category,
  type DocumentFilters,
  type MedicalDocument,
  type ProviderList,
} from './documentsApi'
import { CATEGORY_LABELS, formatBytes, formatDocumentDate, formatTimestamp, REPORT_TYPE_OPTIONS, typeLabel } from './format'
import { GROUPING_LABELS, GROUPINGS, groupDocuments, hasFilters, matchesFilters, type Grouping } from './grouping'
import { UploadPanel } from './UploadPanel'
import { HelperNote } from '../components/HelperNote'

/** Documents are grouped by report type unless another grouping (or none) is chosen (decision 2026-10-17). */
const DEFAULT_GROUPING: Grouping = 'type'

/** Filters and grouping live in the address (?type=&from=&to=&hospital=&nohospital=1&group=), so refresh and Back keep them. */
function readSettings(params: URLSearchParams): { filters: DocumentFilters; grouping: Grouping } {
  const type = params.get('type') ?? ''
  const group = params.get('group') ?? DEFAULT_GROUPING
  return {
    filters: {
      category: (CATEGORIES as readonly string[]).includes(type) ? (type as Category) : '',
      dateFrom: params.get('from') ?? '',
      dateTo: params.get('to') ?? '',
      provider: params.get('nohospital') === '1' ? NO_PROVIDER : (params.get('hospital') ?? ''),
    },
    grouping: (GROUPINGS as readonly string[]).includes(group) ? (group as Grouping) : DEFAULT_GROUPING,
  }
}

function writeSettings(filters: DocumentFilters, grouping: Grouping): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.category) params.set('type', filters.category)
  if (filters.dateFrom) params.set('from', filters.dateFrom)
  if (filters.dateTo) params.set('to', filters.dateTo)
  if (filters.provider === NO_PROVIDER) params.set('nohospital', '1')
  else if (filters.provider) params.set('hospital', filters.provider)
  if (grouping !== DEFAULT_GROUPING) params.set('group', grouping)
  return params
}

const ALL_PAGES_LIMIT = 50

function DocumentTable({ documents, caption, busy }: { documents: MedicalDocument[]; caption: string; busy: boolean }) {
  return (
    // The wrapper scrolls sideways on narrow screens, so the page itself never does.
    <div className="card document-table-wrap">
      <table className="document-table" aria-busy={busy}>
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Report type</th>
            <th scope="col">Report sub-type</th>
            <th scope="col">Document date</th>
            <th scope="col">Hospital, lab, or clinic</th>
            <th scope="col">File</th>
            <th scope="col">Uploaded</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.id}>
              <th scope="row">
                <Link to={`/documents/${document.id}`} className="document-name">
                  {document.title}
                </Link>
              </th>
              <td>{CATEGORY_LABELS[document.category]}</td>
              <td>{document.report_subtype ?? '—'}</td>
              <td>{formatDocumentDate(document)}</td>
              <td>{document.provider_name ?? '—'}</td>
              <td className="mono document-file">
                {document.original_filename}
                <br />
                {typeLabel(document.media_type)} · {formatBytes(document.size_bytes)}
              </td>
              <td className="mono">{formatTimestamp(document.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function DocumentsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const query = searchParams.toString()
  const { filters, grouping } = useMemo(() => readSettings(new URLSearchParams(query)), [query])
  const datesInOrder = !filters.dateFrom || !filters.dateTo || filters.dateFrom <= filters.dateTo

  const [documents, setDocuments] = useState<MedicalDocument[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [providers, setProviders] = useState<ProviderList>({ items: [], without_provider: 0 })

  const loadProviders = useCallback(async () => {
    try {
      setProviders(await documentsApi.providers())
    } catch {
      // The hospital filter then offers only "All" and "No hospital given"; the list itself still works.
    }
  }, [])

  /** Grouped: every matching document (so each group and count is complete). Ungrouped: one page at a time. */
  const load = useCallback(
    async (cursor: string | null, signal?: AbortSignal) => {
      setLoading(true)
      try {
        if (grouping === 'none') {
          const page = await documentsApi.list({ cursor, ...filters })
          if (signal?.aborted) return
          setDocuments((current) => (cursor ? [...current, ...page.items] : page.items))
          setNextCursor(page.pagination.next_cursor)
        } else {
          const all: MedicalDocument[] = []
          let next: string | null = null
          do {
            const page = await documentsApi.list({ cursor: next, limit: ALL_PAGES_LIMIT, ...filters })
            if (signal?.aborted) return
            all.push(...page.items)
            next = page.pagination.next_cursor
          } while (next)
          setDocuments(all)
          setNextCursor(null)
        }
        setLoadError(null)
      } catch (error) {
        if (!signal?.aborted) setLoadError(toFormErrors(error, 'Your documents could not be loaded.').general ?? null)
      } finally {
        if (!signal?.aborted) setLoading(false)
      }
    },
    [filters, grouping],
  )

  useEffect(() => {
    if (!datesInOrder) return
    const controller = new AbortController()
    // Loading from the backend is an external sync; state is only set after the request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void load(null, controller.signal)
    return () => controller.abort()
  }, [load, datesInOrder])

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect
    void loadProviders()
  }, [loadProviders])

  function change(next: Partial<DocumentFilters>, nextGrouping: Grouping = grouping) {
    setSearchParams(writeSettings({ ...filters, ...next }, nextGrouping), { replace: true })
  }

  function handleUploaded(document: MedicalDocument) {
    if (matchesFilters(document, filters)) setDocuments((current) => [document, ...current])
    void loadProviders() // it may name a new hospital or clinic
  }

  const filtered = hasFilters(filters)
  const groups = groupDocuments(documents, grouping)
  const selectedProviderListed =
    !filters.provider || filters.provider === NO_PROVIDER || providers.items.some((p) => p.name === filters.provider)

  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">Medical Documents</h1>
      <HelperNote>Upload, filter, and open your medical reports. Originals are kept exactly as uploaded.</HelperNote>

      <div className="list-header">
        <div>
          <h2>Your documents</h2>
          <a href="#upload" className="jump-link">
            Upload a document ↓
          </a>
        </div>
      </div>

      <div className="card document-filters" role="search" aria-label="Filter and group documents">
        <SelectField
          label="Report type"
          value={filters.category}
          onChange={(e) => change({ category: e.target.value as Category | '' })}
          options={[
            { value: '', label: 'All types' },
            ...REPORT_TYPE_OPTIONS,
            { value: 'unknown', label: CATEGORY_LABELS.unknown },
          ]}
        />
        <FormField
          label="Report date from"
          type="date"
          value={filters.dateFrom}
          onChange={(e) => change({ dateFrom: e.target.value })}
        />
        <FormField
          label="Report date to"
          type="date"
          value={filters.dateTo}
          onChange={(e) => change({ dateTo: e.target.value })}
          error={datesInOrder ? undefined : 'The end date cannot be before the start date.'}
        />
        <SelectField
          label="Hospital or clinic"
          value={filters.provider}
          onChange={(e) => change({ provider: e.target.value })}
          options={[
            { value: '', label: 'All' },
            ...providers.items.map((p) => ({ value: p.name, label: `${p.name} (${p.document_count})` })),
            ...(selectedProviderListed ? [] : [{ value: filters.provider, label: filters.provider }]),
            { value: NO_PROVIDER, label: `No hospital given (${providers.without_provider})` },
          ]}
        />
        <SelectField
          label="Group by"
          value={grouping}
          onChange={(e) => change({}, e.target.value as Grouping)}
          options={GROUPINGS.map((g) => ({ value: g, label: GROUPING_LABELS[g] }))}
        />
        {(filtered || grouping !== DEFAULT_GROUPING) && (
          <button
            type="button"
            className="button button-secondary filters-clear"
            onClick={() => setSearchParams(new URLSearchParams(), { replace: true })}
          >
            Clear filters
          </button>
        )}
        {(filters.dateFrom || filters.dateTo) && (
          <p className="document-meta filters-note">Documents without a report date are not shown while a date filter is set.</p>
        )}
      </div>

      {loadError && (
        <p role="alert" className="form-alert">
          {loadError}
        </p>
      )}

      {!loading && !loadError && datesInOrder && documents.length === 0 && (
        <div className="card empty-state">
          {filtered ? (
            <>
              <p>
                <strong>No documents match these filters.</strong>
              </p>
              <p>Change or clear the filters to see more.</p>
            </>
          ) : (
            <>
              <p>
                <strong>No documents yet.</strong>
              </p>
              <p>Upload a lab report, prescription, or discharge summary below to get started.</p>
            </>
          )}
        </div>
      )}

      {documents.length > 0 &&
        (grouping === 'none' ? (
          <DocumentTable documents={documents} caption="Your documents" busy={loading} />
        ) : (
          groups.map((group, index) => {
            const headingId = `documents-group-${index}` // keys can contain spaces (hospital names)
            return (
              <section key={group.key} className="document-group" aria-labelledby={headingId}>
                <h3 id={headingId}>
                  {group.title} <span className="count">({group.documents.length})</span>
                </h3>
                <DocumentTable documents={group.documents} caption={group.title} busy={loading} />
              </section>
            )
          })
        ))}

      {loading && <p role="status">Loading documents…</p>}

      {nextCursor && !loading && (
        <button type="button" className="button button-secondary" onClick={() => void load(nextCursor)}>
          Load more
        </button>
      )}

      <UploadPanel onUploaded={handleUploaded} />
    </section>
  )
}
