import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { toFormErrors, type FormErrors } from '../auth/formErrors'
import { FormField } from '../components/FormField'
import { TrashIcon } from '../components/icons'
import { formatDayMonthYear, todayIso } from '../documents/format'
import { vitalsApi, type NewVitalReading, type VitalReading } from './vitalsApi'

const SHOWN = 5

const hhmm = (time: string | null) => (time ? time.slice(0, 5) : null)

function when(reading: VitalReading): string {
  return [formatDayMonthYear(reading.measured_on), hhmm(reading.measured_time)].filter(Boolean).join(' ')
}

const EMPTY = { measured_on: '', measured_time: '', systolic: '', diastolic: '', heart_rate: '', context: '' }

/** Blood pressure and heart rate as dated readings: shown as recorded, never labelled high or low. */
export function VitalsSection() {
  const [readings, setReadings] = useState<VitalReading[] | null>(null)
  const [form, setForm] = useState({ ...EMPTY, measured_on: todayIso() })
  const [errors, setErrors] = useState<FormErrors>({ fields: {} })
  const [showAll, setShowAll] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setReadings((await vitalsApi.list()).items)
      setLoadError(null)
    } catch (e) {
      setLoadError(toFormErrors(e, 'Your readings could not be loaded.').general ?? null)
    }
  }, [])

  useEffect(() => {
    // Loading from the backend is an external sync; state is only set after the request resolves.
    // oxlint-disable-next-line react/set-state-in-effect
    void load()
  }, [load])

  const set = (field: keyof typeof EMPTY) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [field]: event.target.value }))

  async function add(event: FormEvent) {
    event.preventDefault()
    const number = (value: string) => (value.trim() ? Number(value) : undefined)
    const reading: NewVitalReading = {
      measured_on: form.measured_on,
      ...(form.measured_time ? { measured_time: form.measured_time } : {}),
      ...(form.systolic.trim() ? { systolic: number(form.systolic) } : {}),
      ...(form.diastolic.trim() ? { diastolic: number(form.diastolic) } : {}),
      ...(form.heart_rate.trim() ? { heart_rate: number(form.heart_rate) } : {}),
      ...(form.context.trim() ? { context: form.context.trim() } : {}),
    }
    if (!form.measured_on) {
      setErrors({ fields: { measured_on: 'Enter the date of the reading.' } })
      return
    }
    try {
      await vitalsApi.add(reading)
      setForm({ ...EMPTY, measured_on: todayIso() })
      setErrors({ fields: {} })
      await load()
    } catch (e) {
      setErrors(toFormErrors(e, 'The reading could not be saved.'))
    }
  }

  const latestPressure = readings?.find((r) => r.systolic !== null)
  const latestRate = readings?.find((r) => r.heart_rate !== null)
  const shown = showAll ? (readings ?? []) : (readings ?? []).slice(0, SHOWN)

  return (
    <section className="card profile-section" aria-labelledby="vitals-title">
      <h2 id="vitals-title">Vital signs</h2>
      <p className="document-meta">
        Blood pressure and heart rate change over time, so each reading is kept with its date. They are shown as recorded,
        without high or low labels; see them over time on the <Link to="/timeline?cat=vitals">Timeline</Link>.
      </p>
      {loadError && (
        <p role="alert" className="form-alert">
          {loadError}
        </p>
      )}

      <div className="vitals-latest">
        <div className="vital-tile" aria-label="Latest blood pressure">
          <span className="vital-name">Blood pressure</span>
          <span className="vital-value">{latestPressure ? `${latestPressure.systolic}/${latestPressure.diastolic}` : '—'}</span>
          <span className="vital-unit">mmHg</span>
          <span className="mono vital-when">{latestPressure ? when(latestPressure) : 'No reading yet'}</span>
        </div>
        <div className="vital-tile" aria-label="Latest heart rate">
          <span className="vital-name">Heart rate</span>
          <span className="vital-value">{latestRate ? latestRate.heart_rate : '—'}</span>
          <span className="vital-unit">bpm</span>
          <span className="mono vital-when">{latestRate ? when(latestRate) : 'No reading yet'}</span>
        </div>
      </div>

      <form className="vitals-form" onSubmit={(event) => void add(event)} noValidate aria-label="New reading">
        {errors.general && (
          <p role="alert" className="form-alert">
            {errors.general}
          </p>
        )}
        <div className="profile-grid">
          <FormField label="Date" type="date" value={form.measured_on} onChange={set('measured_on')} error={errors.fields.measured_on} />
          <FormField label="Time (optional)" type="time" value={form.measured_time} onChange={set('measured_time')} />
          <FormField label="Systolic (mmHg)" hint="Top number" inputMode="numeric" value={form.systolic} onChange={set('systolic')} error={errors.fields.systolic} />
          <FormField label="Diastolic (mmHg)" hint="Bottom number" inputMode="numeric" value={form.diastolic} onChange={set('diastolic')} error={errors.fields.diastolic} />
          <FormField label="Heart rate (bpm)" inputMode="numeric" value={form.heart_rate} onChange={set('heart_rate')} error={errors.fields.heart_rate} />
          <FormField label="Notes (optional)" hint="For example morning, at home" value={form.context} onChange={set('context')} maxLength={200} />
        </div>
        <button type="submit" className="button button-secondary">
          Add reading
        </button>
      </form>

      {readings && readings.length > 0 && (
        <div className="document-table-wrap vitals-table-wrap">
          <table className="document-table">
            <caption className="visually-hidden">Your readings</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Blood pressure</th>
                <th scope="col">Heart rate</th>
                <th scope="col">Notes</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((reading) => (
                <tr key={reading.id}>
                  <th scope="row" className="mono">
                    {when(reading)}
                  </th>
                  <td>{reading.systolic !== null ? `${reading.systolic}/${reading.diastolic} mmHg` : '—'}</td>
                  <td>{reading.heart_rate !== null ? `${reading.heart_rate} bpm` : '—'}</td>
                  <td>{reading.context ?? '—'}</td>
                  <td>
                    <button
                      type="button"
                      className="icon-button icon-button-danger icon-button-small"
                      aria-label={`Remove reading of ${when(reading)}`}
                      title="Remove"
                      onClick={() => void vitalsApi.remove(reading.id).then(load)}
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
      {readings && readings.length > SHOWN && (
        <button type="button" className="button button-small button-secondary" onClick={() => setShowAll((v) => !v)}>
          {showAll ? 'Show fewer' : `Show all ${readings.length} readings`}
        </button>
      )}
    </section>
  )
}
