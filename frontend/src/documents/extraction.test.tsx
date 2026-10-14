import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse, LOGGED_IN, renderAt, stubFetch, stubObjectUrls } from '../test/helpers'
import type { MedicalDocument } from './documentsApi'
import type {
  ConsultationSummary,
  DischargeSummary,
  DocumentExtraction,
  ImagingSummary,
  Observation,
  PrescriptionSummary,
  TestReportSummary,
} from './extractionApi'

const DOCUMENT: MedicalDocument = {
  id: 'doc-1',
  title: 'Blood test March',
  original_filename: 'blood-test.pdf',
  media_type: 'application/pdf',
  size_bytes: 1000,
  category: 'lab_report',
  document_date: null,
  document_date_precision: null,
  provider_name: null,
  copy_type: 'digital',
  processing_status: 'completed_with_warnings',
  created_at: '2026-10-11T09:00:00Z',
  updated_at: '2026-10-11T09:00:00Z',
}

function observation(overrides: Partial<Observation> = {}): Observation {
  return {
    id: 'obs-1',
    name: 'Haemoglobin',
    value_text: '13.8',
    value_numeric: '13.8',
    unit: 'g/dL',
    reference_range_text: '12.0 - 15.5',
    reference_low: '12',
    reference_high: '15.5',
    observed_at: '2026-03-14',
    observed_at_precision: 'day',
    page: 1,
    source_snippet: 'Haemoglobin 13.8 g/dL',
    confidence: 'high',
    needs_review: false,
    validation_findings: ['date_from_report'],
    notes: null,
    ...overrides,
  }
}

function extraction(overrides: Partial<DocumentExtraction> = {}): DocumentExtraction {
  return {
    extraction_enabled: true,
    media_type: 'application/pdf',
    copy_type: 'digital',
    job: { status: 'completed_with_warnings', attempts: 1, error_category: null, updated_at: '2026-10-11T09:01:00Z' },
    document_kind: 'lab_report',
    prescription: null,
    discharge: null,
    consultation: null,
    imaging: null,
    test_report: null,
    items: [
      observation(),
      observation({
        id: 'obs-2',
        name: 'HbA1c',
        value_text: '6.1',
        unit: null,
        confidence: 'medium',
        needs_review: true,
        validation_findings: ['missing_unit'],
      }),
      observation({
        id: 'obs-3',
        name: 'Vitamin B12',
        value_text: '<150',
        value_numeric: null,
        unit: 'pg/mL',
        reference_range_text: '200 - 900',
      }),
    ],
    summary: {
      report_date: '14/03/2026',
      above: [{ name: 'LDL', value_text: '180', unit: 'mg/dL', reference_range_text: '< 100' }],
      below: [],
      normal: [{ name: 'Haemoglobin', value_text: '13.8', unit: 'g/dL', reference_range_text: '12.0 - 15.5' }],
      invalid: [
        { name: 'HbA1c', value_text: '6.1', unit: null, reference_range_text: '4.0 - 5.6', reason: 'The unit is missing or unclear.' },
        {
          name: 'Vitamin B12',
          value_text: '<150',
          unit: 'pg/mL',
          reference_range_text: '200 - 900',
          reason: 'The value "<150" is not a single number, so it was not compared.',
        },
      ],
    },
    ...overrides,
  }
}

function setup(state: DocumentExtraction | (() => DocumentExtraction), extra: Record<string, (init?: RequestInit) => Response> = {}) {
  stubObjectUrls()
  const next = typeof state === 'function' ? state : () => state
  return stubFetch({
    ...LOGGED_IN,
    'GET /documents/doc-1': () => jsonResponse(200, DOCUMENT),
    'GET /documents/doc-1/file': () => new Response(new Blob(['%PDF'])),
    'GET /documents/doc-1/observations': () => jsonResponse(200, next()),
    'GET /documents/doc-1/summary': () => jsonResponse(200, { enabled: true, can_create: false, summary: null, stale: false }),
    ...extra,
  })
}

afterEach(() => {
  vi.useRealTimers()
})

describe('Plain-language summary of one document', () => {
  it('offers a summary once the document is read, and writes it only when asked', async () => {
    const summary = {
      id: 'sum-d',
      scope: 'document',
      created_at: '2026-10-13T09:00:00Z',
      model_version: 'qwen/qwen3.8-27b',
      sections: [{ key: 'overview', title: 'Overview', sentences: [{ text: 'This report has 4 tests.', kind: 'record', fact_ids: ['F1'] }] }],
      explanations: [],
      insights: [],
      sources: { F1: { kind: 'lab_results', title: 'Lab results: 4 tests', date: '2026-03-14', trust: 'from_document', source_document_id: 'doc-1', source_document_title: 'Blood test March', link: '/documents/doc-1' } },
      dropped_count: 0,
    }
    const fetchMock = setup(extraction(), {
      'GET /documents/doc-1/summary': () => jsonResponse(200, { enabled: true, can_create: true, summary: null, stale: false }),
      'POST /documents/doc-1/summary': () => jsonResponse(201, { enabled: true, can_create: true, summary, stale: false }),
    })
    renderAt('/documents/doc-1')

    const panel = await screen.findByRole('region', { name: 'Plain-language summary' })
    await userEvent.click(await within(panel).findByRole('button', { name: 'Create summary' }))

    expect(await within(panel).findByText('AI-generated')).toBeInTheDocument()
    expect(within(panel).getByText('This report has 4 tests.')).toBeInTheDocument()
    const posts = fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith('/documents/doc-1/summary') && init?.method === 'POST')
    expect(posts).toHaveLength(1)
  })
})

describe('Extracted lab results', () => {
  it('shows the summary in the agreed plain-text format', async () => {
    setup(extraction())
    renderAt('/documents/doc-1')

    const section = await screen.findByRole('region', { name: 'Extracted lab results' })
    await within(section).findByText('Report Date: 14/03/2026')
    const lines = within(section)
      .getAllByText(/./, { selector: 'p:not(.read-again), li' })
      .map((element) => (element.tagName === 'LI' ? `- ${element.textContent}` : element.textContent))

    expect(lines).toEqual([
      'Report Date: 14/03/2026',
      'Values Above Range:',
      '- LDL: 180 mg/dL (Reference: < 100)',
      'Values Below Range:',
      'None',
      'Normal Values:',
      '- Haemoglobin: 13.8 g/dL (Reference: 12.0 - 15.5)',
      'Invalid Records:',
      '- HbA1c: 6.1 (Reference: 4.0 - 5.6)',
      '- Vitamin B12: <150 pg/mL (Reference: 200 - 900)',
    ])
    // No closing line and no Needs Review section in the lab format.
    expect(within(section).queryByText(/qualified healthcare professional/)).not.toBeInTheDocument()
    expect(within(section).queryByText(/Needs Review/)).not.toBeInTheDocument()

    // Out-of-range values are highlighted; there is no review step.
    expect(within(section).getByText(/LDL: 180/).closest('ul')).toHaveClass('summary-critical')
    expect(within(section).getByText(/Haemoglobin: 13.8/).closest('ul')).not.toHaveClass('summary-critical')
    for (const name of ['Confirm', 'Correct', 'Reject']) {
      expect(within(section).queryByRole('button', { name })).not.toBeInTheDocument()
    }
  })

  it('writes "Not mentioned" when the report has no date', async () => {
    const base = extraction()
    setup({ ...base, summary: { ...base.summary!, report_date: null } })
    renderAt('/documents/doc-1')

    expect(await screen.findByText('Report Date: Not mentioned')).toBeInTheDocument()
  })

  it('marks parts that could not be read as "Not identified", never as a value', async () => {
    const base = extraction()
    const unreadable = {
      name: 'MCV',
      value_text: 'Not identified',
      unit: 'fL',
      reference_range_text: 'Not identified',
      reason: 'Part of this result could not be read (Not identified). Check it against the original.',
    }
    setup({ ...base, summary: { ...base.summary!, invalid: [unreadable] } })
    renderAt('/documents/doc-1')

    const line = (await screen.findByText(/^MCV:/)).closest('li')!
    expect(within(line).getAllByText('Not identified')).toHaveLength(2)
    expect(within(line).getAllByText('Not identified')[0]).toHaveClass('not-identified')
    expect(line).toHaveTextContent('– check the original')
  })

  it('leaves out Invalid Records when there are none', async () => {
    const base = extraction()
    setup({ ...base, summary: { ...base.summary!, invalid: [] } })
    renderAt('/documents/doc-1')

    expect(await screen.findByText('Normal Values:')).toBeInTheDocument()
    expect(screen.queryByText(/Invalid Records/)).not.toBeInTheDocument()
  })

  it('keeps checking while the document is being read', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let calls = 0
    setup(() => {
      calls += 1
      return calls === 1
        ? extraction({ job: { status: 'running', attempts: 1, error_category: null, updated_at: '' }, items: [] })
        : extraction()
    })
    renderAt('/documents/doc-1')

    expect(await screen.findByText(/Reading your document…/)).toBeInTheDocument()
    await vi.advanceTimersByTimeAsync(3000)
    expect(await screen.findByText('Report Date: 14/03/2026')).toBeInTheDocument()
  })

  it('explains when extraction is turned off', async () => {
    setup(extraction({ extraction_enabled: false, job: { status: 'pending', attempts: 0, error_category: null, updated_at: '' }, items: [] }))
    renderAt('/documents/doc-1')

    expect(await screen.findByText(/Automatic extraction is currently turned off/)).toBeInTheDocument()
  })

  it('explains a failure in plain language and can try again', async () => {
    const pending = extraction({ job: { status: 'pending', attempts: 0, error_category: null, updated_at: '' }, items: [] })
    let state = extraction({ job: { status: 'failed', attempts: 1, error_category: 'image_too_large', updated_at: '' }, items: [] })
    const fetchMock = setup(() => state, {
      'POST /documents/doc-1/extract': () => {
        state = pending // the server now has a new pending job
        return jsonResponse(202, pending)
      },
    })
    renderAt('/documents/doc-1')

    expect(await screen.findByText(/This image is too large to process/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Refresh analysis' }))

    expect(await screen.findByText(/Queued for reading…/)).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith('/extract') && init?.method === 'POST')).toBe(true)
  })

  it('offers extraction for documents uploaded before it existed', async () => {
    setup(extraction({ job: null, items: [] }))
    renderAt('/documents/doc-1')

    expect(await screen.findByRole('button', { name: 'Extract results' })).toBeInTheDocument()
  })

  it('says when no lab results were found', async () => {
    setup(extraction({ job: { status: 'completed', attempts: 1, error_category: null, updated_at: '' }, items: [] }))
    renderAt('/documents/doc-1')

    expect(await screen.findByText('No lab results were found in this document.')).toBeInTheDocument()
  })
})

const PRESCRIPTION: PrescriptionSummary = {
  prescribed_on: '2026-10-07',
  date_text: '07-Oct-2026',
  prescriber_name: 'Dr. Sample Physician',
  medications: [
    { name: 'Atorvastatin', strength: '10 mg', instructions: 'once daily at night', duration_text: '90 days', unclear: false, reason: null },
    { name: 'Metformin', strength: '500 mg', instructions: 'once daily after dinner', duration_text: '90 days', unclear: false, reason: null },
    {
      name: 'Ferrous ascorbate + folic acid',
      strength: null,
      instructions: 'once daily after lunch',
      duration_text: '60 days',
      unclear: false, reason: null,
    },
    { name: 'Vitamin D3', strength: '60,000 IU', instructions: 'once weekly', duration_text: '8 weeks', unclear: false, reason: null },
  ],
  follow_ups: [
    { due_date: '2026-11-04', description: 'Kidney function test + doctor visit', unclear: false, reason: null, when_text: 'after 4 weeks', calculated: true },
    { due_date: '2026-12-07', description: 'CBC', unclear: false, reason: null, when_text: 'on 07-Dec-2026', calculated: false },
    { due_date: '2027-01-05', description: 'HbA1c + lipid profile', unclear: false, reason: null, when_text: 'after 3 months', calculated: true },
  ],
  reminders: 'available',
}

function prescriptionState(overrides: Partial<PrescriptionSummary> = {}): DocumentExtraction {
  return extraction({
    job: { status: 'completed', attempts: 1, error_category: null, updated_at: '2026-10-11T09:01:00Z' },
    document_kind: 'prescription',
    items: [],
    summary: null,
    prescription: { ...PRESCRIPTION, ...overrides },
  })
}

describe('Prescription summary', () => {
  it('shows the prescription in the agreed plain-text format', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-11T09:00:00Z'))
    setup(prescriptionState())
    renderAt('/documents/doc-1')

    const section = await screen.findByRole('region', { name: 'Prescription summary' })
    await within(section).findByText(/PRESCRIPTION SUMMARY/)
    const lines = within(section)
      .getAllByText(/./, { selector: 'p:not(.reminder-prompt):not(.read-again), li' })
      .map((element) => (element.tagName === 'LI' ? `- ${element.textContent}` : element.textContent))

    expect(lines).toEqual([
      'PRESCRIPTION SUMMARY — 07-Oct-2026 (Dr. Sample Physician)',
      'Medications',
      '- Atorvastatin 10 mg: once daily at night, 90 days',
      '- Metformin 500 mg: once daily after dinner, 90 days',
      '- Ferrous ascorbate + folic acid: strength not mentioned, once daily after lunch, 60 days',
      '- Vitamin D3 60,000 IU: once weekly, 8 weeks',
      'Upcoming Follow-Ups',
      // The timing exactly as written; a date the app worked out is labelled as calculated.
      '- after 4 weeks (due 04-Nov-2026, calculated): Kidney function test + doctor visit',
      '- on 07-Dec-2026: CBC',
      '- after 3 months (due 05-Jan-2027, calculated): HbA1c + lipid profile',
    ])
    // Important points stand out: medicine with strength, and follow-up dates.
    expect(within(section).getByText('Atorvastatin 10 mg').tagName).toBe('STRONG')
    expect(within(section).getByText('after 4 weeks').tagName).toBe('STRONG')
    expect(within(section).getByRole('button', { name: 'Add to Checkups and Follow-ups' })).toBeInTheDocument()
    expect(within(section).queryByText(/Needs Review/)).not.toBeInTheDocument()
    expect(within(section).queryByText(/Add as reminders/)).not.toBeInTheDocument()
  })

  it('marks unclear items where they are, and past dates', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-12-01T09:00:00Z'))
    const reason = 'The name, strength, or instructions were not clearly legible.'
    setup(
      prescriptionState({
        prescribed_on: null,
        prescriber_name: null,
        date_text: null,
        medications: [{ ...PRESCRIPTION.medications[1], unclear: true, reason }],
        follow_ups: [
          ...PRESCRIPTION.follow_ups.slice(0, 2),
          { due_date: null, description: 'Eye checkup', unclear: true, reason: 'No follow-up date or timing is written.', when_text: null, calculated: false },
        ],
        reminders: 'none',
      }),
    )
    renderAt('/documents/doc-1')

    const section = await screen.findByRole('region', { name: 'Prescription summary' })
    expect(await within(section).findByText('PRESCRIPTION SUMMARY — Date not mentioned')).toBeInTheDocument()
    const metformin = within(section).getByText('Metformin 500 mg').closest('li') as HTMLElement
    expect(metformin).toHaveTextContent('Metformin 500 mg: once daily after dinner, 90 days (unclear – check original)')
    expect(within(metformin).getByText(/unclear/)).toHaveAttribute('title', reason)
    expect(within(section).getByText('Date not mentioned').closest('li')).toHaveTextContent(
      'Date not mentioned: Eye checkup (unclear – check original)',
    )
    expect(within(section).getByText('after 4 weeks').closest('li')).toHaveTextContent('(date has passed)')
    expect(within(section).getByText('on 07-Dec-2026').closest('li')).not.toHaveTextContent('(date has passed)')
    expect(within(section).queryByRole('button', { name: 'Add to Checkups and Follow-ups' })).not.toBeInTheDocument()
  })

  it('adds the follow-ups to Checkups and Follow-ups', async () => {
    const fetchMock = setup(prescriptionState(), {
      'POST /documents/doc-1/follow-ups': () => jsonResponse(201, prescriptionState({ reminders: 'added' })),
    })
    renderAt('/documents/doc-1')

    await userEvent.click(await screen.findByRole('button', { name: 'Add to Checkups and Follow-ups' }))

    const section = screen.getByRole('region', { name: 'Prescription summary' })
    expect(await within(section).findByRole('link', { name: 'Checkups and Follow-ups' })).toHaveAttribute(
      'href',
      '/follow-ups',
    )
    expect(within(section).getByText(/Added to/)).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/documents/doc-1/follow-ups'))).toBe(true)
  })

  it('offers to try again when a prescription reading found nothing', async () => {
    const fetchMock = setup(prescriptionState({ medications: [], follow_ups: [], reminders: 'none' }), {
      'POST /documents/doc-1/extract': () =>
        jsonResponse(202, extraction({ job: { status: 'pending', attempts: 0, error_category: null, updated_at: '' }, items: [] })),
    })
    renderAt('/documents/doc-1')

    expect(await screen.findByText('No medicines or follow-ups were found in this prescription.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Refresh analysis' }))

    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/documents/doc-1/extract'))).toBe(true)
  })

  it('says when a document is neither a lab report nor a prescription', async () => {
    setup(
      extraction({
        job: { status: 'completed', attempts: 1, error_category: null, updated_at: '' },
        document_kind: 'other',
        items: [],
        summary: null,
      }),
    )
    renderAt('/documents/doc-1')

    expect(
      await screen.findByText('This document does not look like a medical report the app can read yet, so nothing was extracted.'),
    ).toBeInTheDocument()
  })
})

const DISCHARGE: DischargeSummary = {
  facility_name: 'Sampleville General Hospital',
  admitted_on: '2026-08-10',
  admitted_text: '10-Aug-2026 21:40',
  discharged_on: '2026-08-13',
  discharged_text: '13-Aug-2026 11:00',
  stay_days: 4,
  diagnoses: ['Acute gastroenteritis with moderate dehydration', 'Hypokalemia and mild hyponatremia, corrected'],
  key_results: [
    {
      name: 'Serum Creatinine',
      first_value: '1.92',
      last_value: '1.31',
      unit: 'mg/dL',
      reference_range_text: '0.70 – 1.30',
      flag: 'high',
      still: true,
      last_tested: null,
      unclear: false,
    },
    {
      name: 'C-Reactive Protein',
      first_value: '18.4',
      last_value: '6.2',
      unit: 'mg/L',
      reference_range_text: '< 5.0',
      flag: 'high',
      still: true,
      last_tested: '2026-08-12',
      unclear: false,
    },
    {
      name: 'Stool culture',
      first_value: null,
      last_value: 'No enteric pathogens isolated',
      unit: null,
      reference_range_text: null,
      flag: null,
      still: false,
      last_tested: null,
      unclear: false,
    },
  ],
  medications: [
    { name: 'Pantoprazole tablet', strength: '40 mg', instructions: '1 tablet once daily, Before breakfast', duration_text: '5 days', unclear: false, reason: null },
  ],
  follow_ups: [{ due_date: '2026-08-20', description: 'Review with Dr. Sample Consultant', unclear: false, reason: null, when_text: 'after 1 week', calculated: true }],
  reminders: 'available',
  warning_signs: ['Return to the emergency department if vomiting persists or blood appears in stools.'],
}

describe('Discharge summary', () => {
  it('shows the discharge summary in the agreed plain-text format', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-08-14T09:00:00Z'))
    setup(
      extraction({
        job: { status: 'completed', attempts: 1, error_category: null, updated_at: '' },
        document_kind: 'discharge_summary',
        summary: null,
        discharge: DISCHARGE,
      }),
    )
    renderAt('/documents/doc-1')

    const section = await screen.findByRole('region', { name: 'Discharge summary' })
    await within(section).findByText(/DISCHARGE SUMMARY/)
    const lines = within(section)
      .getAllByText(/./, { selector: 'p:not(.reminder-prompt):not(.read-again), li' })
      .map((element) => (element.tagName === 'LI' ? `- ${element.textContent}` : element.textContent))

    expect(lines).toEqual([
      'DISCHARGE SUMMARY — Sampleville General Hospital',
      'Admitted 10-Aug-2026 21:40 → Discharged 13-Aug-2026 11:00 (4 days)', // exactly as printed
      'Diagnosis',
      '- Acute gastroenteritis with moderate dehydration',
      '- Hypokalemia and mild hyponatremia, corrected',
      'Key Results',
      '- Serum Creatinine: 1.92 → 1.31 mg/dL (ref 0.70 – 1.30) — still high',
      '- C-Reactive Protein: 18.4 → 6.2 mg/L (ref < 5.0) — still high, last tested 12-Aug',
      '- Stool culture: No enteric pathogens isolated (ref not mentioned)',
      'Discharge Medications',
      '- Pantoprazole tablet 40 mg: 1 tablet once daily, Before breakfast, 5 days',
      'Upcoming Follow-Ups',
      '- after 1 week (due 20-Aug-2026, calculated): Review with Dr. Sample Consultant',
      'Return to Emergency If',
      '- Return to the emergency department if vomiting persists or blood appears in stools.',
    ])
    expect(within(section).getByRole('button', { name: 'Add to Checkups and Follow-ups' })).toBeInTheDocument()
  })

  it('can read the document again', async () => {
    const fetchMock = setup(
      extraction({
        job: { status: 'completed', attempts: 1, error_category: null, updated_at: '' },
        document_kind: 'discharge_summary',
        summary: null,
        discharge: DISCHARGE,
      }),
      {
        'POST /documents/doc-1/extract': () =>
          jsonResponse(202, extraction({ job: { status: 'pending', attempts: 0, error_category: null, updated_at: '' }, items: [] })),
      },
    )
    renderAt('/documents/doc-1')

    await userEvent.click(await screen.findByRole('button', { name: 'Refresh analysis' }))

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/documents/doc-1/extract'))).toBe(true),
    )
  })

  it('says how the document was read', async () => {
    setup(
      extraction({
        copy_type: 'scanned',
        job: {
          status: 'completed',
          attempts: 1,
          error_category: null,
          updated_at: '',
          reading_method: 'ocr',
          ocr_confidence: 89,
        },
      }),
    )
    renderAt('/documents/doc-1')

    expect(
      await screen.findByText(
        'Read with OCR (text recognition) from the scanned copy (average confidence 89%). OCR can misread characters, so check the values against the original.',
      ),
    ).toBeInTheDocument()
  })

  it('notes when a PDF chosen as digital had no text inside', async () => {
    setup(
      extraction({
        job: { status: 'completed', attempts: 1, error_category: null, updated_at: '', reading_method: 'vision' },
      }),
    )
    renderAt('/documents/doc-1')

    expect(await screen.findByText(/This PDF had no text inside, so it was read as a scanned copy\./)).toBeInTheDocument()
  })

  it('can refresh the analysis as the other kind of copy', async () => {
    const fetchMock = setup(extraction(), {
      'POST /documents/doc-1/extract': () =>
        jsonResponse(202, extraction({ job: { status: 'pending', attempts: 0, error_category: null, updated_at: '' }, items: [] })),
    })
    renderAt('/documents/doc-1')

    expect(await screen.findByText(/refresh the analysis once for a better result/)).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Read as'), 'scanned')
    await userEvent.click(screen.getByRole('button', { name: 'Refresh analysis' }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/documents/doc-1/extract'))
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ copy_type: 'scanned' })
    })
  })

  it('offers Refresh analysis after a reading that found nothing', async () => {
    setup(extraction({ job: { status: 'completed', attempts: 1, error_category: null, updated_at: '' }, items: [], summary: null }))
    renderAt('/documents/doc-1')

    expect(await screen.findByText('No lab results were found in this document.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh analysis' })).toBeInTheDocument()
  })

  it('does not offer Read as for a photo', async () => {
    setup(extraction({ media_type: 'image/jpeg', copy_type: 'scanned' }))
    renderAt('/documents/doc-1')

    expect(await screen.findByRole('button', { name: 'Refresh analysis' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Read as')).not.toBeInTheDocument()
  })
})

function completed(overrides: Partial<DocumentExtraction>): DocumentExtraction {
  return extraction({
    job: { status: 'completed', attempts: 1, error_category: null, updated_at: '' },
    summary: null,
    items: [],
    ...overrides,
  })
}

function textLines(section: HTMLElement): (string | null)[] {
  return within(section)
    .getAllByText(/./, { selector: 'p:not(.reminder-prompt):not(.read-again), li' })
    .map((element) => (element.tagName === 'LI' ? `- ${element.textContent}` : element.textContent))
}

const CONSULTATION: ConsultationSummary = {
  visit_date: '2026-10-15',
  visit_text: '15-Oct-2026',
  clinician_name: 'Dr. Sample Nephrologist',
  symptoms: ['Mild tiredness for 1 month', 'No swelling, no change in urine'],
  observations: ['BP 138/88 mmHg (repeat 136/86); pulse 76/min; no edema'],
  assessment: ['Mildly reduced kidney function; CKD not yet confirmed'],
  plan: ['Avoid NSAIDs; paracetamol if needed'],
  follow_ups: [
    { due_date: '2026-11-10', description: 'Urine ACR', unclear: false, reason: null, when_text: null, calculated: false },
    { due_date: '2026-11-12', description: 'Nephrology review with reports', unclear: false, reason: null, when_text: null, calculated: false },
    { due_date: null, description: 'Repeat creatinine and eGFR', unclear: false, reason: null, when_text: 'Mid-January 2027', calculated: false },
  ],
  reminders: 'available',
}

const IMAGING: ImagingSummary = {
  is_written_report: true,
  exam_name: 'MRI Lumbosacral Spine (Plain)',
  report_id: 'SYN-MRI-26-04415',
  facility_name: 'Spectrum Imaging Centre',
  exam_date: '2026-09-18',
  exam_text: '18-Sep-2026',
  report_date: '2026-09-19',
  report_text: '19-Sep-2026',
  body_region: 'Lower back (L1 to S1)',
  findings: ['L4-L5: disc bulge 3.2 mm; no nerve compression'],
  impression: ['Early degenerative disc disease, L3-L4 to L5-S1'],
  uncertainty: ['Sacroiliac joints only partially seen'],
}

const ECG: TestReportSummary = {
  test_type: 'ECG',
  test_name: '12-Lead Resting ECG',
  report_id: 'SYN-ECG-2026-07731',
  facility_name: 'HeartWell Cardiac Clinic',
  report_form: 'typed',
  test_date: '2026-09-24',
  test_text: '24-Sep-2026 11:12',
  measurements: [
    { name: 'PR', value_text: '158', unit: 'ms', reference_range_text: '120–200', flag: null, unclear: false },
    { name: 'QT', value_text: '382', unit: 'ms', reference_range_text: null, flag: null, unclear: false },
    { name: 'QTc', value_text: '468', unit: 'ms', reference_range_text: '< 450, men', flag: 'high', unclear: false },
  ],
  interpretations: [
    { source: 'machine', confirmed: false, text: 'Normal sinus rhythm. Normal ECG.' },
    { source: 'physician', confirmed: true, text: 'Normal sinus rhythm, normal axis.' },
  ],
  visual_content: ['Lead II rhythm strip'],
}

describe('Consultation, imaging, and other test reports', () => {
  it('shows a consultation note in the agreed format', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-16T09:00:00Z'))
    setup(completed({ document_kind: 'consultation_note', consultation: CONSULTATION }))
    renderAt('/documents/doc-1')

    const section = await screen.findByRole('region', { name: 'Consultation summary' })
    await within(section).findByText(/CONSULTATION SUMMARY/)
    expect(textLines(section)).toEqual([
      'CONSULTATION SUMMARY — 15-Oct-2026 (Dr. Sample Nephrologist)',
      'Symptoms',
      '- Mild tiredness for 1 month',
      '- No swelling, no change in urine',
      'Observations',
      '- BP 138/88 mmHg (repeat 136/86); pulse 76/min; no edema',
      'Assessment',
      '- Mildly reduced kidney function; CKD not yet confirmed',
      'Plan',
      '- Avoid NSAIDs; paracetamol if needed',
      'Follow-Up',
      '- 10-Nov-2026: Urine ACR',
      '- 12-Nov-2026: Nephrology review with reports',
      '- Mid-January 2027: Repeat creatinine and eGFR (no exact date)',
    ])
    expect(within(section).getByRole('button', { name: 'Add to Checkups and Follow-ups' })).toBeInTheDocument()
  })

  it('shows a written imaging report in the agreed format', async () => {
    setup(completed({ document_kind: 'imaging_report', imaging: IMAGING }))
    renderAt('/documents/doc-1')

    const section = await screen.findByRole('region', { name: 'Imaging summary' })
    await within(section).findByText(/IMAGING SUMMARY/)
    expect(textLines(section)).toEqual([
      'IMAGING SUMMARY — MRI Lumbosacral Spine (Plain)',
      'Source: Written report SYN-MRI-26-04415 (Spectrum Imaging Centre)',
      'Examination Date: 18-Sep-2026 (reported 19-Sep-2026)',
      'Body Region: Lower back (L1 to S1)',
      'Findings',
      '- L4-L5: disc bulge 3.2 mm; no nerve compression',
      'Impression',
      '- Early degenerative disc disease, L3-L4 to L5-S1',
      'Uncertainty',
      '- Sacroiliac joints only partially seen',
    ])
  })

  it('does not read scan images without a written report', async () => {
    setup(completed({ document_kind: 'imaging_report', imaging: { ...IMAGING, is_written_report: false } }))
    renderAt('/documents/doc-1')

    expect(await screen.findByText(/Reading scan images is planned for a later update/)).toBeInTheDocument()
  })

  it('shows another test report (ECG) in the agreed format', async () => {
    setup(completed({ document_kind: 'test_report', test_report: ECG }))
    renderAt('/documents/doc-1')

    const section = await screen.findByRole('region', { name: 'Test report summary' })
    await within(section).findByText(/ECG SUMMARY/)
    expect(textLines(section)).toEqual([
      'ECG SUMMARY — 12-Lead Resting ECG',
      'Source: SYN-ECG-2026-07731 (HeartWell Cardiac Clinic), typed report',
      'Date: 24-Sep-2026 11:12',
      'Reported Measurements',
      '- PR 158 ms (120–200)',
      '- QT 382 ms (reference not mentioned)',
      '- QTc 468 ms (< 450, men) — high',
      'Interpretation',
      '- Machine: Normal sinus rhythm. Normal ECG.',
      '- Physician (confirmed): Normal sinus rhythm, normal axis.',
      'Visual Content',
      '- Lead II rhythm strip: not extracted (image only)',
    ])
  })
})
