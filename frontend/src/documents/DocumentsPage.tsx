import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { toFormErrors } from '../auth/formErrors'
import { SelectField } from '../components/SelectField'
import { CATEGORIES, documentsApi, type Category, type MedicalDocument } from './documentsApi'
import { CATEGORY_LABELS, formatBytes, formatDocumentDate, formatTimestamp, typeLabel } from './format'
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
        // The wrapper scrolls sideways on narrow screens, so the page itself never does.
        <div className="card document-table-wrap">
          <table className="document-table" aria-busy={loading}>
            <caption className="visually-hidden">Your documents</caption>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Type</th>
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
