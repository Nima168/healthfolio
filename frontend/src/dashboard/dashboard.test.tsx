import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { jsonResponse, LOGGED_IN, renderAt, stubFetch } from '../test/helpers'
import type { Dashboard } from './dashboardApi'

function overview(overrides: Partial<Dashboard> = {}): Dashboard {
  return {
    documents_total: 0,
    documents_reading: 0,
    recent_documents: [],
    overdue_follow_ups: [],
    upcoming_follow_ups: [],
    alerts_open: 0,
    alerts_acknowledged: 0,
    alerts_urgent: 0,
    top_alerts: [],
    profile_suggestions: 0,
    unconfirmed_medicines: 0,
    follow_ups_to_add: [],
    failed_documents: [],
    profile_filled: 0,
    profile_total: 5,
    profile_missing: ['date_of_birth', 'sex', 'blood_group', 'height', 'weight'],
    allergies: [],
    conditions: 0,
    active_medications: 0,
    bmi: null,
    bmi_category: null,
    latest_blood_pressure: null,
    latest_heart_rate: null,
    recent_activity: [],
    ...overrides,
  }
}

const card = (name: string) => screen.getByRole('region', { name })

describe('Dashboard', () => {
  it('explains how to start and never treats missing data as good health', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /dashboard': () => jsonResponse(200, overview()) })
    renderAt('/')

    expect(await screen.findByText('Get started by uploading a medical report.')).toBeInTheDocument()
    expect(within(card('Alerts')).getByText(/This is not a health check/)).toBeInTheDocument()
    expect(within(card('Health profile')).getByText(/missing date of birth, sex, blood group, height, weight/)).toBeInTheDocument()
    expect(within(card('Health profile')).getByText('none recorded')).toBeInTheDocument()
    expect(within(card('Health profile')).getByText('needs height and weight')).toBeInTheDocument()
  })

  it('shows alerts, items to review, follow-ups, documents, profile, and recent activity with links', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /dashboard': () =>
        jsonResponse(
          200,
          overview({
            documents_total: 3,
            documents_reading: 1,
            recent_documents: [
              { id: 'doc-1', title: 'CBC October', category: 'lab_report', uploaded_at: '', reading_status: 'completed', read_as: 'lab_report' },
              { id: 'doc-2', title: 'Old scan', category: 'imaging_report', uploaded_at: '', reading_status: 'failed', read_as: null },
            ],
            overdue_follow_ups: [{ id: 'f-1', title: 'Kidney function test', due_date: '2026-10-01', source_document_id: 'doc-3' }],
            upcoming_follow_ups: [{ id: 'f-2', title: 'CBC', due_date: '2026-10-20', source_document_id: 'doc-3' }],
            alerts_open: 2,
            alerts_acknowledged: 1,
            alerts_urgent: 1,
            top_alerts: [
              { id: 'a-1', title: 'Potassium 2.4 mmol/L', severity: 'urgent', source_document_title: 'CBC October' },
              { id: 'a-2', title: "HbA1c 6.1 % is above the report's range (4.0 - 5.6)", severity: 'warning', source_document_title: 'CBC October' },
            ],
            profile_suggestions: 3,
            unconfirmed_medicines: 4,
            follow_ups_to_add: [{ id: 'doc-3', title: 'Prescription Oct', count: 2 }],
            failed_documents: [{ id: 'doc-2', title: 'Old scan', count: 1 }],
            profile_filled: 3,
            profile_missing: ['date_of_birth', 'blood_group'],
            allergies: ['Penicillin'],
            bmi: 25,
            bmi_category: 'overweight',
            latest_blood_pressure: { value: '120/80', unit: 'mmHg', measured_on: '2026-10-10', measured_time: '08:30' },
            recent_activity: [
              {
                id: 'e-1',
                date: '2026-10-07',
                date_precision: 'day',
                category: 'lab_results',
                title: 'Lab results: 12 tests',
                lines: [],
                trust: 'from_document',
                tag: null,
                source_document_id: 'doc-1',
                source_document_title: 'CBC October',
                link: '/documents/doc-1',
              },
            ],
          }),
        ),
    })
    renderAt('/')

    expect(await screen.findByRole('alert')).toHaveTextContent('1 urgent alert: open Alerts now')
    expect(screen.queryByText('Get started by uploading a medical report.')).not.toBeInTheDocument()

    const alerts = card('Alerts')
    expect(alerts).toHaveTextContent('2 open · 1 acknowledged')
    expect(within(alerts).getByText('Urgent')).toBeInTheDocument()
    expect(within(alerts).getByRole('link', { name: 'View alerts →' })).toHaveAttribute('href', '/alerts')

    const review = card('To review')
    expect(within(review).getByRole('link', { name: '3 diagnosis suggestions from your documents' })).toHaveAttribute('href', '/profile#suggestions-title')
    expect(within(review).getByRole('link', { name: /4 medicines not yet confirmed/ })).toHaveAttribute('href', '/medications')
    expect(within(review).getByRole('link', { name: '2 follow-ups to add from “Prescription Oct”' })).toHaveAttribute('href', '/documents/doc-3')
    expect(within(review).getByRole('link', { name: '“Old scan” could not be read' })).toBeInTheDocument()

    const followUps = card('Checkups and follow-ups')
    expect(within(followUps).getByText('Overdue')).toBeInTheDocument()
    expect(followUps).toHaveTextContent('01-Oct-2026 · Kidney function test')
    expect(followUps).toHaveTextContent('20-Oct-2026 · CBC')

    const documents = card('Recent documents')
    expect(documents).toHaveTextContent('1 document is being read.')
    expect(within(documents).getByText('Could not be read')).toBeInTheDocument()

    const profile = card('Health profile')
    expect(profile).toHaveTextContent('3 of 5 filled')
    expect(within(profile).getByText('Penicillin')).toBeInTheDocument()
    expect(profile).toHaveTextContent('25.0 · Overweight')
    expect(profile).toHaveTextContent('120/80 mmHg 10-Oct-2026 08:30')

    expect(within(card('Recent activity')).getByRole('link', { name: 'Lab results: 12 tests' })).toHaveAttribute('href', '/documents/doc-1')
  })
})
