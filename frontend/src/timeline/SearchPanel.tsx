import { useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { toFormErrors, type FormErrors } from '../auth/formErrors'
import { FormField } from '../components/FormField'
import { SelectField } from '../components/SelectField'
import { CATEGORIES } from '../documents/documentsApi'
import { CATEGORY_LABELS, formatDayMonthYear } from '../documents/format'
import { searchApi, type RecordType, type SearchCriteria, type SearchResult } from './searchApi'

const TYPE_LABELS: Record<RecordType, string> = {
  document: 'Document',
  report_text: 'Report text',
  lab_result: 'Lab result',
  medication: 'Medicine',
  diagnosis: 'Diagnosis',
  condition: 'Condition',
  follow_up: 'Follow-up',
  allergy: 'Allergy',
  surgery: 'Surgery',
  hospitalization: 'Hospitalization',
  family_history: 'Family history',
}

const DOCUMENT_TYPES = [
  ...CATEGORIES.filter((c) => c !== 'unknown').map((c) => ({ value: c, label: CATEGORY_LABELS[c] })),
  { value: 'test_report', label: 'Test report (ECG etc.)' },
]

const EMPTY = { query: '', document_type: '', provider: '', condition: '', date_from: '', date_to: '' }

/** Marks the query's words in a snippet, so it is clear why a record matched. */
function highlight(text: string, query: string): ReactNode {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return text
  const pattern = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi')
  return text.split(pattern).map((part, index) => (index % 2 === 1 ? <mark key={index}>{part}</mark> : part))
}

/**
 * Search the user's records (frontend_spec.md Section 7). The search text is kept in the page only, never in
 * the address, so it does not end up in browser history or server logs.
 */
export function SearchPanel({ onActiveChange }: { onActiveChange: (active: boolean) => void }) {
  const [form, setForm] = useState(EMPTY)
  const [submitted, setSubmitted] = useState<SearchCriteria | null>(null)
  const [results, setResults] = useState<SearchResult[]>([])
  const [total, setTotal] = useState(0)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [loading, setLoading] = useState(false)

  const set = (field: keyof typeof EMPTY) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [field]: event.target.value }))

  async function run(criteria: SearchCriteria, cursor: string | null) {
    setLoading(true)
    try {
      const page = await searchApi.search(criteria, cursor)
      setResults((current) => (cursor ? [...current, ...page.items] : page.items))
      setTotal(page.total)
      setNextCursor(page.next_cursor)
      setSubmitted(criteria)
      setErrors({ fields: {} })
      onActiveChange(true)
    } catch (e) {
      setErrors(toFormErrors(e, 'The search could not be run.'))
    } finally {
      setLoading(false)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const criteria = Object.fromEntries(
      Object.entries(form)
        .map(([key, value]) => [key, value.trim()])
        .filter(([, value]) => value),
    ) as SearchCriteria
    if (!Object.keys(criteria).length) {
      setErrors({ fields: { query: 'Enter something to search for, or choose a filter.' } })
      return
    }
    void run(criteria, null)
  }

  function clear() {
    setForm(EMPTY)
    setSubmitted(null)
    setResults([])
    setErrors({ fields: {} })
    onActiveChange(false)
  }

  return (
    <section className="card search-panel" aria-labelledby="search-title">
      <h2 id="search-title">Search your records</h2>
      <form role="search" aria-label="Search your records" onSubmit={submit} noValidate>
        {errors.general && (
          <p role="alert" className="form-alert">
            {errors.general}
          </p>
        )}
        <div className="search-row">
          <FormField
            label="Search for"
            type="search"
            hint="For example a test, medicine, diagnosis, or word in a report"
            value={form.query}
            onChange={set('query')}
            maxLength={200}
            error={errors.fields.query}
          />
          <button type="submit" className="button" disabled={loading}>
            {loading ? 'Searching…' : 'Search'}
          </button>
          {submitted && (
            <button type="button" className="button button-secondary" onClick={clear}>
              Clear search
            </button>
          )}
        </div>
        <details className="search-more">
          <summary>More filters</summary>
          <div className="profile-grid">
            <SelectField
              label="Document type"
              value={form.document_type}
              onChange={set('document_type')}
              options={[{ value: '', label: 'Any type' }, ...DOCUMENT_TYPES]}
            />
            <FormField label="Hospital or clinic" value={form.provider} onChange={set('provider')} maxLength={200} />
            <FormField label="Condition" hint="Records from documents with this diagnosis" value={form.condition} onChange={set('condition')} maxLength={200} />
            <FormField label="Date from" type="date" value={form.date_from} onChange={set('date_from')} />
            <FormField label="Date to" type="date" value={form.date_to} onChange={set('date_to')} error={errors.fields.date_to} />
          </div>
        </details>
      </form>

      {submitted && (
        <div className="search-results" aria-live="polite">
          <p className="search-count">
            <strong>{total}</strong> result{total === 1 ? '' : 's'}
          </p>
          {results.length === 0 ? (
            <p className="document-meta">Nothing matched. Try fewer or shorter words.</p>
          ) : (
            <ul className="search-list">
              {results.map((result) => (
                <li key={`${result.record_type}-${result.id}`}>
                  <p className="timeline-entry-head">
                    <span className="timeline-category">{TYPE_LABELS[result.record_type]}</span>
                    <Link to={result.link} className="timeline-title">
                      {result.title}
                    </Link>
                    {result.date && <span className="mono">{formatDayMonthYear(result.date)}</span>}
                  </p>
                  {result.snippet && (
                    <p className="search-snippet">
                      <span className="document-meta">{result.matched_field}: </span>
                      {highlight(result.snippet, submitted.query ?? '')}
                    </p>
                  )}
                  {result.source_document_id && result.source_document_title && (
                    <p className="document-meta">
                      Source: <Link to={`/documents/${result.source_document_id}`}>{result.source_document_title}</Link>
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
          {nextCursor && !loading && (
            <button type="button" className="button button-secondary" onClick={() => void run(submitted, nextCursor)}>
              Load more results
            </button>
          )}
        </div>
      )}
    </section>
  )
}
