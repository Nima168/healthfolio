import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { toFormErrors, type FormErrors } from '../auth/formErrors'
import { FormField } from '../components/FormField'
import { HelperNote } from '../components/HelperNote'
import { TrashIcon } from '../components/icons'
import { SelectField } from '../components/SelectField'
import { formatDayMonthYear, formatTimestamp } from '../documents/format'
import {
  PERSONAL_FIELDS,
  profileApi,
  type ActiveMedication,
  type AllergyCategory,
  type BmiCategory,
  type ConditionStatus,
  type ConditionSuggestion,
  type PersonalField,
  type Profile,
  type ProfileHistoryEntry,
  type RecordItem,
  type RecordKind,
} from './profileApi'

const FIELD_LABELS: Record<string, string> = {
  date_of_birth: 'Date of birth',
  sex: 'Sex',
  blood_group: 'Blood group',
  height: 'Height (cm)',
  weight: 'Weight (kg)',
  allergy: 'Allergy',
}

const SEX_OPTIONS = [
  { value: '', label: 'Not set' },
  { value: 'female', label: 'Female' },
  { value: 'male', label: 'Male' },
  { value: 'other', label: 'Other' },
  { value: 'prefer_not_to_say', label: 'Prefer not to say' },
]
const SEX_LABELS = Object.fromEntries(SEX_OPTIONS.map((o) => [o.value, o.label]))
const BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']

const STATUS_OPTIONS: { value: ConditionStatus; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'unknown', label: 'Not sure' },
]

const ALLERGY_LABELS: Record<AllergyCategory, string> = {
  drug: 'Drug',
  food: 'Food',
  environmental: 'Environmental',
  other: 'Other',
}

const MEDICINE_KIND_LABELS: Record<ActiveMedication['kind'], string> = {
  prescription: 'Prescription',
  over_the_counter: 'Over the counter',
  supplement: 'Supplement',
}

const RELATIONS = ['Mother', 'Father', 'Sister', 'Brother', 'Grandmother', 'Grandfather', 'Aunt', 'Uncle', 'Child', 'Other']

function shownValue(field: string, value: string | null): string {
  if (!value) return '—'
  if (field === 'date_of_birth') return formatDayMonthYear(value)
  if (field === 'sex') return SEX_LABELS[value] ?? value
  return value
}

type Values = Record<PersonalField, string>

function toValues(profile: Profile): Values {
  return Object.fromEntries(PERSONAL_FIELDS.map((f) => [f, profile.values[f]?.value ?? ''])) as Values
}

// ---------- BMI ----------

const BMI_BANDS: { category: BmiCategory; label: string; range: string; from: number; to: number }[] = [
  { category: 'underweight', label: 'Underweight', range: 'below 18.5', from: 12, to: 18.5 },
  { category: 'healthy', label: 'Healthy weight', range: '18.5 to 24.9', from: 18.5, to: 25 },
  { category: 'overweight', label: 'Overweight', range: '25.0 to 29.9', from: 25, to: 30 },
  { category: 'obesity_1', label: 'Obesity (class 1)', range: '30.0 to 34.9', from: 30, to: 35 },
  { category: 'obesity_2', label: 'Obesity (class 2)', range: '35.0 to 39.9', from: 35, to: 40 },
  { category: 'obesity_3', label: 'Obesity (class 3, severe)', range: '40.0 or greater', from: 40, to: 45 },
]
const SCALE = { from: 12, to: 45 }

function BmiIndicator({ bmi, category, hasBirthDate }: { bmi: number | null; category: BmiCategory | null; hasBirthDate: boolean }) {
  if (bmi === null) {
    return <p className="document-meta bmi-empty">BMI: save your height and weight to see it.</p>
  }
  const band = BMI_BANDS.find((b) => b.category === category)
  const position = Math.min(100, Math.max(0, ((bmi - SCALE.from) / (SCALE.to - SCALE.from)) * 100))
  return (
    <div className="bmi-indicator" role="group" aria-label="BMI">
      <p className="bmi-summary">
        <span className="bmi-label">BMI</span> <span className="bmi-value">{bmi.toFixed(1)}</span>
        {band ? (
          <span className={`bmi-category bmi-${band.category}`}>
            {band.label} ({band.range})
          </span>
        ) : (
          <span className="document-meta">Adult categories do not apply under 18.</span>
        )}
      </p>
      {band && (
        <div className="bmi-scale" aria-hidden="true">
          {BMI_BANDS.map((b) => (
            <span
              key={b.category}
              className={`bmi-band bmi-${b.category}${b.category === category ? ' bmi-band-current' : ''}`}
              style={{ flexGrow: b.to - b.from }}
              title={`${b.label}: ${b.range}`}
            />
          ))}
          <span className="bmi-marker" style={{ left: `${position}%` }} />
        </div>
      )}
      <p className="form-hint">
        Calculated from your saved height and weight{hasBirthDate ? '' : '; adult categories'}. BMI does not account for
        muscle, body shape, or pregnancy.
      </p>
    </div>
  )
}

// ---------- suggestions ----------

function SuggestionRow({
  suggestion,
  onReview,
}: {
  suggestion: ConditionSuggestion
  onReview: (action: 'accept' | 'correct' | 'reject', name?: string) => Promise<void>
}) {
  const [correcting, setCorrecting] = useState(false)
  const [name, setName] = useState(suggestion.name)
  return (
    <li className="suggestion-row">
      <div>
        <p className="suggestion-name">{suggestion.name}</p>
        <p className="document-meta">
          Suggested from <Link to={`/documents/${suggestion.source_document_id}`}>{suggestion.source_document_title}</Link>
          {suggestion.source_document_date && ` · ${formatDayMonthYear(suggestion.source_document_date)}`}
        </p>
      </div>
      {correcting ? (
        <form
          className="suggestion-correct"
          onSubmit={(event) => {
            event.preventDefault()
            if (name.trim()) void onReview('correct', name.trim())
          }}
        >
          <FormField label="Corrected name" value={name} onChange={(e) => setName(e.target.value)} maxLength={300} />
          <div className="button-row">
            <button type="submit" className="button button-small">
              Save
            </button>
            <button type="button" className="button button-small button-secondary" onClick={() => setCorrecting(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="button-row">
          <button type="button" className="button button-small" onClick={() => void onReview('accept')}>
            Accept
          </button>
          <button type="button" className="button button-small button-secondary" onClick={() => setCorrecting(true)}>
            Correct
          </button>
          <button type="button" className="button button-small button-secondary" onClick={() => void onReview('reject')}>
            Reject
          </button>
        </div>
      )}
    </li>
  )
}

// ---------- surgeries, hospitalizations, family history ----------

function RecordList({
  kind,
  items,
  addLabel,
  emptyText,
  onChanged,
}: {
  kind: RecordKind
  items: RecordItem[]
  addLabel: string
  emptyText: string
  onChanged: () => Promise<void>
}) {
  const [name, setName] = useState('')
  const [when, setWhen] = useState('')
  const [relation, setRelation] = useState('')
  const [notes, setNotes] = useState('')
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const family = kind === 'family'

  async function add(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) {
      setErrors({ fields: { name: family ? 'Enter the condition.' : 'Enter a name.' } })
      return
    }
    if (family && !relation) {
      setErrors({ fields: { relation: 'Choose who in your family.' } })
      return
    }
    try {
      await profileApi.addRecord({
        kind,
        name: name.trim(),
        ...(when && !family ? { occurred_on: when } : {}),
        ...(family ? { relation } : {}),
        ...(notes.trim() ? { notes: notes.trim() } : {}),
      })
      setName('')
      setWhen('')
      setRelation('')
      setNotes('')
      setErrors({ fields: {} })
      await onChanged()
    } catch (e) {
      setErrors(toFormErrors(e, 'It could not be added.'))
    }
  }

  return (
    <>
      {items.length === 0 ? (
        <p className="document-meta">{emptyText}</p>
      ) : (
        <ul className="record-list">
          {items.map((item) => (
            <li key={item.id}>
              <span>
                <strong>{item.name}</strong>
                {item.relation && ` — ${item.relation}`}
                {item.occurred_on && <span className="mono"> · {formatDayMonthYear(item.occurred_on)}</span>}
                {item.notes && <span className="document-meta"> · {item.notes}</span>}
              </span>
              <button
                type="button"
                className="icon-button icon-button-danger icon-button-small"
                aria-label={`Remove ${item.name}`}
                title="Remove"
                onClick={() => void profileApi.removeRecord(item.id).then(onChanged)}
              >
                <TrashIcon />
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="inline-add" onSubmit={(event) => void add(event)} noValidate aria-label={addLabel}>
        {errors.general && (
          <p role="alert" className="form-alert">
            {errors.general}
          </p>
        )}
        <FormField
          label={family ? 'Condition' : kind === 'surgery' ? 'Surgery' : 'Reason for stay'}
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={300}
          error={errors.fields.name}
        />
        {family ? (
          <SelectField
            label="Relative"
            value={relation}
            onChange={(e) => setRelation(e.target.value)}
            options={[{ value: '', label: 'Choose' }, ...RELATIONS.map((r) => ({ value: r, label: r }))]}
            error={errors.fields.relation}
          />
        ) : (
          <FormField label="Date (optional)" type="date" value={when} onChange={(e) => setWhen(e.target.value)} error={errors.fields.occurred_on} />
        )}
        <FormField label="Notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} />
        <button type="submit" className="button button-secondary">
          {addLabel}
        </button>
      </form>
    </>
  )
}

// ---------- page ----------

export function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [values, setValues] = useState<Values | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [valueErrors, setValueErrors] = useState<FormErrors>({ fields: {} })
  const [saved, setSaved] = useState(false)
  const [history, setHistory] = useState<ProfileHistoryEntry[] | null>(null)
  const [allergy, setAllergy] = useState('')
  const [allergyCategory, setAllergyCategory] = useState<AllergyCategory | ''>('')
  const [reaction, setReaction] = useState('')
  const [allergyError, setAllergyError] = useState<string | undefined>()
  const [condition, setCondition] = useState('')
  const [conditionStatus, setConditionStatus] = useState<ConditionStatus>('active')
  const [conditionError, setConditionError] = useState<string | undefined>()

  const show = useCallback((next: Profile) => {
    setProfile(next)
    setValues(toValues(next))
  }, [])

  const load = useCallback(async () => {
    try {
      show(await profileApi.get())
      setError(null)
    } catch (e) {
      setError(toFormErrors(e, 'Your profile could not be loaded.').general ?? null)
    }
  }, [show])

  useEffect(() => {
    // Loading from the backend is an external sync; state is only set after the request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void load()
  }, [load])

  async function act(action: () => Promise<unknown>, fallback: string) {
    try {
      await action()
      setError(null)
    } catch (e) {
      setError(toFormErrors(e, fallback).general ?? null)
    }
  }

  async function saveValues(event: FormEvent) {
    event.preventDefault()
    if (!profile || !values) return
    const changed = Object.fromEntries(
      PERSONAL_FIELDS.filter((f) => values[f] !== (profile.values[f]?.value ?? '')).map((f) => [f, values[f]]),
    )
    setSaved(false)
    try {
      show(await profileApi.updateValues(changed))
      setValueErrors({ fields: {} })
      setSaved(true)
      if (history) setHistory((await profileApi.history()).items)
    } catch (e) {
      setValueErrors(toFormErrors(e, 'Your details could not be saved.'))
    }
  }

  async function toggleHistory() {
    if (history) {
      setHistory(null)
      return
    }
    await act(async () => setHistory((await profileApi.history()).items), 'The history could not be loaded.')
  }

  async function addAllergy(event: FormEvent) {
    event.preventDefault()
    if (!allergy.trim()) {
      setAllergyError('Enter the allergy.')
      return
    }
    try {
      await profileApi.addAllergy(allergy.trim(), allergyCategory || undefined, reaction.trim() || undefined)
      setAllergy('')
      setAllergyCategory('')
      setReaction('')
      setAllergyError(undefined)
      await load()
    } catch (e) {
      setAllergyError(toFormErrors(e, 'The allergy could not be added.').general ?? 'The allergy could not be added.')
    }
  }

  async function addCondition(event: FormEvent) {
    event.preventDefault()
    if (!condition.trim()) {
      setConditionError('Enter the condition.')
      return
    }
    try {
      await profileApi.addCondition(condition.trim(), conditionStatus)
      setCondition('')
      setConditionError(undefined)
      await load()
    } catch (e) {
      const errors = toFormErrors(e, 'The condition could not be added.')
      setConditionError(errors.fields.name ?? errors.general)
    }
  }

  if (!profile || !values) {
    return (
      <section aria-labelledby="page-title">
        <h1 id="page-title">Health Profile</h1>
        {error ? (
          <p role="alert" className="form-alert">
            {error}
          </p>
        ) : (
          <p role="status">Loading your profile…</p>
        )}
      </section>
    )
  }

  const set = (field: PersonalField) => (event: { target: { value: string } }) => {
    setValues((current) => (current ? { ...current, [field]: event.target.value } : current))
    setSaved(false)
  }

  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">Health Profile</h1>
      <HelperNote>Your vital signs, medical history, medicines, allergies, and family history in one place.</HelperNote>

      {/* Allergies first: the most important thing for anyone treating you. */}
      <div className={`allergy-banner${profile.allergies.length ? '' : ' allergy-banner-none'}`} role="note" aria-label="Allergies">
        <strong>Allergies:</strong>{' '}
        {profile.allergies.length === 0
          ? 'none recorded.'
          : profile.allergies
              .map((a) => [a.name, a.category && `(${ALLERGY_LABELS[a.category].toLowerCase()})`, a.reaction && `— ${a.reaction}`].filter(Boolean).join(' '))
              .join(' · ')}
      </div>

      {error && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}

      {profile.suggestions.length > 0 && (
        <a href="#suggestions-title" className="suggestions-notice">
          <span className="suggestions-count">{profile.suggestions.length}</span>
          {profile.suggestions.length === 1 ? ' diagnosis' : ' diagnoses'} from your documents to review →
        </a>
      )}

      <section className="card profile-section" aria-labelledby="details-title">
        <h2 id="details-title">Personal Data</h2>
        <form onSubmit={(event) => void saveValues(event)} noValidate>
          {valueErrors.general && (
            <p role="alert" className="form-alert">
              {valueErrors.general}
            </p>
          )}
          <div className="profile-grid">
            <FormField label="Date of birth" type="date" value={values.date_of_birth} onChange={set('date_of_birth')} error={valueErrors.fields.date_of_birth} />
            <SelectField label="Sex" value={values.sex} onChange={set('sex')} options={SEX_OPTIONS} error={valueErrors.fields.sex} />
            <SelectField
              label="Blood group"
              value={values.blood_group}
              onChange={set('blood_group')}
              options={[{ value: '', label: 'Not set' }, ...BLOOD_GROUPS.map((g) => ({ value: g, label: g }))]}
              error={valueErrors.fields.blood_group}
            />
            <FormField label="Height (cm)" inputMode="decimal" value={values.height} onChange={set('height')} error={valueErrors.fields.height} />
            <FormField label="Weight (kg)" inputMode="decimal" value={values.weight} onChange={set('weight')} error={valueErrors.fields.weight} />
          </div>
          <BmiIndicator bmi={profile.bmi} category={profile.bmi_category} hasBirthDate={Boolean(profile.values.date_of_birth)} />
          <div className="button-row">
            <button type="submit" className="button">
              Save details
            </button>
            <button type="button" className="button button-secondary" aria-expanded={history !== null} onClick={() => void toggleHistory()}>
              {history ? 'Hide history' : 'Change history'}
            </button>
            {saved && (
              <span role="status" className="form-success-inline">
                Saved.
              </span>
            )}
          </div>
        </form>
        {history && (
          <div className="profile-history">
            {history.length === 0 ? (
              <p>No changes yet.</p>
            ) : (
              <ul className="history-list">
                {history.map((entry, index) => (
                  <li key={index}>
                    <span className="mono">{formatTimestamp(entry.changed_at)}</span> · {FIELD_LABELS[entry.field] ?? entry.field}:{' '}
                    {entry.change === 'added'
                      ? `added ${shownValue(entry.field, entry.new_value)}`
                      : entry.change === 'removed'
                        ? `removed ${shownValue(entry.field, entry.previous_value)}`
                        : `${shownValue(entry.field, entry.previous_value)} → ${shownValue(entry.field, entry.new_value)}`}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      <section className="card profile-section" aria-labelledby="history-title">
        <h2 id="history-title">Medical history</h2>

        <h3>Conditions</h3>
        {profile.conditions.length === 0 ? (
          <p className="document-meta">No conditions recorded.</p>
        ) : (
          <div className="document-table-wrap">
            <table className="document-table profile-conditions">
              <caption className="visually-hidden">Your conditions</caption>
              <thead>
                <tr>
                  <th scope="col">Condition</th>
                  <th scope="col">Status</th>
                  <th scope="col">Source</th>
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {profile.conditions.map((item) => (
                  <tr key={item.id}>
                    <th scope="row">{item.name}</th>
                    <td>
                      <select
                        aria-label={`Status of ${item.name}`}
                        value={item.status}
                        onChange={(e) =>
                          void act(async () => {
                            await profileApi.updateCondition(item.id, { status: e.target.value as ConditionStatus })
                            await load()
                          }, 'The condition could not be updated.')
                        }
                      >
                        {STATUS_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      {item.origin === 'user_entered' ? (
                        'Added by you'
                      ) : item.source_document_id && item.source_document_title ? (
                        <>
                          Accepted from <Link to={`/documents/${item.source_document_id}`}>{item.source_document_title}</Link>
                        </>
                      ) : (
                        'Accepted from a deleted document'
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="icon-button icon-button-danger icon-button-small"
                        aria-label={`Remove ${item.name}`}
                        title="Remove"
                        onClick={() => void act(async () => { await profileApi.removeCondition(item.id); await load() }, 'The condition could not be removed.')}
                      >
                        <TrashIcon />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <form className="inline-add" onSubmit={(event) => void addCondition(event)} noValidate aria-label="New condition">
          <FormField label="Add a condition" hint="For example diabetes or asthma" value={condition} onChange={(e) => setCondition(e.target.value)} maxLength={300} error={conditionError} />
          <SelectField label="Status" value={conditionStatus} onChange={(e) => setConditionStatus(e.target.value as ConditionStatus)} options={STATUS_OPTIONS} />
          <button type="submit" className="button button-secondary">
            Add condition
          </button>
        </form>

        {profile.suggestions.length > 0 && (
          <div className="suggestions-box" role="region" aria-labelledby="suggestions-title">
            <h3 id="suggestions-title">
              Suggested from your documents <span className="count">({profile.suggestions.length})</span>
            </h3>
            <p className="document-meta">Diagnoses as written in your documents. Not in your profile until you accept or correct them.</p>
            <ul className="suggestion-list">
              {profile.suggestions.map((suggestion) => (
                <SuggestionRow
                  key={suggestion.id}
                  suggestion={suggestion}
                  onReview={(action, name) =>
                    act(async () => show(await profileApi.reviewSuggestion(suggestion.id, action, name)), 'The suggestion could not be saved.')
                  }
                />
              ))}
            </ul>
          </div>
        )}
        <h3>Past surgeries</h3>
        <RecordList kind="surgery" items={profile.surgeries} addLabel="Add surgery" emptyText="No surgeries recorded." onChanged={load} />

        <h3>Hospitalizations</h3>
        {profile.document_stays.length > 0 && (
          <ul className="record-list">
            {profile.document_stays.map((stay) => (
              <li key={stay.source_document_id}>
                <span>
                  <strong>{stay.facility_name ?? 'Hospital stay'}</strong>
                  {(stay.admitted_on || stay.discharged_on) && (
                    <span className="mono">
                      {' '}
                      · {stay.admitted_on ? formatDayMonthYear(stay.admitted_on) : '?'} → {stay.discharged_on ? formatDayMonthYear(stay.discharged_on) : '?'}
                    </span>
                  )}
                  {stay.diagnoses.length > 0 && <span className="document-meta"> · {stay.diagnoses.join('; ')}</span>}
                  <span className="document-meta">
                    {' '}
                    · From <Link to={`/documents/${stay.source_document_id}`}>{stay.source_document_title}</Link>
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
        <RecordList
          kind="hospitalization"
          items={profile.hospitalizations}
          addLabel="Add hospitalization"
          emptyText={profile.document_stays.length ? 'Add stays that are not in your documents.' : 'No hospitalizations recorded.'}
          onChanged={load}
        />
      </section>

      <section className="card profile-section" aria-labelledby="medicines-title">
        <h2 id="medicines-title">Active medications</h2>
        {profile.active_medications.length === 0 ? (
          <p className="document-meta">
            No medicines marked as taking. Mark them on the <Link to="/medications">Medications page</Link>.
          </p>
        ) : (
          <>
            <ul className="record-list">
              {profile.active_medications.map((medicine) => (
                <li key={medicine.id}>
                  <span>
                    <strong>{[medicine.name, medicine.strength].filter(Boolean).join(' ')}</strong>
                    {medicine.dosage_text && ` — ${medicine.dosage_text}`}
                    <span className="medication-tag medication-tag-kind">{MEDICINE_KIND_LABELS[medicine.kind]}</span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="document-meta">
              Change these on the <Link to="/medications">Medications page</Link>.
            </p>
          </>
        )}
      </section>

      <section className="card profile-section" aria-labelledby="allergies-title">
        <h2 id="allergies-title">Allergies</h2>
        {profile.allergies.length === 0 ? (
          <p className="document-meta">No allergies recorded.</p>
        ) : (
          <ul className="allergy-list">
            {profile.allergies.map((item) => (
              <li key={item.id} className="allergy-chip">
                {item.name}
                {item.category && <span className="allergy-type">{ALLERGY_LABELS[item.category]}</span>}
                {item.reaction && <span className="allergy-reaction">{item.reaction}</span>}
                <button
                  type="button"
                  className="chip-remove"
                  aria-label={`Remove ${item.name}`}
                  onClick={() => void act(async () => { await profileApi.removeAllergy(item.id); await load() }, 'The allergy could not be removed.')}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
        <form className="inline-add" onSubmit={(event) => void addAllergy(event)} noValidate aria-label="New allergy">
          <FormField label="Add an allergy" hint="For example penicillin or peanuts" value={allergy} onChange={(e) => setAllergy(e.target.value)} maxLength={200} error={allergyError} />
          <SelectField
            label="Type"
            value={allergyCategory}
            onChange={(e) => setAllergyCategory(e.target.value as AllergyCategory | '')}
            options={[{ value: '', label: 'Choose' }, ...(Object.keys(ALLERGY_LABELS) as AllergyCategory[]).map((c) => ({ value: c, label: ALLERGY_LABELS[c] }))]}
          />
          <FormField label="Reaction (optional)" value={reaction} onChange={(e) => setReaction(e.target.value)} maxLength={300} />
          <button type="submit" className="button button-secondary">
            Add allergy
          </button>
        </form>
      </section>

      <section className="card profile-section" aria-labelledby="family-title">
        <h2 id="family-title">Family medical history</h2>
        <p className="document-meta">Conditions that run in your family, such as heart disease, stroke, or cancer.</p>
        <RecordList kind="family" items={profile.family_history} addLabel="Add family history" emptyText="No family history recorded." onChanged={load} />
      </section>
    </section>
  )
}
