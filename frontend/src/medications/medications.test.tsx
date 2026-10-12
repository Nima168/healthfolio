import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { errorResponse, jsonResponse, LOGGED_IN, renderAt, stubFetch } from '../test/helpers'
import type { Medication } from './medicationsApi'

function medication(overrides: Partial<Medication> = {}): Medication {
  return {
    id: 'm-1',
    name: 'Atorvastatin',
    strength: '10 mg',
    dosage_text: 'once daily at night',
    duration_text: '90 days',
    prescriber_name: 'Dr. Sample Physician',
    start_date: null,
    end_date: null,
    notes: null,
    status: 'unknown',
    origin: 'document_extracted',
    status_confirmed: false,
    edited: false,
    review_reason: null,
    source_document_id: 'doc-1',
    source_document_title: 'Prescription October',
    source_document_date: '2026-10-07',
    source_document_deleted: false,
    updated_at: '2026-10-12T08:00:00Z',
    ...overrides,
  }
}

const groupNames = () =>
  screen.getAllByRole('region', { name: /\(\d+\)/ }).map((region) => within(region).getByRole('heading').textContent)

describe('Medications page', () => {
  it('groups medicines by status, with their source and labels', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /medications': () =>
        jsonResponse(200, {
          items: [
            medication({ id: 'a', name: 'Vitamin D3', strength: '1000 IU', status: 'active', origin: 'user_entered', status_confirmed: true, source_document_id: null, source_document_title: null, source_document_date: null }),
            medication({ id: 'b', status: 'active', status_confirmed: true, edited: true }),
            medication({ id: 'c', name: 'Metformin', strength: '500 mg', review_reason: 'The strength is hard to read.' }),
            medication({ id: 'd', name: 'Amoxicillin', strength: null, status: 'stopped', status_confirmed: true, source_document_id: 'doc-9', source_document_title: null, source_document_date: null, source_document_deleted: true }),
          ],
        }),
    })
    renderAt('/medications')

    await screen.findByRole('region', { name: /Taking now/ })
    expect(groupNames()).toEqual(['Taking now (2)', 'Not confirmed (1)', 'Stopped (1)'])
    expect(screen.getByText(/Do not start, stop, or change a medicine without your doctor’s advice/)).toBeInTheDocument()

    const taking = screen.getByRole('region', { name: /Taking now/ })
    const [vitamin, atorvastatin] = within(taking).getAllByRole('row').slice(1)
    expect(within(vitamin).getByText('Added by you')).toBeInTheDocument()
    expect(within(atorvastatin).getByText('Confirmed by you')).toBeInTheDocument()
    expect(within(atorvastatin).getByText('Edited by you')).toBeInTheDocument()
    expect(within(atorvastatin).getByRole('link', { name: 'Prescription October' })).toHaveAttribute('href', '/documents/doc-1')
    expect(within(atorvastatin).getByText('07-Oct-2026')).toBeInTheDocument()

    const unsure = screen.getByRole('region', { name: /Not confirmed/ })
    expect(within(unsure).getByText('From document')).toBeInTheDocument()
    expect(within(unsure).getByText(/unclear – check original/)).toBeInTheDocument()
    expect(within(unsure).getByRole('button', { name: 'Mark taking' })).toBeInTheDocument()

    const stopped = screen.getByRole('region', { name: /Stopped/ })
    expect(within(stopped).getByText('Deleted document')).toBeInTheDocument()
    expect(within(stopped).queryByRole('button', { name: 'Mark stopped' })).not.toBeInTheDocument()
  })

  it('marks a medicine as taking', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /medications': () => jsonResponse(200, { items: [medication()] }),
      'PATCH /medications/m-1': () => jsonResponse(200, medication({ status: 'active', status_confirmed: true })),
    })
    renderAt('/medications')

    await userEvent.click(await screen.findByRole('button', { name: 'Mark taking' }))

    const taking = await screen.findByRole('region', { name: /Taking now/ })
    expect(within(taking).getByText('Confirmed by you')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /Not confirmed/ })).not.toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith('/medications/m-1') && init?.method === 'PATCH')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ status: 'active' })
  })

  it('adds a medicine', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /medications': () => jsonResponse(200, { items: [] }),
      'POST /medications': () =>
        jsonResponse(201, medication({ id: 'new', name: 'Vitamin D3', strength: '1000 IU', status: 'active', origin: 'user_entered', status_confirmed: true, source_document_id: null, source_document_title: null })),
    })
    renderAt('/medications')

    expect(await screen.findByText('No medicines yet.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Add medicine' }))
    const form = screen.getByRole('form', { name: 'Add medicine' })
    await userEvent.click(within(form).getByRole('button', { name: 'Add medicine' }))
    expect(within(form).getByText('Enter the medicine name.')).toBeInTheDocument()

    await userEvent.type(within(form).getByLabelText('Medicine name'), 'Vitamin D3')
    await userEvent.type(within(form).getByLabelText(/^Strength/), '1000 IU')
    await userEvent.click(within(form).getByRole('button', { name: 'Add medicine' }))

    const taking = await screen.findByRole('region', { name: /Taking now/ })
    expect(within(taking).getByText('Vitamin D3 1000 IU')).toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST' && String(init?.body).includes('Vitamin'))
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      name: 'Vitamin D3',
      strength: '1000 IU',
      dosage_text: null,
      duration_text: null,
      prescriber_name: null,
      start_date: null,
      end_date: null,
      notes: null,
      status: 'active',
    })
  })

  it('edits a medicine and shows server field errors', async () => {
    let attempts = 0
    stubFetch({
      ...LOGGED_IN,
      'GET /medications': () => jsonResponse(200, { items: [medication()] }),
      'PATCH /medications/m-1': () =>
        ++attempts === 1
          ? errorResponse(422, 'VALIDATION_ERROR', 'Invalid', [{ field: 'strength', issue: 'Too long.' }])
          : jsonResponse(200, medication({ strength: '20 mg', edited: true })),
    })
    renderAt('/medications')

    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    const form = screen.getByRole('form', { name: 'Edit Atorvastatin' })
    const strength = within(form).getByLabelText(/^Strength/)
    await userEvent.clear(strength)
    await userEvent.type(strength, '20 mg')
    await userEvent.click(within(form).getByRole('button', { name: 'Save changes' }))
    expect(await within(form).findByText('Too long.')).toBeInTheDocument()

    await userEvent.click(within(form).getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Atorvastatin 20 mg')).toBeInTheDocument()
    expect(screen.queryByRole('form')).not.toBeInTheDocument()
    expect(screen.getByText('Edited by you')).toBeInTheDocument()
  })

  it('shows the change history', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /medications': () => jsonResponse(200, { items: [medication({ status: 'active', status_confirmed: true })] }),
      'GET /medications/m-1/history': () =>
        jsonResponse(200, {
          items: [
            { id: 'h2', change: 'edited', changed_at: '2026-10-12T09:00:00Z', changes: { strength: ['10 mg', '20 mg'], start_date: [null, '2026-10-07'] } },
            { id: 'h1', change: 'status_changed', changed_at: '2026-10-12T08:00:00Z', changes: { status: ['unknown', 'active'] } },
          ],
        }),
    })
    renderAt('/medications')

    await userEvent.click(await screen.findByRole('button', { name: 'History' }))

    expect(await screen.findByText('Strength: 10 mg → 20 mg')).toBeInTheDocument()
    expect(screen.getByText('Start date: — → 07-Oct-2026')).toBeInTheDocument()
    expect(screen.getByText('Status: Not sure → Taking')).toBeInTheDocument()
    expect(screen.getByText(/as read from the document/)).toBeInTheDocument()
  })

  it('asks before removing a medicine', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /medications': () => jsonResponse(200, { items: [medication()] }),
      'DELETE /medications/m-1': () => new Response(null, { status: 204 }),
    })
    renderAt('/medications')

    await userEvent.click(await screen.findByRole('button', { name: 'Remove Atorvastatin 10 mg' }))
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('Its change history is kept.')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Keep' }))
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)

    await userEvent.click(screen.getByRole('button', { name: 'Remove Atorvastatin 10 mg' }))
    await userEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove' }))

    expect(await screen.findByText('No medicines yet.')).toBeInTheDocument()
  })
})
