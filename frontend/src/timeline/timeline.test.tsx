import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { jsonResponse, LOGGED_IN, renderAt, stubFetch } from '../test/helpers'
import type { TimelineEntry } from './timelineApi'

function entry(overrides: Partial<TimelineEntry> = {}): TimelineEntry {
  return {
    id: 'lab_results:doc-1:2026-10-07',
    date: '2026-10-07',
    date_precision: 'day',
    category: 'lab_results',
    title: 'Lab results: 12 tests',
    lines: ['Hemoglobin 10.2 g/dL (low; range 13.0 – 17.0)', '11 within range'],
    trust: 'from_document',
    tag: '1 outside range',
    source_document_id: 'doc-1',
    source_document_title: 'CBC October',
    link: '/documents/doc-1',
    ...overrides,
  }
}

const page = (items: TimelineEntry[], next_cursor: string | null = null) => jsonResponse(200, { items, next_cursor })

const dayHeadings = () =>
  screen.getAllByRole('region').filter((r) => r.classList.contains('timeline-day')).map((r) => within(r).getByRole('heading').textContent)

describe('Health timeline', () => {
  it('shows records by date with their source and how far they can be trusted', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /timeline': () =>
        page([
          entry(),
          entry({
            id: 'p',
            category: 'prescriptions',
            title: 'Prescription (Dr. Sample Physician)',
            lines: ['Atorvastatin 10 mg — once daily at night (taking, confirmed by you)'],
            tag: null,
            source_document_id: 'doc-2',
            source_document_title: 'Prescription Oct',
            link: '/documents/doc-2',
          }),
          entry({ id: 'f', date: '2026-09-01', category: 'follow_ups', title: 'CBC (due)', lines: [], trust: 'added_by_you', tag: 'Overdue', link: '/follow-ups', source_document_id: null, source_document_title: null }),
          entry({ id: 'y', date: '2024-01-01', date_precision: 'year', category: 'imaging', title: 'Old X-ray', lines: [], tag: null }),
          entry({ id: 'n', date: null, date_precision: null, category: 'medications', title: 'Added Calcium', lines: [], trust: 'added_by_you', tag: 'Taking', link: '/medications', source_document_id: null, source_document_title: null }),
        ]),
    })
    renderAt('/timeline')

    expect(await screen.findByRole('link', { name: 'Lab results: 12 tests' })).toHaveAttribute('href', '/documents/doc-1')
    expect(dayHeadings()).toEqual(['07-Oct-2026', '01-Sep-2026', '2024', 'No date'])

    const october = screen.getByRole('region', { name: '07-Oct-2026' })
    const [lab, prescription] = within(october).getAllByRole('listitem').filter((li) => li.classList.contains('timeline-entry'))
    expect(within(lab).getByText('1 outside range')).toHaveClass('timeline-tag-alert')
    expect(within(lab).getByText('Hemoglobin 10.2 g/dL (low; range 13.0 – 17.0)')).toBeInTheDocument()
    expect(within(lab).getByText('From document (not checked by you)')).toBeInTheDocument()
    expect(within(lab).getByRole('link', { name: 'CBC October' })).toHaveAttribute('href', '/documents/doc-1')
    expect(within(prescription).getByText(/confirmed by you\)$/)).toBeInTheDocument()

    const september = screen.getByRole('region', { name: '01-Sep-2026' })
    expect(within(september).getByText('Overdue')).toHaveClass('timeline-tag-alert')
    expect(within(september).getByText('Added by you')).toBeInTheDocument()
    expect(within(september).getByRole('link', { name: 'CBC (due)' })).toHaveAttribute('href', '/follow-ups')
  })

  it('filters by category and date, keeping the filters in the address', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /timeline': () => page([entry()]),
      'GET /timeline?category=lab_results': () => page([entry()]),
      'GET /timeline?category=lab_results&category=medications': () => page([]),
    })
    renderAt('/timeline')

    await screen.findByRole('link', { name: 'Lab results: 12 tests' })
    await userEvent.click(screen.getByRole('checkbox', { name: 'Medications' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Lab results' }))
    expect(await screen.findByText('Nothing matches these filters.')).toBeInTheDocument()
    // Categories are sent in the usual order, whatever order they were ticked in.
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/timeline?category=lab_results&category=medications'))).toBe(true)

    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(await screen.findByRole('link', { name: 'Lab results: 12 tests' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Medications' })).not.toBeChecked()
  })

  it('reads date filters from the address and explains that undated records are hidden', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /timeline?date_from=2026-10-01&date_to=2026-10-31': () => page([entry()]) })
    renderAt('/timeline?from=2026-10-01&to=2026-10-31')

    expect(await screen.findByRole('link', { name: 'Lab results: 12 tests' })).toBeInTheDocument()
    expect(screen.getByLabelText('From')).toHaveValue('2026-10-01')
    expect(screen.getByText(/Records without a date are not shown/)).toBeInTheDocument()
  })

  it('does not load when the end date is before the start date', async () => {
    const fetchMock = stubFetch({ ...LOGGED_IN })
    renderAt('/timeline?from=2026-10-02&to=2026-10-01')

    expect(await screen.findByText('The end date cannot be before the start date.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/timeline'))).toBe(false)
  })

  it('loads more and keeps one heading per date', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /timeline': () => page([entry()], '50'),
      'GET /timeline?cursor=50': () => page([entry({ id: 'second', title: 'Consultation', category: 'consultations', lines: [], tag: null })]),
    })
    renderAt('/timeline')

    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }))

    expect(await screen.findByRole('link', { name: 'Consultation' })).toBeInTheDocument()
    expect(dayHeadings()).toEqual(['07-Oct-2026'])
  })

  it('explains an empty timeline', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /timeline': () => page([]) })
    renderAt('/timeline')

    expect(await screen.findByText('Your timeline is empty.')).toBeInTheDocument()
  })
})
