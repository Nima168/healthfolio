import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { toFormErrors } from '../auth/formErrors'
import { SelectField } from '../components/SelectField'
import { CATEGORIES, documentsApi, type Category, type MedicalDocument } from './documentsApi'
import { CATEGORY_LABELS, formatBytes, formatDocumentDate, formatTimestamp, processingLabel, typeLabel } from './format'
import { UploadPanel } from './UploadPanel'

export function DocumentsPage() {
  const [documents, setDocuments] = useState<MedicalDocument[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [category, setCategory] = useState<Category | ''>('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async (cursor: string | null, filter: Category | '', signal?: AbortSignal) => {
    setLoading(true)
    try {
      const page = await documentsApi.list({ cursor, category: filter })
      if (signal?.aborted) return
      setDocuments((current) => (cursor ? [...current, ...page.items] : page.items))
      setNextCursor(page.pagination.next_cursor)
      setLoadError(null)
    } catch (error) {
      if (!signal?.aborted) setLoadError(toFormErrors(error, 'Your documents could not be loaded.').general ?? null)
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    // Loading from the backend is an external sync; state is only set after the request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void load(null, category, controller.signal)
    return () => controller.abort()
  }, [category, load])

  function handleUploaded(document: MedicalDocument) {
    if (!category || document.category === category) setDocuments((current) => [document, ...current])
  }

  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">Medical Documents</h1>
      <p className="page-intro">Your reports, prescriptions, and summaries. Originals are kept exactly as uploaded.</p>

      <div className="list-header">
        <div>
          <h2>Your documents</h2>
          <a href="#upload" className="jump-link">
            Upload a document ↓
          </a>
        </div>
        <SelectField
          label="Show"
          value={category}
          onChange={(e) => setCategory(e.target.value as Category | '')}
          options={[
            { value: '', label: 'All types' },
            ...CATEGORIES.map((c) => ({ value: c, label: CATEGORY_LABELS[c] })),
          ]}
        />
      </div>

      {loadError && (
        <p role="alert" className="form-alert">
          {loadError}
        </p>
      )}

      {!loading && !loadError && documents.length === 0 && (
        <div className="card empty-state">
          <p>
            <strong>{category ? 'No documents of this type yet.' : 'No documents yet.'}</strong>
          </p>
          <p>Upload a lab report, prescription, or discharge summary below to get started.</p>
        </div>
      )}

      {documents.length > 0 && (
        <ul className="document-list" aria-busy={loading}>
          {documents.map((document) => (
            <li key={document.id} className="card document-row">
              <div>
                <Link to={`/documents/${document.id}`} className="document-name">
                  {document.title}
                </Link>
                <p className="document-meta">
                  {CATEGORY_LABELS[document.category]} · {formatDocumentDate(document)}
                  {document.provider_name && <> · {document.provider_name}</>}
                </p>
                <p className="document-meta mono">
                  {document.original_filename} · {typeLabel(document.media_type)} · {formatBytes(document.size_bytes)} · Uploaded{' '}
                  {formatTimestamp(document.created_at)}
                </p>
              </div>
              <span className="status-badge" data-state="checking">
                {processingLabel(document.processing_status)}
              </span>
            </li>
          ))}
        </ul>
      )}

      {loading && <p role="status">Loading documents…</p>}

      {nextCursor && !loading && (
        <button type="button" className="button button-secondary" onClick={() => void load(nextCursor, category)}>
          Load more
        </button>
      )}

      <UploadPanel onUploaded={handleUploaded} />
    </section>
  )
}
