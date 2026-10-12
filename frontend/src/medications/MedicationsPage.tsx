import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { toFormErrors, type FormErrors } from '../auth/formErrors'
import { FormField } from '../components/FormField'
import { TrashIcon } from '../components/icons'
import { SelectField } from '../components/SelectField'
import { formatDayMonthYear, formatTimestamp } from '../documents/format'
import {
  medicationsApi,
  type HistoryField,
  type Medication,
  type MedicationFields,
  type MedicationHistoryEntry,
  type MedicationStatus,
} from './medicationsApi'

const STATUS_LABELS: Record<MedicationStatus, string> = {
  active: 'Taking',
  unknown: 'Not sure',
  stopped: 'Stopped',
}

const GROUPS: { status: MedicationStatus; title: string; intro?: string }[] = [
  { status: 'active', title: 'Taking now' },
  {
    status: 'unknown',
    title: 'Not confirmed',
    intro: 'Read from your documents, or not yet confirmed by you. A medicine on a prescription is not marked as taking until you confirm it.',
  },
  { status: 'stopped', title: 'Stopped' },
]

const FIELD_LABELS: Record<HistoryField, string> = {
  name: 'Medicine',
  strength: 'Strength',
  dosage_text: 'How to take',
  duration_text: 'Duration',
  prescriber_name: 'Prescriber',
  start_date: 'Start date',
  end_date: 'End date',
  notes: 'Notes',
  status: 'Status',
}

const CHANGE_LABELS: Record<MedicationHistoryEntry['change'], string> = {
  added: 'Added',
  edited: 'Edited',
  status_changed: 'Status changed',
  removed: 'Removed',
}

const TEXT_FIELDS = ['strength', 'dosage_text', 'duration_text', 'prescriber_name', 'start_date', 'end_date', 'notes'] as const

type FormValues = Record<keyof MedicationFields, string>

const EMPTY_FORM: FormValues = {
  name: '',
  strength: '',
  dosage_text: '',
  duration_text: '',
  prescriber_name: '',
  start_date: '',
  end_date: '',
  notes: '',
  status: 'active',
}

function toForm(medication: Medication): FormValues {
  const values = { ...EMPTY_FORM, name: medication.name, status: medication.status }
  for (const field of TEXT_FIELDS) values[field] = medication[field] ?? ''
  return values
}

function toFields(values: FormValues): MedicationFields {
  const fields: MedicationFields = {
    name: values.name.trim(),
    status: values.status as MedicationStatus,
    strength: null,
    dosage_text: null,
    duration_text: null,
    prescriber_name: null,
    start_date: null,
    end_date: null,
    notes: null,
  }
  for (const field of TEXT_FIELDS) fields[field] = values[field].trim() || null
  return fields
}

function historyValue(field: HistoryField, value: string | null): string {
  if (value === null || value === '') return '—'
  if (field === 'status') return STATUS_LABELS[value as MedicationStatus] ?? value
  if (field === 'start_date' || field === 'end_date') return formatDayMonthYear(value)
  return value
}

// ---------- form ----------

function MedicationForm({
  title,
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  title: string
  initial: FormValues
  submitLabel: string
  onSubmit: (fields: MedicationFields) => Promise<void>
  onCancel: () => void
}) {
  const [values, setValues] = useState(initial)
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [saving, setSaving] = useState(false)

  const set = (field: keyof FormValues) => (event: { target: { value: string } }) =>
    setValues((current) => ({ ...current, [field]: event.target.value }))

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!values.name.trim()) {
      setErrors({ fields: { name: 'Enter the medicine name.' } })
      return
    }
    if (values.start_date && values.end_date && values.end_date < values.start_date) {
      setErrors({ fields: { end_date: 'The end date cannot be before the start date.' } })
      return
    }
    setSaving(true)
    try {
      await onSubmit(toFields(values))
    } catch (e) {
      setErrors(toFormErrors(e, 'The medicine could not be saved.'))
      setSaving(false)
    }
  }

  return (
    <form className="medication-form" onSubmit={(event) => void submit(event)} noValidate aria-label={title}>
      <h3>{title}</h3>
      {errors.general && (
        <p role="alert" className="form-alert">
          {errors.general}
        </p>
      )}
      <div className="medication-form-grid">
        <FormField label="Medicine name" value={values.name} onChange={set('name')} maxLength={200} error={errors.fields.name} required />
        <FormField label="Strength" hint="For example 500 mg" value={values.strength} onChange={set('strength')} maxLength={100} error={errors.fields.strength} />
        <FormField label="How to take" hint="As written, for example once daily after dinner" value={values.dosage_text} onChange={set('dosage_text')} maxLength={300} error={errors.fields.dosage_text} />
        <FormField label="Duration" hint="For example 90 days" value={values.duration_text} onChange={set('duration_text')} maxLength={100} error={errors.fields.duration_text} />
        <FormField label="Prescriber" value={values.prescriber_name} onChange={set('prescriber_name')} maxLength={200} error={errors.fields.prescriber_name} />
        <SelectField
          label="Status"
          value={values.status}
          onChange={set('status')}
          options={(['active', 'unknown', 'stopped'] as const).map((status) => ({ value: status, label: STATUS_LABELS[status] }))}
        />
        <FormField label="Start date" type="date" value={values.start_date} onChange={set('start_date')} error={errors.fields.start_date} />
        <FormField label="End date" type="date" value={values.end_date} onChange={set('end_date')} error={errors.fields.end_date} />
      </div>
      <FormField label="Notes" value={values.notes} onChange={set('notes')} maxLength={2000} error={errors.fields.notes} />
      <div className="button-row">
        <button type="submit" className="button" disabled={saving}>
          {saving ? 'Saving…' : submitLabel}
        </button>
        <button type="button" className="button button-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

// ---------- history ----------

function HistoryPanel({ medication }: { medication: Medication }) {
  const [entries, setEntries] = useState<MedicationHistoryEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let current = true
    medicationsApi
      .history(medication.id)
      .then((body) => current && setEntries(body.items))
      .catch((e: unknown) => current && setError(toFormErrors(e, 'The history could not be loaded.').general ?? null))
    return () => {
      current = false
    }
  }, [medication.id, medication.updated_at])

  return (
    <div className="medication-history">
      <h3>Change history</h3>
      {error && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}
      {entries === null && !error && <p role="status">Loading history…</p>}
      {entries !== null && entries.length === 0 && <p>No changes yet.</p>}
      {entries !== null && entries.length > 0 && (
        <ul className="history-list">
          {entries.map((entry) => (
            <li key={entry.id}>
              <span className="mono">{formatTimestamp(entry.changed_at)}</span> · <strong>{CHANGE_LABELS[entry.change]}</strong>
              {entry.change !== 'removed' && (
                <ul>
                  {Object.entries(entry.changes).map(([field, [before, after]]) => {
                    const key = field as HistoryField
                    return (
                      <li key={field}>
                        {FIELD_LABELS[key]}:{' '}
                        {entry.change === 'added' ? historyValue(key, after) : `${historyValue(key, before)} → ${historyValue(key, after)}`}
                      </li>
                    )
                  })}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
      {medication.origin === 'document_extracted' && entries !== null && (
        <p className="document-meta">Before these changes, the values were as read from the document.</p>
      )}
    </div>
  )
}

// ---------- rows ----------

type Panel = { id: string; mode: 'edit' | 'history' | 'remove' } | null

function Labels({ medication }: { medication: Medication }) {
  const labels =
    medication.origin === 'user_entered'
      ? ['Added by you']
      : [medication.status_confirmed ? 'Confirmed by you' : 'From document', ...(medication.edited ? ['Edited by you'] : [])]
  return (
    <>
      {labels.map((label) => (
        <span key={label} className={`medication-tag${label === 'From document' ? ' medication-tag-document' : ''}`}>
          {label}
        </span>
      ))}
    </>
  )
}

function SourceCell({ medication }: { medication: Medication }) {
  if (medication.source_document_id && medication.source_document_title) {
    return (
      <>
        <Link to={`/documents/${medication.source_document_id}`}>{medication.source_document_title}</Link>
        {medication.source_document_date && (
          <span className="mono medication-source-date">{formatDayMonthYear(medication.source_document_date)}</span>
        )}
      </>
    )
  }
  if (medication.source_document_deleted) return <span className="document-meta">Deleted document</span>
  return <>—</>
}

function MedicationRow({
  medication,
  panel,
  setPanel,
  onUpdate,
  onRemove,
}: {
  medication: Medication
  panel: Panel
  setPanel: (panel: Panel) => void
  onUpdate: (fields: Partial<MedicationFields>) => Promise<void>
  onRemove: () => Promise<void>
}) {
  const open = panel?.id === medication.id ? panel.mode : null
  const toggle = (mode: 'edit' | 'history' | 'remove') => setPanel(open === mode ? null : { id: medication.id, mode })
  const fullName = [medication.name, medication.strength].filter(Boolean).join(' ')
  const dates = [
    medication.start_date && `From ${formatDayMonthYear(medication.start_date)}`,
    medication.end_date && `to ${formatDayMonthYear(medication.end_date)}`,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <>
      <tr>
        <th scope="row">
          <span className="medication-name">{fullName}</span>
          {medication.review_reason && (
            <span className="unclear-tag" title={medication.review_reason}>
              {' '}
              (unclear – check original)
            </span>
          )}
          <div className="medication-tags">
            <Labels medication={medication} />
          </div>
          {dates && <p className="document-meta">{dates}</p>}
          {medication.notes && <p className="document-meta">{medication.notes}</p>}
        </th>
        <td>{medication.dosage_text ?? '—'}</td>
        <td>{medication.duration_text ?? '—'}</td>
        <td>{medication.prescriber_name ?? '—'}</td>
        <td>
          <SourceCell medication={medication} />
        </td>
        <td>
          <div className="medication-actions">
            {medication.status !== 'active' && (
              <button type="button" className="button button-small" onClick={() => void onUpdate({ status: 'active' })}>
                Mark taking
              </button>
            )}
            {medication.status !== 'stopped' && (
              <button type="button" className="button button-small button-secondary" onClick={() => void onUpdate({ status: 'stopped' })}>
                Mark stopped
              </button>
            )}
            <button type="button" className="button button-small button-secondary" aria-expanded={open === 'edit'} onClick={() => toggle('edit')}>
              Edit
            </button>
            <button type="button" className="button button-small button-secondary" aria-expanded={open === 'history'} onClick={() => toggle('history')}>
              History
            </button>
            <button
              type="button"
              className="icon-button icon-button-danger icon-button-small"
              aria-label={`Remove ${fullName}`}
              title="Remove"
              aria-expanded={open === 'remove'}
              onClick={() => toggle('remove')}
            >
              <TrashIcon />
            </button>
          </div>
        </td>
      </tr>
      {open && (
        <tr className="medication-panel-row">
          <td colSpan={6}>
            {open === 'edit' && (
              <MedicationForm
                title={`Edit ${medication.name}`}
                initial={toForm(medication)}
                submitLabel="Save changes"
                onSubmit={async (fields) => {
                  await onUpdate(fields)
                  setPanel(null)
                }}
                onCancel={() => setPanel(null)}
              />
            )}
            {open === 'history' && <HistoryPanel medication={medication} />}
            {open === 'remove' && (
              <div role="alertdialog" aria-labelledby={`remove-${medication.id}`} className="medication-remove">
                <p id={`remove-${medication.id}`}>
                  Remove <strong>{fullName}</strong> from your list? Its change history is kept.
                </p>
                <div className="button-row">
                  <button type="button" className="button button-danger" onClick={() => void onRemove()}>
                    Remove
                  </button>
                  <button type="button" className="button button-secondary" onClick={() => setPanel(null)}>
                    Keep
                  </button>
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ---------- page ----------

export function MedicationsPage() {
  const [items, setItems] = useState<Medication[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [panel, setPanel] = useState<Panel>(null)

  const load = useCallback(async () => {
    try {
      setItems((await medicationsApi.list()).items)
      setError(null)
    } catch (e) {
      setError(toFormErrors(e, 'Your medicines could not be loaded.').general ?? null)
    }
  }, [])

  useEffect(() => {
    // Loading from the backend is an external sync; state is only set after the request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void load()
  }, [load])

  async function update(id: string, fields: Partial<MedicationFields>) {
    const updated = await medicationsApi.update(id, fields)
    setItems((current) => current?.map((item) => (item.id === id ? updated : item)) ?? null)
    setError(null)
  }

  async function quickUpdate(id: string, fields: Partial<MedicationFields>) {
    try {
      await update(id, fields)
    } catch (e) {
      setError(toFormErrors(e, 'The medicine could not be updated.').general ?? null)
    }
  }

  async function remove(id: string) {
    try {
      await medicationsApi.remove(id)
      setItems((current) => current?.filter((item) => item.id !== id) ?? null)
      setPanel(null)
      setError(null)
    } catch (e) {
      setError(toFormErrors(e, 'The medicine could not be removed.').general ?? null)
    }
  }

  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">Medications and Prescriptions</h1>
      <p className="page-intro">
        Medicines read from your prescriptions and discharge summaries, and medicines you add yourself. Every change is
        kept in each medicine’s history.
      </p>
      <p className="medication-safety-note">
        This list is a record, not medical advice. Do not start, stop, or change a medicine without your doctor’s advice.
      </p>

      <div className="list-header">
        <span />
        {!adding && (
          <button type="button" className="button" onClick={() => setAdding(true)}>
            Add medicine
          </button>
        )}
      </div>

      {adding && (
        <div className="card">
          <MedicationForm
            title="Add medicine"
            initial={EMPTY_FORM}
            submitLabel="Add medicine"
            onSubmit={async (fields) => {
              const created = await medicationsApi.create(fields)
              setItems((current) => [created, ...(current ?? [])])
              setAdding(false)
            }}
            onCancel={() => setAdding(false)}
          />
        </div>
      )}

      {error && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}
      {items === null && !error && <p role="status">Loading medicines…</p>}

      {items !== null && items.length === 0 && (
        <div className="card empty-state">
          <p>
            <strong>No medicines yet.</strong>
          </p>
          <p>
            Upload a prescription in <Link to="/documents">Medical Documents</Link>, or add a medicine yourself.
          </p>
        </div>
      )}

      {items !== null &&
        GROUPS.map((group) => {
          const rows = items.filter((item) => item.status === group.status)
          if (rows.length === 0) return null
          const headingId = `group-${group.status}`
          return (
            <section key={group.status} className="medication-group" aria-labelledby={headingId}>
              <h2 id={headingId}>
                {group.title} <span className="count">({rows.length})</span>
              </h2>
              {group.intro && <p className="document-meta">{group.intro}</p>}
              <div className="card document-table-wrap">
                <table className="document-table medication-table">
                  <caption className="visually-hidden">{group.title}</caption>
                  <thead>
                    <tr>
                      <th scope="col">Medicine</th>
                      <th scope="col">How to take</th>
                      <th scope="col">Duration</th>
                      <th scope="col">Prescriber</th>
                      <th scope="col">Source</th>
                      <th scope="col">
                        <span className="visually-hidden">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((medication) => (
                      <MedicationRow
                        key={medication.id}
                        medication={medication}
                        panel={panel}
                        setPanel={setPanel}
                        onUpdate={(fields) =>
                          fields.name === undefined ? quickUpdate(medication.id, fields) : update(medication.id, fields)
                        }
                        onRemove={() => remove(medication.id)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )
        })}
    </section>
  )
}
