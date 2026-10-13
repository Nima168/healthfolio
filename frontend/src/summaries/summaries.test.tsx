import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { errorResponse, jsonResponse, LOGGED_IN, renderAt, stubFetch } from '../test/helpers'
import type { AiSummary, SummaryState } from './summariesApi'

const SUMMARY: AiSummary = {
  id: 'sum-1',
  scope: 'history',
  created_at: '2026-10-13T09:00:00Z',
  model_version: 'qwen/qwen3.8-27b',
  sections: [
    {
      key: 'results',
      title: 'Results',
      sentences: [
        { text: 'Your HbA1c of 6.1 % is above the range 4.0 - 5.6 printed on the report.', kind: 'record', fact_ids: ['F1'] },
        { text: 'This is worth discussing at your next doctor visit.', kind: 'interpretation', fact_ids: ['F1'] },
      ],
    },
    { key: 'gaps', title: 'Missing or unclear information', sentences: [{ text: 'One medicine is not confirmed.', kind: 'record', fact_ids: ['C1'] }] },
  ],
  explanations: [{ term: 'HbA1c', text: 'A blood test that reflects average blood sugar.', fact_ids: ['F1'] }],
  insights: [{ id: 'C1', text: '1 medicine read from documents not yet confirmed as taking or stopped.', link: '/medications' }],
  sources: {
    F1: {
      kind: 'lab_results',
      title: 'Lab results: 2 tests',
      date: '2026-03-14',
      trust: 'from_document',
      source_document_id: 'doc-1',
      source_document_title: 'Blood test March',
      link: '/documents/doc-1',
    },
    C1: { kind: 'check', title: '1 medicine not confirmed.', date: null, trust: null, source_document_id: null, source_document_title: null, link: '/medications' },
  },
  dropped_count: 1,
}

const state = (overrides: Partial<SummaryState> = {}): SummaryState => ({
  enabled: true,
  can_create: true,
  summary: null,
  stale: false,
  ...overrides,
})

describe('AI Summaries page', () => {
  it('writes a summary only when asked, then shows it with its sources and labels', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /summaries/history': () => jsonResponse(200, state()),
      'POST /summaries/history': () => jsonResponse(201, state({ summary: SUMMARY })),
    })
    renderAt('/summaries')

    const create = await screen.findByRole('button', { name: 'Create summary' })
    expect(screen.getByText(/sent to the AI service only when you ask/)).toBeInTheDocument()
    const posted = () => fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith('/summaries/history') && init?.method === 'POST')
    expect(posted()).toHaveLength(0) // nothing is sent to the AI until asked
    await userEvent.click(create)

    expect(await screen.findByText('AI-generated')).toBeInTheDocument()
    expect(posted()).toHaveLength(1)
    expect(screen.getByText(/This is not medical advice/)).toBeInTheDocument()
    const results = screen.getByRole('heading', { name: 'Results' }).parentElement as HTMLElement
    const [fact, interpretation] = within(results).getAllByRole('listitem')
    expect(fact).toHaveTextContent('Your HbA1c of 6.1 % is above the range 4.0 - 5.6 printed on the report.1')
    expect(within(fact).getByRole('link', { name: 'Source 1' })).toHaveAttribute('href', '#source-F1')
    expect(within(interpretation).getByText('AI interpretation')).toBeInTheDocument()

    // General knowledge is set apart, with the doctor's-advice note.
    const general = screen.getByRole('complementary', { name: 'General information, not from your records' })
    expect(within(general).getByText('HbA1c')).toBeInTheDocument()
    expect(within(general).getByText(/ask your doctor what it means for you/)).toBeInTheDocument()

    // Rule-based checks are labelled as such and link to where they can be fixed.
    expect(screen.getByText('Found by fixed rules in the app, not by the AI.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /1 medicine read from documents/ })).toHaveAttribute('href', '/medications')

    // Sources list the record, its date, its document, and that it was not checked.
    const source = document.getElementById('source-F1') as HTMLElement
    expect(source).toHaveTextContent('Lab results: 2 tests · 14-Mar-2026 · From Blood test March (read from a document, not checked by you)')
    expect(within(source).getByRole('link', { name: 'Blood test March' })).toHaveAttribute('href', '/documents/doc-1')
    expect(screen.getByText(/1 AI statement was left out because it could not be matched to your records/)).toBeInTheDocument()
  })

  it('says when the records changed and offers a refresh', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /summaries/history': () => jsonResponse(200, state({ summary: SUMMARY, stale: true })) })
    renderAt('/summaries')

    const notice = await screen.findByText(/Your records changed after this summary was written/)
    expect(within(notice).getByRole('button', { name: 'Refresh summary' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Write again' })).not.toBeInTheDocument()
  })

  it('explains when summaries are off or there is nothing to summarise', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /summaries/history': () => jsonResponse(200, state({ enabled: false })) })
    const { unmount } = renderAt('/summaries')
    expect(await screen.findByText(/AI summaries are turned off on this server/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create summary' })).not.toBeInTheDocument()
    unmount()

    stubFetch({ ...LOGGED_IN, 'GET /summaries/history': () => jsonResponse(200, state({ can_create: false })) })
    renderAt('/summaries')
    expect(await screen.findByText(/There are no records to summarise yet/)).toBeInTheDocument()
  })

  it('shows why a summary could not be written', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /summaries/history': () => jsonResponse(200, state()),
      'POST /summaries/history': () =>
        errorResponse(503, 'SERVICE_UNAVAILABLE', 'The AI service is busy or unreachable. Please try again in a minute.'),
    })
    renderAt('/summaries')

    await userEvent.click(await screen.findByRole('button', { name: 'Create summary' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The AI service is busy or unreachable.')
    expect(screen.getByRole('button', { name: 'Create summary' })).toBeInTheDocument()
  })
})
