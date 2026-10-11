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
    document_date: '2026-03-01',
    document_date_precision: 'month',
    provider_name: 'City Diagnostics',
    processing_status: 'pending',
    created_at: '2026-10-11T09:00:00Z',
    updated_at: '2026-10-11T09:00:00Z',
    ...overrides,
  }
}

const page = (items: MedicalDocument[], nextCursor: string | null = null) =>
  jsonResponse(200, { items, pagination: { limit: 20, next_cursor: nextCursor } })

const pdfFile = (name = 'new-report.pdf') => new File(['%PDF-1.4 synthetic'], name, { type: 'application/pdf' })

describe('Documents page', () => {
  it('lists documents with their details, showing only as much of the date as is known', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([makeDocument()]) })
    renderAt('/documents')

    const item = (await screen.findByRole('link', { name: 'Blood test March' })).closest('li') as HTMLElement
    expect(within(item).getByText(/Lab report · March 2026 · City Diagnostics/)).toBeInTheDocument()
    expect(within(item).getByText(/blood-test\.pdf · PDF · 178 KB/)).toBeInTheDocument()
    expect(within(item).getByText('Waiting for processing (extraction coming soon)')).toBeInTheDocument()
  })

  it('shows your documents above the upload panel, with a link down to it', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([makeDocument()]) })
    renderAt('/documents')

    const listHeading = await screen.findByRole('heading', { name: 'Your documents' })
    const uploadHeading = screen.getByRole('heading', { name: 'Upload a document' })
    expect(listHeading.compareDocumentPosition(uploadHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByRole('link', { name: /Upload a document/ })).toHaveAttribute('href', '#upload')
  })

  it('explains what is missing when Upload is clicked with nothing chosen', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    const requests = stubUploads(() => ({ status: 201, body: {} }))
    renderAt('/documents')

    await userEvent.click(await screen.findByRole('button', { name: 'Upload' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Choose a file to upload.')
    expect(screen.getByText('Enter a name for this document.')).toBeInTheDocument()
    expect(screen.getByLabelText('Name (required)')).toHaveAttribute('aria-invalid', 'true')
    expect(requests).toHaveLength(0)
  })

  it('requires a name even when a file is chosen', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    const requests = stubUploads(() => ({ status: 201, body: {} }))
    renderAt('/documents')

    await userEvent.upload(await screen.findByLabelText('Choose a file'), pdfFile())
    await userEvent.type(screen.getByLabelText('Name (required)'), '   ')
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(screen.getByText('Enter a name for this document.')).toBeInTheDocument()
    expect(screen.queryByText('Choose a file to upload.')).not.toBeInTheDocument()
    expect(requests).toHaveLength(0)
  })

  it('shows a helpful empty state', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    renderAt('/documents')

    expect(await screen.findByText('No documents yet.')).toBeInTheDocument()
  })

  it('uploads a file with progress and adds it to the list', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    const requests = stubUploads(() => ({
      status: 201,
      body: makeDocument({ id: 'doc-new', title: 'Thyroid panel', original_filename: 'new-report.pdf' }),
    }))
    renderAt('/documents')

    await userEvent.upload(await screen.findByLabelText('Choose a file'), pdfFile())
    await userEvent.type(screen.getByLabelText('Name (required)'), '  Thyroid panel ')
    await userEvent.click(screen.getByText('Add details (optional)'))
    await userEvent.selectOptions(screen.getByLabelText('Document type'), 'prescription')
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Uploaded “Thyroid panel”.')
    expect(screen.getByRole('link', { name: 'Thyroid panel' })).toBeInTheDocument()
    expect(screen.getByLabelText('Name (required)')).toHaveValue('') // form reset for the next upload

    const [request] = requests
    expect(request.url).toBe('http://localhost:8000/api/v1/documents')
    expect(request.headers.Authorization).toBe('Bearer access-1')
    expect(request.body.get('title')).toBe('Thyroid panel')
    expect(request.body.get('category')).toBe('prescription')
    expect(request.body.has('provider_name')).toBe(false) // blank fields are not sent
  })

  it('rejects unsupported and oversized files before uploading', async () => {
    stubFetch({ ...LOGGED_IN, 'GET /documents': () => page([]) })
    const requests = stubUploads(() => ({ status: 201, body: {} }))
    renderAt('/documents')
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
    renderAt('/documents')

    await userEvent.upload(await screen.findByLabelText('Choose a file'), pdfFile())
    await userEvent.type(screen.getByLabelText('Name (required)'), 'Copy')
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
    renderAt('/documents')

    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }))
    expect(await screen.findByRole('link', { name: 'Older report' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Show'), 'prescription')
    expect(await screen.findByText('No documents of this type yet.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/documents?category=prescription'))).toBe(true)
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
      'PATCH /documents/doc-1': () => jsonResponse(200, makeDocument({ title: 'Blood test (repeat)', provider_name: 'General Hospital' })),
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
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('General Hospital')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Blood test (repeat)' })).toBeInTheDocument()
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      title: 'Blood test (repeat)',
      category: 'lab_report',
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

    await userEvent.click(await screen.findByRole('button', { name: 'Delete…' }))
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
