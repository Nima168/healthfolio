import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { jsonResponse, LOGGED_IN, renderAt, stubFetch } from '../test/helpers'
import type { HealthIssue } from './diagnosesApi'

function issue(overrides: Partial<HealthIssue> = {}): HealthIssue {
  return {
    name: 'Acute kidney injury (pre-renal)',
    kinds: ['assessment', 'diagnosis'],
    first_seen: '2026-08-13',
    last_seen: '2026-10-15',
    profile: 'to_review',
    condition_status: null,
    normal: false,
    mentions: [
      { text: 'Acute kidney injury (pre-renal)', kind: 'assessment', document_id: 'doc-2', document_title: 'Nephrology visit', date: '2026-10-15' },
      { text: 'Acute kidney injury (pre-renal)', kind: 'diagnosis', document_id: 'doc-1', document_title: 'Discharge August', date: '2026-08-13' },
    ],
    ...overrides,
  }
}

const IMPRESSION = issue({
  name: 'Early degenerative disc disease',
  kinds: ['impression'],
  first_seen: '2026-09-18',
  last_seen: '2026-09-18',
  profile: 'not_in_profile',
  mentions: [{ text: 'Early degenerative disc disease', kind: 'impression', document_id: 'doc-3', document_title: 'MRI spine', date: '2026-09-18' }],
})

describe('Diagnoses and Conditions page', () => {
  it('lists each health issue with where and when it was written', async () => {
    const IN_PROFILE = issue({ name: 'Type 2 diabetes', kinds: ['diagnosis'], first_seen: null, last_seen: null, profile: 'in_profile', condition_status: 'active', mentions: [] })
    stubFetch({ ...LOGGED_IN, 'GET /diagnoses': () => jsonResponse(200, { items: [issue(), IMPRESSION, IN_PROFILE] }) })
    renderAt('/diagnoses')

    expect(await screen.findByRole('heading', { level: 1, name: 'Diagnoses and Conditions' })).toBeInTheDocument()
    const list = await screen.findByRole('list', { name: 'Diagnoses and conditions' })
    const rows = [...list.children] as HTMLElement[]
    expect(rows).toHaveLength(3)
    const kidney = rows[0]
    expect(kidney).toHaveTextContent('AssessmentDiagnosis 13-Aug-2026 → 15-Oct-2026 · 2 documents')
    expect(within(kidney).getByRole('link', { name: 'Review in Health Profile' })).toHaveAttribute('href', '/profile#suggestions-title')
    expect(within(kidney).getByRole('link', { name: 'Discharge August' })).toHaveAttribute('href', '/documents/doc-1')
    expect(kidney).toHaveTextContent('15-Oct-2026 · Assessment in Nephrology visit: “Acute kidney injury (pre-renal)”')
    expect(screen.getByText('In Health Profile · Active')).toBeInTheDocument()
    expect(screen.getByText(/The app does not diagnose/)).toBeInTheDocument()
  })

  it('does not list normal findings', async () => {
    const NORMAL = issue({
      name: 'Normal heart size.',
      kinds: ['impression'],
      profile: 'not_in_profile',
      normal: true,
      mentions: [{ text: 'Normal heart size.', kind: 'impression', document_id: 'doc-4', document_title: 'Chest X-ray', date: '2026-10-05' }],
    })
    stubFetch({ ...LOGGED_IN, 'GET /diagnoses': () => jsonResponse(200, { items: [issue(), NORMAL] }) })
    renderAt('/diagnoses')

    const list = await screen.findByRole('list', { name: 'Diagnoses and conditions' })
    expect(list.children).toHaveLength(1)
    expect(screen.queryByText(/Normal heart size/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Normal findings/)).not.toBeInTheDocument()
  })

  it('shows the empty state when the documents only have normal findings', async () => {
    const NORMAL = issue({ name: 'Lungs are clear.', kinds: ['impression'], normal: true, mentions: [] })
    stubFetch({ ...LOGGED_IN, 'GET /diagnoses': () => jsonResponse(200, { items: [NORMAL] }) })
    renderAt('/diagnoses')

    expect(await screen.findByText('No diagnoses or conditions found yet.')).toBeInTheDocument()
  })

  it('filters by kind', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /diagnoses': () => jsonResponse(200, { items: [issue(), IMPRESSION] }) })
    renderAt('/diagnoses')

    await userEvent.selectOptions(await screen.findByLabelText('Show'), 'impression')

    expect(screen.getByText('Early degenerative disc disease', { selector: '.follow-up-title' })).toBeInTheDocument()
    expect(screen.queryByText('Acute kidney injury (pre-renal)', { selector: '.follow-up-title' })).not.toBeInTheDocument()
  })

  it('adds an issue to the Health Profile without guessing its status', async () => {
    let added = false
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /diagnoses': () =>
        jsonResponse(200, { items: [added ? { ...IMPRESSION, profile: 'in_profile', condition_status: 'unknown' } : IMPRESSION] }),
      'POST /profile/conditions': () => {
        added = true
        return jsonResponse(201, { id: 'c-1', name: IMPRESSION.name, status: 'unknown' })
      },
    })
    renderAt('/diagnoses')

    await userEvent.click(await screen.findByRole('button', { name: 'Add to Health Profile' }))

    expect(await screen.findByText('In Health Profile · Status not set')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/profile/conditions'))
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ name: 'Early degenerative disc disease', status: 'unknown' })
  })

  it('explains where issues come from when there are none', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /diagnoses': () => jsonResponse(200, { items: [] }) })
    renderAt('/diagnoses')

    const empty = (await screen.findByText('No diagnoses or conditions found yet.')).closest('.card') as HTMLElement
    expect(within(empty).getByRole('link', { name: 'Medical Documents' })).toHaveAttribute('href', '/documents')
  })
})
