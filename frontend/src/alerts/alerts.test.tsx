import { fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { jsonResponse, LOGGED_IN, renderAt, stubFetch } from '../test/helpers'
import type { SafetyAlert } from './alertsApi'

function alert(overrides: Partial<SafetyAlert> = {}): SafetyAlert {
  return {
    id: 'a-1',
    rule_code: 'RESULT_OUTSIDE_REPORT_RANGE',
    rule_version: 1,
    rule_description: 'A result is outside the reference range printed on the same report; for review.',
    severity: 'warning',
    status: 'open',
    title: "HbA1c 6.1 % is above the report's range (4.0 - 5.6)",
    reason: 'The report gives 4.0 - 5.6 as the reference range for HbA1c. This is a rule-based flag for review, not a diagnosis.',
    uncertainty: 'Reference ranges differ between laboratories.',
    next_steps: 'Discuss this result with your doctor.',
    explanation_text: null,
    source_document_id: 'doc-1',
    source_document_title: 'CBC October',
    report_type: 'lab_report',
    report_date: '2026-10-07',
    created_at: '2026-10-12T09:00:00Z',
    acknowledged_at: null,
    resolved_at: null,
    resolved_by: null,
    resolution_note: null,
    history: [{ event: 'raised', actor: 'system', note: null, occurred_at: '2026-10-12T09:00:00Z' }],
    ...overrides,
  }
}

const row = (name: RegExp) => screen.getByRole('row', { name })

describe('Alerts page', () => {
  it('lists alerts in tables by status, with the report each came from', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /alerts': () =>
        jsonResponse(200, {
          items: [
            alert(),
            alert({ id: 'a-4', title: "Ferritin 29 ng/mL is below the report's range (30 - 400)", source_document_title: 'Anemia panel', source_document_id: 'doc-4' }),
            alert({ id: 'a-2', title: "LDL 160 mg/dL is above the report's range (< 100)", status: 'acknowledged' }),
            alert({
              id: 'a-3',
              title: "CRP 6.2 mg/L is above the report's range (< 5.0)",
              status: 'resolved',
              resolved_by: 'system',
              resolution_note: 'The result is no longer in your records.',
              source_document_id: null,
              source_document_title: null,
            }),
          ],
        }),
    })
    renderAt('/alerts')

    const hba1c = await screen.findByRole('row', { name: /HbA1c/ })
    expect(within(hba1c).getByRole('link', { name: 'CBC October' })).toHaveAttribute('href', '/documents/doc-1')
    expect(within(hba1c).getByText('For review')).toBeInTheDocument()
    expect(within(hba1c).getByText('12-Oct-2026')).toBeInTheDocument()
    // Not crowded: no per-alert "Keep in mind" or "What to do".
    expect(screen.queryByText('Keep in mind')).not.toBeInTheDocument()
    expect(screen.queryByText('Discuss this result with your doctor.')).not.toBeInTheDocument()

    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual(['Open (2)', 'Acknowledged (1)', 'Resolved (1)'])
    // Alerts from the same report sit together, reports A to Z.
    const open = screen.getByRole('table', { name: 'Open alerts' })
    const reports = within(open).getAllByRole('row').slice(1).map((r) => within(r).getAllByRole('cell')[0].textContent)
    expect(reports).toEqual(['Anemia panel', 'CBC October'])

    expect(within(row(/LDL/)).queryByRole('button', { name: 'Acknowledge' })).not.toBeInTheDocument()
    expect(within(row(/CRP/)).getByText('Deleted document')).toBeInTheDocument()
    expect(within(row(/CRP/)).queryByRole('button', { name: 'Resolve' })).not.toBeInTheDocument()

    // Always present, never generated.
    expect(screen.getByText(/call your local emergency number now/)).toBeInTheDocument()
    expect(screen.getByText(/Having no alerts does not mean you are healthy/)).toBeInTheDocument()
  })

  it('filters by report type and report date, keeping the filters in the address', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /alerts': () =>
        jsonResponse(200, {
          items: [
            alert(),
            alert({ id: 'a-2', title: 'Creatinine 1.31 above', report_type: 'discharge_summary', report_date: '2026-08-13', source_document_title: 'Discharge August' }),
            alert({ id: 'a-3', title: 'QTc 468 ms above', report_type: 'test_report', report_date: null, source_document_title: 'ECG' }),
          ],
        }),
    })
    renderAt('/alerts')

    const type = await screen.findByLabelText('Report type')
    expect(within(type).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'All types',
      'Discharge summary',
      'Laboratory reports',
      'Test report (ECG etc.)',
    ])
    expect(within(row(/HbA1c/)).getByText('07-Oct-2026')).toBeInTheDocument()

    await userEvent.selectOptions(type, 'discharge_summary')
    expect(screen.getByRole('heading', { name: 'Open (1)' })).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /Creatinine/ })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(screen.getByRole('heading', { name: 'Open (3)' })).toBeInTheDocument()

    // A date range leaves out alerts whose report has no known date.
    fireEvent.change(screen.getByLabelText('Report date from'), { target: { value: '2026-09-01' } })
    expect(screen.getByRole('heading', { name: 'Open (1)' })).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /HbA1c/ })).toBeInTheDocument()
    expect(screen.getByText(/no known date are not shown/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Report date to'), { target: { value: '2026-09-15' } })
    expect(await screen.findByText('No alerts match these filters.')).toBeInTheDocument()
  })

  it('reads the filters from the address', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /alerts': () =>
        jsonResponse(200, { items: [alert(), alert({ id: 'a-2', title: 'QTc 468 ms above', report_type: 'test_report' })] }),
    })
    renderAt('/alerts?type=test_report')

    expect(await screen.findByRole('row', { name: /QTc/ })).toBeInTheDocument()
    expect(screen.queryByRole('row', { name: /HbA1c/ })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Report type')).toHaveValue('test_report')
  })

  it('shows the reason, history, and rule under Details', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /alerts': () => jsonResponse(200, { items: [alert()] }) })
    renderAt('/alerts')

    await userEvent.click(await screen.findByRole('button', { name: 'Details' }))

    expect(screen.getByText(/not a diagnosis/)).toBeInTheDocument()
    expect(screen.getByText(/Raised \(automatically\)/)).toBeInTheDocument()
    expect(screen.getByText(/RESULT_OUTSIDE_REPORT_RANGE v1/)).toBeInTheDocument()
  })

  it('acknowledges an alert', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /alerts': () => jsonResponse(200, { items: [alert()] }),
      'PATCH /alerts/a-1': () => jsonResponse(200, alert({ status: 'acknowledged', acknowledged_at: '2026-10-12T10:00:00Z' })),
    })
    renderAt('/alerts')

    await userEvent.click(await screen.findByRole('button', { name: 'Acknowledge' }))

    expect(await screen.findByRole('heading', { name: 'Acknowledged (1)' })).toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ status: 'acknowledged' })
  })

  it('resolves an alert with an optional note, explaining that this is not a clean bill of health', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /alerts': () => jsonResponse(200, { items: [alert()] }),
      'PATCH /alerts/a-1': () =>
        jsonResponse(200, alert({ status: 'resolved', resolved_by: 'user', resolution_note: 'Seen by Dr. Sample' })),
    })
    renderAt('/alerts')

    await userEvent.click(await screen.findByRole('button', { name: 'Resolve' }))
    const group = screen.getByRole('group', { name: 'Resolve this alert' })
    expect(group).toHaveTextContent('This does not mean the result is normal.')
    await userEvent.type(within(group).getByLabelText('Note (optional)'), 'Seen by Dr. Sample')
    await userEvent.click(within(group).getByRole('button', { name: 'Resolve' }))

    expect(await screen.findByRole('heading', { name: 'Resolved (1)' })).toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ status: 'resolved', note: 'Seen by Dr. Sample' })
  })

  it('says that no alerts is not a health check', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /alerts': () => jsonResponse(200, { items: [] }) })
    renderAt('/alerts')

    expect(await screen.findByText('No alerts.')).toBeInTheDocument()
    expect(screen.getByText(/This is not a health check/)).toBeInTheDocument()
  })
})
