import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { errorResponse, jsonResponse, LOGGED_IN, renderAt, stubFetch } from '../test/helpers'
import type { Profile } from './profileApi'

function profile(overrides: Partial<Profile> = {}): Profile {
  return {
    values: {
      date_of_birth: { value: '1985-04-12', unit: null, updated_at: '2026-10-12T08:00:00Z' },
      sex: { value: 'female', unit: null, updated_at: '2026-10-12T08:00:00Z' },
      blood_group: null,
      height: { value: '162', unit: 'cm', updated_at: '2026-10-12T08:00:00Z' },
      weight: null,
    },
    bmi: null,
    bmi_category: null,
    allergies: [{ id: 'al-1', name: 'Penicillin', category: 'drug', reaction: 'Hives', added_at: '2026-10-12T08:00:00Z' }],
    surgeries: [],
    hospitalizations: [],
    document_stays: [],
    family_history: [],
    active_medications: [],
    conditions: [
      { id: 'c-1', name: 'Type 2 diabetes', status: 'active', origin: 'user_entered', source_document_id: null, source_document_title: null },
      {
        id: 'c-2',
        name: 'Acute gastroenteritis',
        status: 'unknown',
        origin: 'suggestion_accepted',
        source_document_id: 'doc-9',
        source_document_title: 'Discharge August',
      },
    ],
    suggestions: [
      {
        id: 's-1',
        name: 'Hypokalemia and mild hyponatremia, corrected',
        source_document_id: 'doc-9',
        source_document_title: 'Discharge August',
        source_document_date: '2026-08-13',
      },
    ],
    ...overrides,
  }
}

describe('Health profile', () => {
  it('shows details, allergies, conditions, and suggestions apart from confirmed data', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /profile': () => jsonResponse(200, profile()) })
    renderAt('/profile')

    expect(await screen.findByLabelText('Date of birth')).toHaveValue('1985-04-12')
    expect(screen.getByLabelText('Sex')).toHaveValue('female')
    expect(screen.getByLabelText('Height (cm)')).toHaveValue('162')
    expect(screen.getByRole('note', { name: 'Allergies' })).toHaveTextContent('Allergies: Penicillin (drug) — Hives')
    expect(screen.queryByLabelText(/Blood pressure/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Heart rate/)).not.toBeInTheDocument()
    // Suggestions sit in Medical history; a notice at the top links to them.
    expect(screen.getByRole('link', { name: /1 diagnosis from your documents to review/ })).toHaveAttribute('href', '#suggestions-title')
    expect(within(screen.getByRole('region', { name: 'Medical history' })).getByRole('region', { name: /Suggested from your documents/ })).toBeInTheDocument()

    const suggestions = screen.getByRole('region', { name: /Suggested from your documents/ })
    expect(within(suggestions).getByText('Hypokalemia and mild hyponatremia, corrected')).toBeInTheDocument()
    expect(within(suggestions).getByText(/Not in your profile until you accept/)).toBeInTheDocument()
    expect(within(suggestions).getByRole('link', { name: 'Discharge August' })).toHaveAttribute('href', '/documents/doc-9')

    const conditions = screen.getByRole('region', { name: 'Medical history' })
    expect(within(conditions).getByRole('row', { name: /Type 2 diabetes/ })).toHaveTextContent('Added by you')
    expect(within(conditions).getByRole('row', { name: /Acute gastroenteritis/ })).toHaveTextContent('Accepted from Discharge August')
    const table = within(conditions).getByRole('table', { name: 'Your conditions' })
    expect(within(table).queryByText('Hypokalemia and mild hyponatremia, corrected')).not.toBeInTheDocument()
  })

  it('saves only the changed details and shows server field errors', async () => {
    let attempts = 0
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /profile': () => jsonResponse(200, profile()),
      'PATCH /profile/values': () =>
        ++attempts === 1
          ? errorResponse(422, 'VALIDATION_ERROR', 'Invalid', [{ field: 'weight', issue: 'Enter a value between 1 and 500 kg.' }])
          : jsonResponse(200, profile()),
    })
    renderAt('/profile')

    await userEvent.type(await screen.findByLabelText('Weight (kg)'), '900')
    await userEvent.click(screen.getByRole('button', { name: 'Save details' }))
    expect(await screen.findByText('Enter a value between 1 and 500 kg.')).toBeInTheDocument()

    await userEvent.clear(screen.getByLabelText('Weight (kg)'))
    await userEvent.type(screen.getByLabelText('Weight (kg)'), '61')
    await userEvent.click(screen.getByRole('button', { name: 'Save details' }))
    expect(await screen.findByText('Saved.')).toBeInTheDocument()
    const call = fetchMock.mock.calls.filter(([, init]) => init?.method === 'PATCH').at(-1)
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ weight: '61' })
  })

  it('shows the change history', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /profile': () => jsonResponse(200, profile()),
      'GET /profile/history': () =>
        jsonResponse(200, {
          items: [
            { field: 'weight', change: 'changed', previous_value: '61.5', new_value: '60', changed_at: '2026-10-12T09:00:00Z' },
            { field: 'sex', change: 'added', previous_value: null, new_value: 'female', changed_at: '2026-10-12T08:00:00Z' },
          ],
        }),
    })
    renderAt('/profile')

    await userEvent.click(await screen.findByRole('button', { name: 'Change history' }))

    expect(await screen.findByText(/Weight \(kg\): 61.5 → 60/)).toBeInTheDocument()
    expect(screen.getByText(/Sex: added Female/)).toBeInTheDocument()
  })

  it('accepts, corrects, or rejects a suggestion', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /profile': () => jsonResponse(200, profile()),
      'POST /profile/suggestions/s-1': () => jsonResponse(200, profile({ suggestions: [] })),
    })
    renderAt('/profile')

    const suggestions = await screen.findByRole('region', { name: /Suggested from your documents/ })
    await userEvent.click(within(suggestions).getByRole('button', { name: 'Correct' }))
    const name = within(suggestions).getByLabelText('Corrected name')
    await userEvent.clear(name)
    await userEvent.type(name, 'Hypokalemia')
    await userEvent.click(within(suggestions).getByRole('button', { name: 'Save' }))

    await screen.findByRole('region', { name: 'Medical history' })
    expect(screen.queryByRole('region', { name: /Suggested from your documents/ })).not.toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/profile/suggestions/s-1'))
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ action: 'correct', name: 'Hypokalemia' })
  })

  it('adds and removes allergies and conditions', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /profile': () => jsonResponse(200, profile({ suggestions: [] })),
      'POST /profile/allergies': () => jsonResponse(201, { id: 'al-2', name: 'Peanuts', added_at: '' }),
      'DELETE /profile/allergies/al-1': () => new Response(null, { status: 204 }),
      'POST /profile/conditions': () => errorResponse(409, 'ALREADY_RECORDED', 'This condition is already in your profile.'),
    })
    renderAt('/profile')

    await screen.findByLabelText('Add an allergy')
    await userEvent.click(screen.getByRole('button', { name: 'Add allergy' }))
    expect(await screen.findByText('Enter the allergy.')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Add an allergy'), 'Peanuts')
    await userEvent.selectOptions(screen.getByLabelText('Type'), 'food')
    await userEvent.click(screen.getByRole('button', { name: 'Add allergy' }))
    const added = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith('/profile/allergies') && init?.method === 'POST')
    expect(JSON.parse(String(added?.[1]?.body))).toEqual({ name: 'Peanuts', category: 'food' })
    await userEvent.click(screen.getByRole('button', { name: 'Remove Penicillin' }))
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(true)

    await userEvent.type(screen.getByLabelText('Add a condition'), 'Type 2 diabetes')
    await userEvent.click(screen.getByRole('button', { name: 'Add condition' }))
    expect(await screen.findByText('This condition is already in your profile.')).toBeInTheDocument()
  })

  it('shows BMI, hospital stays from documents, and active medications', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /profile': () =>
        jsonResponse(
          200,
          profile({
            bmi: 27.3,
            bmi_category: 'overweight',
            suggestions: [],
            document_stays: [
              {
                source_document_id: 'doc-9',
                source_document_title: 'Discharge August',
                facility_name: 'Sampleville General',
                admitted_on: '2026-08-10',
                discharged_on: '2026-08-13',
                diagnoses: ['Acute gastroenteritis'],
              },
            ],
            active_medications: [
              { id: 'm-1', name: 'Vitamin D3', strength: '1000 IU', dosage_text: 'once daily', kind: 'supplement' },
            ],
          }),
        ),
    })
    renderAt('/profile')

    const bmi = await screen.findByRole('group', { name: 'BMI' })
    expect(bmi).toHaveTextContent('27.3')
    expect(within(bmi).getByText('Overweight (25.0 to 29.9)')).toBeInTheDocument()
    const history = screen.getByRole('region', { name: 'Medical history' })
    expect(within(history).getByText('Sampleville General')).toBeInTheDocument()
    expect(within(history).getByText(/10-Aug-2026 → 13-Aug-2026/)).toBeInTheDocument()
    const medicines = screen.getByRole('region', { name: 'Active medications' })
    expect(within(medicines).getByText('Vitamin D3 1000 IU')).toBeInTheDocument()
    expect(within(medicines).getByText('Supplement')).toBeInTheDocument()
  })

  it('adds family history with the relative', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /profile': () => jsonResponse(200, profile({ suggestions: [] })),
      'POST /profile/records': () =>
        jsonResponse(201, { id: 'r-1', kind: 'family', name: 'Heart disease', occurred_on: null, relation: 'Father', notes: null }),
    })
    renderAt('/profile')

    const family = await screen.findByRole('region', { name: 'Family medical history' })
    await userEvent.type(within(family).getByLabelText('Condition'), 'Heart disease')
    await userEvent.click(within(family).getByRole('button', { name: 'Add family history' }))
    expect(within(family).getByText('Choose who in your family.')).toBeInTheDocument()

    await userEvent.selectOptions(within(family).getByLabelText('Relative'), 'Father')
    await userEvent.click(within(family).getByRole('button', { name: 'Add family history' }))
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/profile/records'))
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ kind: 'family', name: 'Heart disease', relation: 'Father' })
  })

  it('does not give an adult BMI category under 18, and asks for height and weight when missing', async () => {
    let call = 0
    stubFetch({
      ...LOGGED_IN,
      'GET /profile': () =>
        jsonResponse(200, ++call === 1 ? profile({ suggestions: [], bmi: 22.1, bmi_category: null }) : profile()),
    })
    renderAt('/profile')

    const bmi = await screen.findByRole('group', { name: 'BMI' })
    expect(bmi).toHaveTextContent('22.1')
    expect(within(bmi).getByText('Adult categories do not apply under 18.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /to review/ })).not.toBeInTheDocument()
  })
})

