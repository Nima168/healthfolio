import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { jsonResponse, LOGGED_IN, renderAt, stubFetch } from '../test/helpers'
import type { SearchResult } from './searchApi'

const RESULT: SearchResult = {
  record_type: 'report_text',
  id: 'text:doc-4',
  title: 'MRI Spine',
  date: '2026-09-18',
  matched_field: 'Impression',
  snippet: 'Early degenerative disc disease, L3-L4 to L5-S1',
  source_document_id: 'doc-4',
  source_document_title: 'MRI September',
  link: '/documents/doc-4',
}

const timeline = () => jsonResponse(200, { items: [], next_cursor: null })

describe('Record search', () => {
  it('searches with a POST body, keeps the text out of the address, and highlights the match', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /timeline': timeline,
      'POST /search': () => jsonResponse(200, { items: [RESULT], total: 1, next_cursor: null }),
    })
    renderAt('/timeline')

    await userEvent.type(await screen.findByLabelText(/^Search for/), 'degenerative disc')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('1')).toBeInTheDocument()
    const result = screen.getByRole('link', { name: 'MRI Spine' })
    expect(result).toHaveAttribute('href', '/documents/doc-4')
    const item = result.closest('li') as HTMLElement
    expect(within(item).getByText('Report text')).toBeInTheDocument()
    expect(within(item).getByText('Impression:')).toBeInTheDocument()
    expect(within(item).getByText('degenerative').tagName).toBe('MARK')
    expect(within(item).getByRole('link', { name: 'MRI September' })).toBeInTheDocument()

    const call = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith('/search') && init?.method === 'POST')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ query: 'degenerative disc' })
    expect(fetchMock.mock.calls.every(([url]) => !String(url).includes('degenerative'))).toBe(true)
    // The timeline steps aside while results are shown, and comes back on Clear search.
    expect(screen.queryByRole('search', { name: 'Filter the timeline' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clear search' }))
    expect(screen.getByRole('search', { name: 'Filter the timeline' })).toBeInTheDocument()
  })

  it('sends the extra filters and explains an empty result', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /timeline': timeline,
      'POST /search': () => jsonResponse(200, { items: [], total: 0, next_cursor: null }),
    })
    renderAt('/timeline')

    await userEvent.click(await screen.findByText('More filters'))
    await userEvent.selectOptions(screen.getByLabelText('Report type'), 'discharge_summary')
    await userEvent.type(screen.getByLabelText(/^Condition/), 'kidney')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('Nothing matched. Try fewer or shorter words.')).toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/search'))
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ document_type: 'discharge_summary', condition: 'kidney' })
  })

  it('asks for something to search for', async () => {
    const fetchMock = stubFetch({ ...LOGGED_IN, 'GET /timeline': timeline })
    renderAt('/timeline')

    await userEvent.click(await screen.findByRole('button', { name: 'Search' }))

    expect(screen.getByText('Enter something to search for, or choose a filter.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/search'))).toBe(false)
  })
})
