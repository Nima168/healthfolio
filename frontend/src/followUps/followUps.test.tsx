import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { jsonResponse, LOGGED_IN, renderAt, stubFetch } from '../test/helpers'
import type { FollowUp } from './followUpsApi'

function followUp(overrides: Partial<FollowUp> = {}): FollowUp {
  return {
    id: 'fu-1',
    title: 'Kidney function test',
    kind: 'investigation',
    due_date: '2026-11-04',
    status: 'scheduled',
    overdue: false,
    completed_at: null,
    source_document_id: 'doc-1',
    source_document_title: 'Prescription October',
    ...overrides,
  }
}

const rowTexts = (group: HTMLElement) => within(group).getAllByRole('listitem').map((li) => li.textContent)

describe('Checkups and Follow-ups page', () => {
  it('groups follow-ups by the report they came from', async () => {
    const august = { source_document_id: 'doc-2', source_document_title: 'Discharge August' }
    stubFetch({
      ...LOGGED_IN,
      'GET /follow-ups': () =>
        jsonResponse(200, {
          items: [
            followUp({ id: 'a', title: 'CBC', due_date: '2026-12-07' }),
            followUp({ id: 'b' }),
            followUp({ id: 'c', title: 'Eye checkup', due_date: '2026-10-01', overdue: true, ...august }),
            followUp({ id: 'd', title: 'HbA1c', due_date: '2026-09-01', status: 'completed', ...august }),
            followUp({ id: 'e', title: 'X-ray', source_document_id: 'doc-3', source_document_title: null }),
          ],
        }),
    })
    renderAt('/follow-ups')

    const groups = await screen.findAllByRole('region', { name: /pending of/ })
    // The report with the soonest pending follow-up comes first.
    expect(groups.map((group) => within(group).getByRole('heading').textContent)).toEqual([
      'Discharge August (1 pending of 2)',
      'Prescription October (2 pending of 2)',
      'From a deleted document (1 pending of 1)',
    ])
    expect(within(groups[0]).getByRole('link', { name: 'Discharge August' })).toHaveAttribute('href', '/documents/doc-2')

    // Within a report: date order, each with its own status.
    expect(rowTexts(groups[0])).toEqual([
      '01-Sep-2026 · HbA1cDoneTestUndoDelete',
      '01-Oct-2026 · Eye checkupOverdueTestMark doneCancelDelete',
    ])
    expect(rowTexts(groups[1])).toEqual([
      '04-Nov-2026 · Kidney function testTestMark doneCancelDelete',
      '07-Dec-2026 · CBCTestMark doneCancelDelete',
    ])
    expect(within(groups[2]).queryByRole('link')).not.toBeInTheDocument()
  })

  it('marks a follow-up as done within its report', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /follow-ups': () => jsonResponse(200, { items: [followUp()] }),
      'PATCH /follow-ups/fu-1': () =>
        jsonResponse(200, followUp({ status: 'completed', completed_at: '2026-10-11T10:00:00Z' })),
    })
    renderAt('/follow-ups')

    await userEvent.click(await screen.findByRole('button', { name: 'Mark done' }))

    const group = await screen.findByRole('region', { name: /Prescription October/ })
    expect(await within(group).findByText('Done')).toBeInTheDocument()
    expect(within(group).getByRole('heading')).toHaveTextContent('(0 pending of 1)')
    expect(within(group).getByRole('button', { name: 'Undo' })).toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/follow-ups/fu-1'))
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ status: 'completed' })
  })

  it('deletes a follow-up only after confirming', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /follow-ups': () => jsonResponse(200, { items: [followUp(), followUp({ id: 'fu-2', title: 'CBC' })] }),
      'DELETE /follow-ups/fu-1': () => new Response(null, { status: 204 }),
    })
    renderAt('/follow-ups')

    await userEvent.click(await screen.findByRole('button', { name: 'Delete Kidney function test' }))
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('Delete Kidney function test permanently? It cannot be undone.')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Keep' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)

    await userEvent.click(screen.getByRole('button', { name: 'Delete Kidney function test' }))
    await userEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete' }))

    expect(await screen.findByRole('heading', { name: /1 pending of 1/ })).toBeInTheDocument()
    expect(screen.queryByText(/Kidney function test/)).not.toBeInTheDocument()
    expect(screen.getByText(/CBC/)).toBeInTheDocument()
  })

  it('explains how to add follow-ups when there are none', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /follow-ups': () => jsonResponse(200, { items: [] }) })
    renderAt('/follow-ups')

    expect(await screen.findByText('No follow-ups yet.')).toBeInTheDocument()
    expect(screen.getByText(/Reminders are not sent yet/)).toBeInTheDocument()
  })
})
