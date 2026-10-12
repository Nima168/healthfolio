import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { errorResponse, jsonResponse, LOGGED_IN, renderAt, stubFetch } from '../test/helpers'
import type { Profile } from './profileApi'
import type { VitalReading } from './vitalsApi'

const PROFILE: Profile = {
  values: { date_of_birth: null, sex: null, blood_group: null, height: null, weight: null },
  bmi: null,
  bmi_category: null,
  allergies: [],
  conditions: [],
  suggestions: [],
  surgeries: [],
  hospitalizations: [],
  document_stays: [],
  family_history: [],
  active_medications: [],
}

function reading(overrides: Partial<VitalReading> = {}): VitalReading {
  return {
    id: 'v-1',
    measured_on: '2026-10-12',
    measured_time: '08:30:00',
    systolic: 128,
    diastolic: 84,
    heart_rate: 72,
    context: 'morning, at home',
    ...overrides,
  }
}

describe('Vital sign readings', () => {
  it('shows the latest blood pressure and heart rate with their dates, and every reading', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /profile': () => jsonResponse(200, PROFILE),
      'GET /vitals': () =>
        jsonResponse(200, {
          items: [
            reading({ id: 'v-2', measured_on: '2026-10-13', measured_time: null, systolic: null, diastolic: null, heart_rate: 80, context: null }),
            reading(),
          ],
        }),
    })
    renderAt('/profile')

    await screen.findByText('128/84 mmHg')
    const pressure = screen.getByLabelText('Latest blood pressure')
    expect(pressure).toHaveTextContent('128/84')
    expect(pressure).toHaveTextContent('12-Oct-2026 08:30')
    const rate = screen.getByLabelText('Latest heart rate')
    expect(rate).toHaveTextContent('80')
    expect(rate).toHaveTextContent('13-Oct-2026')

    const table = screen.getByRole('table', { name: 'Your readings' })
    expect(within(table).getAllByRole('row')).toHaveLength(3)
    expect(within(table).getByText('128/84 mmHg')).toBeInTheDocument()
    // Shown as recorded: no high or low labels.
    expect(screen.queryByText(/high|low/i, { selector: '.vital-tile *' })).not.toBeInTheDocument()
  })

  it('adds a reading and shows server errors', async () => {
    let attempts = 0
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /profile': () => jsonResponse(200, PROFILE),
      'GET /vitals': () => jsonResponse(200, { items: [] }),
      'POST /vitals': () =>
        ++attempts === 1
          ? errorResponse(422, 'VALIDATION_ERROR', 'Invalid', [
              { field: 'diastolic', issue: 'The first number (systolic) should be higher than the second (diastolic).' },
            ])
          : jsonResponse(201, reading()),
    })
    renderAt('/profile')

    const form = await screen.findByRole('form', { name: 'New reading' })
    await userEvent.type(within(form).getByLabelText(/^Systolic/), '80')
    await userEvent.type(within(form).getByLabelText(/^Diastolic/), '120')
    await userEvent.click(within(form).getByRole('button', { name: 'Add reading' }))
    expect(await within(form).findByText(/should be higher than the second/)).toBeInTheDocument()

    await userEvent.clear(within(form).getByLabelText(/^Systolic/))
    await userEvent.type(within(form).getByLabelText(/^Systolic/), '128')
    await userEvent.clear(within(form).getByLabelText(/^Diastolic/))
    await userEvent.type(within(form).getByLabelText(/^Diastolic/), '84')
    await userEvent.click(within(form).getByRole('button', { name: 'Add reading' }))

    const posts = fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith('/vitals') && init?.method === 'POST')
    expect(posts).toHaveLength(2)
    const body = JSON.parse(String(posts[1][1]?.body))
    expect(body).toMatchObject({ systolic: 128, diastolic: 84 })
    expect(body.measured_on).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(body).not.toHaveProperty('heart_rate')
  })
})
