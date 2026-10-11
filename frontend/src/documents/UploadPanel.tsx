import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '../api/client'
import { toFormErrors, type FormErrors } from '../auth/formErrors'
import { FormField } from '../components/FormField'
import { checkFile } from './checkFile'
import {
  ACCEPT_ATTRIBUTE,
  documentsApi,
  MAX_UPLOAD_MB,
  TITLE_MAX_LENGTH,
  type DocumentMetadata,
  type MedicalDocument,
} from './documentsApi'
import { formatBytes } from './format'
import { EMPTY_METADATA, type MetadataValues } from './metadata'
import { MetadataFields } from './MetadataFields'

function toMetadata(title: string, values: MetadataValues): DocumentMetadata {
  return {
    title: title.trim(),
    category: values.category || null,
    document_date: values.document_date || null,
    document_date_precision: values.document_date ? values.document_date_precision || 'day' : null,
    provider_name: values.provider_name.trim() || null,
  }
}

export function UploadPanel({ onUploaded }: { onUploaded: (document: MedicalDocument) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [metadata, setMetadata] = useState<MetadataValues>(EMPTY_METADATA)
  const [progress, setProgress] = useState<number | null>(null)
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [duplicateId, setDuplicateId] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [success, setSuccess] = useState<string | null>(null)

  function choose(selected: File | undefined) {
    setErrors((current) => ({ fields: current.fields }))
    setDuplicateId(null)
    setSuccess(null)
    if (!selected) return
    const problem = checkFile(selected)
    if (problem) {
      setFile(null)
      setErrors({ general: problem, fields: {} })
      return
    }
    setFile(selected)
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    choose(event.dataTransfer.files[0])
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    // Check what is missing before contacting the server.
    const missing: FormErrors = { fields: {} }
    if (!file) missing.general = 'Choose a file to upload.'
    if (!title.trim()) missing.fields.title = 'Enter a name for this document.'
    if (!file || missing.fields.title) {
      setErrors(missing)
      setSuccess(null)
      return
    }

    setProgress(0)
    setErrors({ fields: {} })
    setDuplicateId(null)
    try {
      const document = await documentsApi.upload(file, toMetadata(title, metadata), { onProgress: setProgress })
      setSuccess(`Uploaded “${document.title}”.`)
      setFile(null)
      setTitle('')
      setMetadata(EMPTY_METADATA)
      if (inputRef.current) inputRef.current.value = ''
      onUploaded(document)
    } catch (error) {
      if (error instanceof ApiError && error.code === 'DUPLICATE_DOCUMENT') {
        setDuplicateId(error.details.find((d) => d.field === 'existing_document_id')?.issue ?? null)
      } else if (error instanceof ApiError && error.status === 415) {
        setErrors({ general: 'This file is not a PDF, JPEG, or PNG, even if its name says so.', fields: {} })
      } else {
        setErrors(toFormErrors(error))
      }
    } finally {
      setProgress(null)
    }
  }

  const uploading = progress !== null

  return (
    <section id="upload" className="card upload-panel" aria-labelledby="upload-title">
      <h2 id="upload-title">Upload a document</h2>
      <form onSubmit={handleSubmit} noValidate>
        <div
          className={`drop-zone${dragging ? ' drop-zone-active' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
        >
          <p>
            {file ? (
              <>
                <strong>{file.name}</strong> · {formatBytes(file.size)}
              </>
            ) : (
              'Drag a file here, or'
            )}
          </p>
          <label className="button button-small button-secondary file-picker">
            {file ? 'Choose a different file' : 'Choose a file'}
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT_ATTRIBUTE}
              className="visually-hidden"
              onChange={(e) => choose(e.target.files?.[0])}
              disabled={uploading}
            />
          </label>
          <p className="form-hint">PDF, JPEG, or PNG · up to {MAX_UPLOAD_MB} MB · scanned reports are fine</p>
        </div>

        <FormField
          label="Name (required)"
          required
          maxLength={TITLE_MAX_LENGTH}
          hint="A name you'll recognise later, e.g. “Blood test – March 2026”."
          value={title}
          onChange={(e) => {
            setTitle(e.target.value)
            if (errors.fields.title) setErrors((current) => ({ ...current, fields: { ...current.fields, title: '' } }))
          }}
          error={errors.fields.title || undefined}
        />

        {file && (
          <details className="optional-details">
            <summary>Add details (optional)</summary>
            <MetadataFields values={metadata} onChange={setMetadata} errors={errors.fields} />
          </details>
        )}

        <div aria-live="polite">
          {uploading && (
            <div className="upload-progress">
              <progress value={progress} max={1} aria-label="Upload progress" />
              <span>{Math.round((progress ?? 0) * 100)}%</span>
            </div>
          )}
          {success && (
            <p role="status" className="form-success">
              {success} It will be processed once extraction is available.
            </p>
          )}
        </div>

        {errors.general && (
          <p role="alert" className="form-alert">
            {errors.general}
          </p>
        )}
        {duplicateId && (
          <p role="alert" className="form-alert">
            You have already uploaded this file. <Link to={`/documents/${duplicateId}`}>View the existing document</Link>
          </p>
        )}

        <button type="submit" className="button" disabled={uploading}>
          {uploading ? 'Uploading…' : 'Upload'}
        </button>
      </form>
    </section>
  )
}
