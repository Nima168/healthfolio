import { fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import {
  errorResponse,
  jsonResponse,
  LOGGED_IN,
  renderAt,
  stubFetch,
  stubObjectUrls,
  stubUploads,
} from '../test/helpers'
import type { MedicalDocument } from './documentsApi'

function makeDocument(overrides: Partial<MedicalDocument> = {}): MedicalDocument {
  return {
    id: 'doc-1',
    title: 'Blood test March',
    original_filename: 'blood-test.pdf',
    media_type: 'application/pdf',
    size_bytes: 182_344,
    category: 'lab_report',
    report_subtype: null,
    document_date: '2026-03-01',
    document_date_precision: 'month',
    provider_name: 'City Diagnostics',
    copy_type: 'digital',
    processing_status: 'pending',
    created_at: '2026-10-11T09:00:00Z',
    updated_at: '2026-10-11T09:00:00Z',
    ...overrides,
  }
}

const page = (items: MedicalDocument[], nextCursor: string | null = null) =>
  jsonResponse(200, { items, pagination: { limit: 20, next_cursor: nextCursor } })

const pdfFile = (name = 'new-report.pdf') => new File(['%PDF-1.4 synthetic'], name, { type: 'application/pdf' })

/** Upload details are all required. */
async function fillDetails(category = 'lab_report', copyType: RegExp = /Digital PDF/) {
  await userEvent.selectOptions(screen.getByLabelText('Report type (required)'), category)
  fireEvent.change(screen.getByLabelText('Document date (required)'), { target: { value: '2026-03-14' } })
  await userEvent.type(screen.getByLabelText('Hospital, lab, or clinic (required)'), 'City Diagnostics')
  await userEvent.click(screen.getByRole('radio', { name: copyType }))
}

describe('Documents page', () => {
  it('lists documents with their details, showing only as much of the date as is known', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([makeDocument({ report_subtype: 'Lipid profile' })]) })
    renderAt('/documents?group=none')

    const table = await screen.findByRole('table', { name: 'Your documents' })
    expect(within(table).getAllByRole('columnheader').map((th) => th.textContent)).toEqual([
      'Name',
      'Report type',
      'Report sub-type',
      'Document date',
      'Hospital, lab, or clinic',
      'File',
      'Uploaded',
    ])
    const row = within(table).getByRole('link', { name: 'Blood test March' }).closest('tr') as HTMLElement
    const cells = within(row).getAllByRole('cell').map((td) => td.textContent)
    expect(cells.slice(0, 4)).toEqual(['Laboratory reports', 'Lipid profile', 'March 2026', 'City Diagnostics'])
    expect(cells[4]).toBe('blood-test.pdfPDF · 178 KB')
    expect(within(row).queryByText('Queued for extraction')).not.toBeInTheDocument() // no processing status shown
  })

  it('shows your documents above the upload panel, with a link down to it', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([makeDocument()]) })
    renderAt('/documents?group=none')

    const listHeading = await screen.findByRole('heading', { name: 'Your documents' })
    const uploadHeading = screen.getByRole('heading', { name: 'Upload a document' })
    expect(listHeading.compareDocumentPosition(uploadHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByRole('link', { name: /Upload a document/ })).toHaveAttribute('href', '#upload')
  })

  it('asks for only one page of a discharge summary, due to AI limits', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    renderAt('/documents?group=none')

    await userEvent.upload(await screen.findByLabelText('Choose a file'), pdfFile())
    const type = screen.getByLabelText('Report type (required)')
    expect(screen.queryByText(/only one page of the discharge summary/)).not.toBeInTheDocument()

    await userEvent.selectOptions(type, 'discharge_summary')

    const note = screen.getByText(/Please upload only one page of the discharge summary/)
    expect(note).toHaveTextContent('due to AI reading limits')
    expect(type).toHaveAttribute('aria-describedby', note.id)
  })

  it('explains what is missing when Upload is clicked with nothing chosen', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    const requests = stubUploads(() => ({ status: 201, body: {} }))
    renderAt('/documents?group=none')

    await userEvent.click(await screen.findByRole('button', { name: 'Upload' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Choose a file to upload.')
    expect(screen.getByText('Enter a name for this document.')).toBeInTheDocument()
    expect(screen.getByLabelText('Name (required)')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Choose the report type.')).toBeInTheDocument()
    expect(screen.getByText('Enter the date on the document.')).toBeInTheDocument()
    expect(screen.getByText('Enter the hospital, lab, or clinic.')).toBeInTheDocument()
    expect(screen.getByLabelText('Hospital, lab, or clinic (required)')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Choose whether this is a digital PDF or a scanned copy.')).toBeInTheDocument()
    expect(requests).toHaveLength(0)
  })

  it('asks whether a PDF is digital or scanned, and treats a photo as scanned', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    renderAt('/documents?group=none')
    const digital = await screen.findByRole('radio', { name: /Digital PDF/ })
    const scanned = screen.getByRole('radio', { name: /Scanned copy or photo/ })

    await userEvent.upload(screen.getByLabelText('Choose a file'), pdfFile())
    expect([digital, scanned].map((radio) => (radio as HTMLInputElement).checked)).toEqual([false, false])

    const photo = new File(['photo'], 'report.jpg', { type: 'image/jpeg' })
    await userEvent.upload(screen.getByLabelText('Choose a different file'), photo)
    expect(scanned).toBeChecked()
    expect(digital).toBeDisabled()
    expect(screen.getByText('Photos are always read as scanned copies.')).toBeInTheDocument()
  })

  it('requires a name even when a file is chosen', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    const requests = stubUploads(() => ({ status: 201, body: {} }))
    renderAt('/documents?group=none')

    await userEvent.upload(await screen.findByLabelText('Choose a file'), pdfFile())
    await userEvent.type(screen.getByLabelText('Name (required)'), '   ')
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(screen.getByText('Enter a name for this document.')).toBeInTheDocument()
    expect(screen.queryByText('Choose a file to upload.')).not.toBeInTheDocument()
    expect(requests).toHaveLength(0)
  })

  it('shows a helpful empty state', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    renderAt('/documents?group=none')

    expect(await screen.findByText('No documents yet.')).toBeInTheDocument()
  })

  it('uploads a file with progress and adds it to the list', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    const requests = stubUploads(() => ({
      status: 201,
      body: makeDocument({ id: 'doc-new', title: 'Thyroid panel', original_filename: 'new-report.pdf' }),
    }))
    renderAt('/documents?group=none')

    await userEvent.upload(await screen.findByLabelText('Choose a file'), pdfFile())
    await userEvent.type(screen.getByLabelText('Name (required)'), '  Thyroid panel ')
    await fillDetails('prescription')
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Uploaded “Thyroid panel”.')
    expect(screen.getByRole('link', { name: 'Thyroid panel' })).toBeInTheDocument()
    expect(screen.getByLabelText('Name (required)')).toHaveValue('') // form reset for the next upload

    const [request] = requests
    expect(request.url).toBe('http://localhost:8000/api/v1/documents')
    expect(request.headers.Authorization).toBe('Bearer access-1')
    expect(request.body.get('title')).toBe('Thyroid panel')
    expect(request.body.get('category')).toBe('prescription')
    expect(request.body.get('document_date')).toBe('2026-03-14')
    expect(request.body.get('provider_name')).toBe('City Diagnostics')
    expect(request.body.get('copy_type')).toBe('digital')
  })

  it('offers the report types with clinical documents under one heading', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    renderAt('/documents?group=none')

    const type = await screen.findByLabelText('Report type (required)')
    expect(within(type).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Choose a type',
      'Laboratory reports',
      'Text-based imaging reports',
      'Prescription',
      'Discharge summary',
      'Consultation note',
      'Pathology reports',
      'Specialist reports',
    ])
    const groups = [...type.querySelectorAll('optgroup')].map((group) => [
      group.getAttribute('label'),
      within(group as HTMLElement).getAllByRole('option').map((o) => o.textContent),
    ])
    expect(groups).toEqual([
      ['Clinical Documents', ['Prescription', 'Discharge summary', 'Consultation note']],
      ['Other', ['Pathology reports', 'Specialist reports']],
    ])
  })

  it('sends an optional free-text sub-type', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    const requests = stubUploads(() => ({ status: 201, body: makeDocument({ id: 'doc-new' }) }))
    renderAt('/documents?group=none')

    await userEvent.upload(await screen.findByLabelText('Choose a file'), pdfFile())
    await userEvent.type(screen.getByLabelText('Name (required)'), 'Lipids')
    await fillDetails('lab_report')
    await userEvent.type(screen.getByLabelText('Report sub-type (optional)'), 'Lipid profile')
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }))

    await screen.findByRole('status')
    expect(requests[0].body.get('report_subtype')).toBe('Lipid profile')
  })

  it('uploads a specialist report with an optional sub-type', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    const requests = stubUploads(() => ({ status: 201, body: makeDocument({ id: 'doc-new', category: 'specialist_report' }) }))
    renderAt('/documents?group=none')

    await userEvent.upload(await screen.findByLabelText('Choose a file'), pdfFile())
    await userEvent.type(screen.getByLabelText('Name (required)'), 'ECG')
    await fillDetails('specialist_report')
    await userEvent.type(screen.getByLabelText('Report sub-type (optional)'), 'ECG')
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }))

    await screen.findByRole('status')
    expect(requests[0].body.get('category')).toBe('specialist_report')
    expect(requests[0].body.get('report_subtype')).toBe('ECG')
  })

  it('rejects unsupported and oversized files before uploading', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    const requests = stubUploads(() => ({ status: 201, body: {} }))
    renderAt('/documents?group=none')
    const input = await screen.findByLabelText('Choose a file')

    fireEvent.change(input, { target: { files: [new File(['hello'], 'notes.txt', { type: 'text/plain' })] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Only PDF, JPEG, and PNG files can be uploaded.')

    const big = new File(['x'], 'huge.pdf', { type: 'application/pdf' })
    Object.defineProperty(big, 'size', { value: 21 * 1024 * 1024 })
    fireEvent.change(input, { target: { files: [big] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('20 MB or smaller')

    await userEvent.click(screen.getByRole('button', { name: 'Upload' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose a file to upload.')
    expect(requests).toHaveLength(0)
  })

  it('asks for a clearer copy when the server finds the photo or scan unclear', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    const issue = 'This image looks blurry. Please take a clearer photo in good light, or upload the original PDF.'
    stubUploads(() => ({
      status: 422,
      body: {
        error: { code: 'VALIDATION_ERROR', message: 'Invalid input.', details: [{ field: 'file', issue }], request_id: 'r1' },
      },
    }))
    renderAt('/documents?group=none')

    await userEvent.upload(await screen.findByLabelText('Choose a file'), pdfFile())
    await userEvent.type(screen.getByLabelText('Name (required)'), 'Blood test')
    await fillDetails()
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(issue)
  })

  it('links to the existing document when the same file was already uploaded', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    stubUploads(() => ({
      status: 409,
      body: {
        error: {
          code: 'DUPLICATE_DOCUMENT',
          message: 'You have already uploaded this file.',
          details: [{ field: 'existing_document_id', issue: 'doc-existing' }],
          request_id: 'r1',
        },
      },
    }))
    renderAt('/documents?group=none')

    await userEvent.upload(await screen.findByLabelText('Choose a file'), pdfFile())
    await userEvent.type(screen.getByLabelText('Name (required)'), 'Copy')
    await fillDetails()
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }))

    const link = await screen.findByRole('link', { name: 'View the existing document' })
    expect(link).toHaveAttribute('href', '/documents/doc-existing')
  })

  it('filters by type and loads more pages', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /documents': () => page([makeDocument()], 'cursor-2'),
      'GET /documents?cursor=cursor-2': () => page([makeDocument({ id: 'doc-2', title: 'Older report' })]),
      'GET /documents?category=prescription': () => page([]),
    })
    renderAt('/documents?group=none')

    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }))
    expect(await screen.findByRole('link', { name: 'Older report' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Report type'), 'prescription')
    expect(await screen.findByText('No documents match these filters.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/documents?category=prescription'))).toBe(true)
  })
})

describe('Filtering and grouping documents', () => {
  const PROVIDERS = {
    items: [
      { name: 'Apollo Hospitals', document_count: 2 },
      { name: 'SampleCare Clinic', document_count: 1 },
    ],
    without_provider: 1,
  }
  const day = { document_date_precision: 'day' as const }
  const LIBRARY = [
    makeDocument({ id: 'a', title: 'CBC', document_date: '2026-10-07', ...day, provider_name: 'Apollo Hospitals' }),
    makeDocument({ id: 'b', title: 'Lipids', document_date: '2026-08-15', ...day, provider_name: 'apollo  hospitals' }),
    makeDocument({
      id: 'c',
      title: 'Prescription Oct',
      category: 'prescription',
      document_date: '2026-10-01',
      ...day,
      provider_name: 'SampleCare Clinic',
    }),
    makeDocument({
      id: 'd',
      title: 'Old scan',
      category: 'imaging_report',
      document_date: '2024-01-01',
      document_date_precision: 'year',
      provider_name: null,
    }),
    makeDocument({
      id: 'e',
      title: 'Undated note',
      category: 'other',
      document_date: null,
      document_date_precision: null,
      provider_name: null,
    }),
  ]
  const groupHeadings = () =>
    screen.getAllByRole('region', { name: /\(\d+\)$/ }).map((region) => within(region).getByRole('heading').textContent)
  const groupTitles = (name: RegExp) =>
    within(screen.getByRole('region', { name })).getAllByRole('link').map((link) => link.textContent)
  const providers = () => jsonResponse(200, PROVIDERS)

  it('groups by hospital, counting spelling variants together, with "No hospital given" last', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents/providers': providers, 'GET /documents?limit=50': () => page(LIBRARY) })
    renderAt('/documents?group=hospital')

    await screen.findByRole('region', { name: /Apollo Hospitals/ })
    expect(groupHeadings()).toEqual(['Apollo Hospitals (2)', 'SampleCare Clinic (1)', 'No hospital given (2)'])
    expect(groupTitles(/Apollo Hospitals/)).toEqual(['CBC', 'Lipids'])
  })

  it('groups by report month, newest first, with year-only and undated documents placed clearly', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents/providers': providers, 'GET /documents?limit=50': () => page(LIBRARY) })
    renderAt('/documents?group=date')

    await screen.findByRole('region', { name: /October 2026/ })
    expect(groupHeadings()).toEqual([
      'October 2026 (2)',
      'August 2026 (1)',
      '2024 (month not given) (1)',
      'No date (1)',
    ])
    expect(groupTitles(/October 2026/)).toEqual(['CBC', 'Prescription Oct'])
  })

  it('opens grouped by report type', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents/providers': providers, 'GET /documents?limit=50': () => page(LIBRARY) })
    renderAt('/documents')

    await screen.findByRole('region', { name: /Laboratory reports/ })
    expect(screen.getByLabelText('Group by')).toHaveValue('type')
    expect(groupHeadings()[0]).toBe('Laboratory reports (2)')
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument() // the default view
  })

  it('groups by type in the usual type order', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents/providers': providers, 'GET /documents?limit=50': () => page(LIBRARY) })
    renderAt('/documents?group=type')

    await screen.findByRole('region', { name: /Laboratory reports/ })
    expect(groupHeadings()).toEqual([
      'Laboratory reports (2)',
      'Text-based imaging reports (1)',
      'Prescription (1)',
      'Other (1)',
    ])
  })

  it('loads every page when grouped, so groups are complete', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /documents/providers': providers,
      'GET /documents?limit=50': () => page(LIBRARY.slice(0, 2), 'next-page'),
      'GET /documents?limit=50&cursor=next-page': () => page(LIBRARY.slice(2)),
    })
    renderAt('/documents?group=type')

    expect(await screen.findByRole('region', { name: /Other/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })

  it('sends the filters to the server and keeps them until cleared', async () => {
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /documents/providers': providers,
      'GET /documents': () => page(LIBRARY),
      'GET /documents?limit=50': () => page(LIBRARY), // cleared: back to the default, grouped by report type
      'GET /documents?category=lab_report': () => page(LIBRARY.slice(0, 2)),
      'GET /documents?category=lab_report&provider=Apollo+Hospitals': () => page(LIBRARY.slice(0, 2)),
      'GET /documents?category=lab_report&provider_missing=true': () => page([]),
    })
    renderAt('/documents?group=none')

    const hospital = await screen.findByLabelText('Hospital or clinic')
    expect(await within(hospital).findByRole('option', { name: 'Apollo Hospitals (2)' })).toBeInTheDocument()
    expect(within(hospital).getByRole('option', { name: 'No hospital given (1)' })).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Report type'), 'lab_report')
    await userEvent.selectOptions(hospital, 'Apollo Hospitals')
    expect(await screen.findByRole('link', { name: 'Lipids' })).toBeInTheDocument()
    const called = (suffix: string) => fetchMock.mock.calls.some(([url]) => String(url).endsWith(suffix))
    await screen.findByRole('link', { name: 'CBC' })
    expect(called('/documents?category=lab_report&provider=Apollo+Hospitals')).toBe(true)

    await userEvent.selectOptions(hospital, 'No hospital given (1)')
    expect(await screen.findByText('No documents match these filters.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(await screen.findByRole('link', { name: 'Undated note' })).toBeInTheDocument()
    expect(screen.getByLabelText('Report type')).toHaveValue('')
  })

  it('reads filters from the address and filters by report date', async () => {
    stubFetch({
      ...LOGGED_IN,
      'GET /documents/providers': providers,
      'GET /documents?date_from=2026-09-01&date_to=2026-10-31': () => page([LIBRARY[0], LIBRARY[2]]),
    })
    renderAt('/documents?from=2026-09-01&to=2026-10-31&group=none')

    expect(await screen.findByRole('link', { name: 'CBC' })).toBeInTheDocument()
    expect(screen.getByLabelText('Report date from')).toHaveValue('2026-09-01')
    expect(screen.getByText(/without a report date are not shown/)).toBeInTheDocument()
  })

  it('does not load when the end date is before the start date', async () => {
    const fetchMock = stubFetch({ ...LOGGED_IN, 'GET /documents/providers': providers })
    renderAt('/documents?from=2026-10-01&to=2026-09-01&group=none')

    expect(await screen.findByText('The end date cannot be before the start date.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('date_from'))).toBe(false)
  })
})

describe('Document detail page', () => {
  it('previews the file through an authorised blob URL', async () => {
    const blobs = stubObjectUrls()
    stubFetch({
      ...LOGGED_IN,
      'GET /documents/doc-1': () => jsonResponse(200, makeDocument({ media_type: 'image/png', title: 'Chest scan', original_filename: 'scan.png' })),
      'GET /documents/doc-1/file': () => new Response(new Blob(['png-bytes'], { type: 'image/png' })),
    })
    renderAt('/documents/doc-1')

    expect(await screen.findByRole('img', { name: 'Preview of Chest scan' })).toHaveAttribute('src', 'blob:fake-1')
    expect(screen.getByRole('heading', { level: 1, name: 'Chest scan' })).toBeInTheDocument()
    expect(blobs).toHaveLength(1)
  })

  it('edits details', async () => {
    stubObjectUrls()
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /documents/doc-1': () => jsonResponse(200, makeDocument()),
      'GET /documents/doc-1/file': () => new Response(new Blob(['%PDF'])),
      'PATCH /documents/doc-1': () => jsonResponse(200, makeDocument({ title: 'Blood test (repeat)', provider_name: 'General Hospital', report_subtype: 'Lipid profile' })),
    })
    renderAt('/documents/doc-1')

    await userEvent.click(await screen.findByRole('button', { name: 'Edit details' }))
    const name = screen.getByLabelText('Name (required)')
    expect(name).toHaveValue('Blood test March')
    await userEvent.clear(name)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByText('Enter a name for this document.')).toBeInTheDocument() // a name cannot be removed
    await userEvent.type(name, 'Blood test (repeat)')

    const provider = screen.getByLabelText('Hospital, lab, or clinic')
    await userEvent.clear(provider)
    await userEvent.type(provider, 'General Hospital')
    await userEvent.type(screen.getByLabelText('Report sub-type (optional)'), 'Lipid profile')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('General Hospital')).toBeInTheDocument()
    expect(screen.getByText('Report sub-type').nextElementSibling).toHaveTextContent('Lipid profile')
    expect(screen.getByRole('heading', { level: 1, name: 'Blood test (repeat)' })).toBeInTheDocument()
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      title: 'Blood test (repeat)',
      category: 'lab_report',
      report_subtype: 'Lipid profile',
      document_date: '2026-03-01',
      document_date_precision: 'month',
      provider_name: 'General Hospital',
    })
  })

  it('asks for confirmation, then deletes and returns to the list', async () => {
    stubObjectUrls()
    const fetchMock = stubFetch({
      ...LOGGED_IN,
      'GET /documents/doc-1': () => jsonResponse(200, makeDocument()),
      'GET /documents/doc-1/file': () => new Response(new Blob(['%PDF'])),
      'DELETE /documents/doc-1': () => new Response(null, { status: 204 }),
      'GET /documents': () => page([]),
    })
    renderAt('/documents/doc-1')

    await userEvent.click(await screen.findByRole('button', { name: 'Delete document' }))
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('Delete “Blood test March” permanently?')
    expect(dialog).toHaveTextContent('Backup copies are erased automatically within 30 days')
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)

    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete permanently' }))

    expect(await screen.findByRole('heading', { name: 'Medical Documents' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(true)
  })

  it('explains a missing or deleted document', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents/gone': () => errorResponse(404, 'NOT_FOUND') })
    renderAt('/documents/gone')

    expect(await screen.findByRole('alert')).toHaveTextContent('does not exist or has been deleted')
  })
})
