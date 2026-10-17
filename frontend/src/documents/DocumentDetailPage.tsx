import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import { toFormErrors, type FormErrors } from '../auth/formErrors'
import { FormField } from '../components/FormField'
import { TrashIcon } from '../components/icons'
import { documentsApi, TITLE_MAX_LENGTH, type MedicalDocument } from './documentsApi'
import { AiSummaryPanel } from '../summaries/AiSummaryPanel'
import { summariesApi } from '../summaries/summariesApi'
import { ExtractedResults } from './ExtractedResults'
import type { JobStatus } from './extractionApi'
import {
  CATEGORY_LABELS,
  formatBytes,
  formatDocumentDate,
  formatTimestamp,
  PRECISION_LABELS,
  typeLabel,
} from './format'
import type { MetadataValues } from './metadata'
import { MetadataFields } from './MetadataFields'

/** Loads the file through the authenticated API into a temporary blob URL (never a public link). */
function DocumentPreview({ document }: { document: MedicalDocument }) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | null = null
    documentsApi
      .file(document.id, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) setFailed(true)
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl) // free the in-memory copy when leaving the page
    }
  }, [document.id])

  if (failed) return <p role="alert" className="form-alert">The preview could not be loaded.</p>
  if (!url) return <p role="status">Loading preview…</p>

  const title = `Preview of ${document.title}`
  return document.media_type === 'application/pdf' ? (
    <iframe src={url} title={title} className="document-preview document-preview-pdf" />
  ) : (
    <img src={url} alt={title} className="document-preview" />
  )
}

function toValues(document: MedicalDocument): MetadataValues {
  return {
    category: document.category === 'unknown' ? '' : document.category,
    report_subtype: document.report_subtype ?? '',
    document_date: document.document_date ?? '',
    document_date_precision: document.document_date_precision === 'day' ? '' : (document.document_date_precision ?? ''),
    provider_name: document.provider_name ?? '',
  }
}

export function DocumentDetailPage() {
  const { documentId = '' } = useParams()
  const navigate = useNavigate()
  const [document, setDocument] = useState<MedicalDocument | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [values, setValues] = useState<MetadataValues | null>(null)
  const [titleValue, setTitleValue] = useState('')
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [busy, setBusy] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  const loadSummary = useCallback(() => summariesApi.document(documentId), [documentId])
  const createSummary = useCallback(() => summariesApi.createDocument(documentId), [documentId])

  // Stable identity: ExtractedResults reloads when this changes.
  const handleStatusChange = useCallback((status: JobStatus) => {
    setDocument((current) => (current && current.processing_status !== status ? { ...current, processing_status: status } : current))
  }, [])

  useEffect(() => {
    let active = true
    documentsApi
      .get(documentId)
      .then((loaded) => active && setDocument(loaded))
      .catch((error: unknown) => {
        if (!active) return
        setLoadError(
          error instanceof ApiError && error.status === 404
            ? 'This document does not exist or has been deleted.'
            : 'The document could not be loaded.',
        )
      })
    return () => {
      active = false
    }
  }, [documentId])

  async function handleSave(event: FormEvent) {
    event.preventDefault()
    if (!values) return
    if (!titleValue.trim()) {
      setErrors({ fields: { title: 'Enter a name for this document.' } })
      return
    }
    setBusy(true)
    setErrors({ fields: {} })
    try {
      const updated = await documentsApi.update(documentId, {
        title: titleValue.trim(),
        category: values.category || 'unknown',
        report_subtype: values.report_subtype.trim() || null,
        document_date: values.document_date || null,
        document_date_precision: values.document_date ? values.document_date_precision || 'day' : null,
        provider_name: values.provider_name.trim() || null,
      })
      setDocument(updated)
      setEditing(false)
    } catch (error) {
      setErrors(toFormErrors(error))
    } finally {
      setBusy(false)
    }
  }

  async function handleDownload() {
    if (!document) return
    try {
      const url = URL.createObjectURL(await documentsApi.file(document.id))
      const link = window.document.createElement('a')
      link.href = url
      link.download = document.original_filename ?? 'document'
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (error) {
      setErrors(toFormErrors(error, 'The download failed. Please try again.'))
    }
  }

  async function handleDelete() {
    setBusy(true)
    try {
      await documentsApi.remove(documentId)
      navigate('/documents', { replace: true })
    } catch (error) {
      setErrors(toFormErrors(error, 'The document could not be deleted.'))
      setBusy(false)
    }
  }

  if (loadError) {
    return (
      <section aria-labelledby="page-title">
        <h1 id="page-title">Document</h1>
        <p role="alert" className="form-alert">
          {loadError}
        </p>
        <Link to="/documents">Back to documents</Link>
      </section>
    )
  }
  if (!document) return <p role="status">Loading document…</p>

  return (
    <section aria-labelledby="page-title">
      <p>
        <Link to="/documents">← All documents</Link>
      </p>
      <h1 id="page-title" className="document-title">
        {document.title}
      </h1>
      <p className="document-meta mono">
        {document.original_filename} · {typeLabel(document.media_type)} · {formatBytes(document.size_bytes)} · Uploaded {formatTimestamp(document.created_at)}
      </p>

      {errors.general && (
        <p role="alert" className="form-alert">
          {errors.general}
        </p>
      )}

      <div className="card document-details">
        <h2>Details</h2>
        {editing && values ? (
          <form onSubmit={handleSave} noValidate>
            <FormField
              label="Name (required)"
              required
              maxLength={TITLE_MAX_LENGTH}
              value={titleValue}
              onChange={(e) => setTitleValue(e.target.value)}
              error={errors.fields.title}
            />
            <MetadataFields values={values} onChange={setValues} errors={errors.fields} />
            <div className="button-row">
              <button type="submit" className="button" disabled={busy}>
                {busy ? 'Saving…' : 'Save'}
              </button>
              <button type="button" className="button button-secondary" onClick={() => setEditing(false)}>
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <>
            <dl className="detail-list">
              <dt>Report type</dt>
              <dd>{CATEGORY_LABELS[document.category]}</dd>
              <dt>Report sub-type</dt>
              <dd>{document.report_subtype ?? 'Not set'}</dd>
              <dt>Document date</dt>
              <dd>
                {formatDocumentDate(document)}
                {document.document_date_precision && document.document_date_precision !== 'day' && (
                  <span className="form-hint"> ({PRECISION_LABELS[document.document_date_precision]})</span>
                )}
              </dd>
              <dt>Hospital, lab, or clinic</dt>
              <dd>{document.provider_name ?? 'Not set'}</dd>
            </dl>
            <div className="button-row">
              <button
                type="button"
                className="button button-secondary"
                onClick={() => {
                  setValues(toValues(document))
                  setTitleValue(document.title)
                  setErrors({ fields: {} })
                  setEditing(true)
                }}
              >
                Edit details
              </button>
              <button type="button" className="button button-secondary" onClick={() => void handleDownload()}>
                Download
              </button>
              <button
                type="button"
                className="icon-button icon-button-danger"
                aria-label="Delete document"
                title="Delete document"
                aria-expanded={confirmingDelete}
                onClick={() => setConfirmingDelete(true)}
              >
                <TrashIcon />
              </button>
            </div>
          </>
        )}
      </div>

      {/* Asked to confirm before anything is deleted. */}
      {confirmingDelete && (
        <div className="card danger-zone delete-confirm">
          <h2>Delete document</h2>
          <div role="alertdialog" aria-labelledby="delete-question" aria-describedby="delete-explanation">
            <p id="delete-question">
              <strong>Delete “{document.title}” permanently?</strong>
            </p>
            <p id="delete-explanation">
              The file is removed now and cannot be recovered from the app. Backup copies are erased automatically
              within 30 days.
            </p>
            <div className="button-row">
              <button type="button" className="button button-danger" onClick={() => void handleDelete()} disabled={busy}>
                {busy ? 'Deleting…' : 'Delete permanently'}
              </button>
              <button type="button" className="button button-secondary" onClick={() => setConfirmingDelete(false)}>
                Keep document
              </button>
            </div>
          </div>
        </div>
      )}

      {/* The summary sits beside the original so values can be checked against it. */}
      <div className="document-layout">
        <div className="card">
          <DocumentPreview document={document} />
        </div>
        <ExtractedResults documentId={document.id} onStatusChange={handleStatusChange} />
      </div>

      {/* Reloads when the reading finishes, so the summary button appears without a page refresh. */}
      <AiSummaryPanel
        key={document.processing_status}
        title="Plain-language summary"
        load={loadSummary}
        create={createSummary}
        emptyText="A summary can be written once this document has been read."
      />

    </section>
  )
}
