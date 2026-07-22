/**
 * UploadDocuments tests
 *
 *  1. Renders form fields; upload disabled until doc type + period + files chosen
 *  2. Adding files via input updates the file list, rejects non-PDF
 *  3. Clear all removes selected files
 *  4. Successful upload: posts multipart form, shows summary banner, opens SSE per file
 *  5. Upload API failure: marks all results as ERROR with message
 *  6. Over-limit (too many / too large files) blocks upload and shows warning
 *  7. SSE message updates a file's pipeline stage; ROUTED closes the stream
 *  8. SSE onerror marks file as ERROR with disconnect message
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { UploadDocuments } from './UploadDocuments'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn(), get: vi.fn() } }))
import { api } from '@/lib/api'
const mockPost = vi.mocked(api.post)
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

// ── Minimal controllable EventSource mock ──────────────────────────────────
class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onmessage: ((e: any) => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
  close() { this.closed = true }
  emit(data: any) { this.onmessage?.({ data: JSON.stringify(data) }) }
  triggerError() { this.onerror?.() }
}

function makeFile(name: string, size = 1024, type = 'application/pdf') {
  const file = new File(['x'.repeat(size)], name, { type })
  return file
}

beforeEach(() => {
  vi.clearAllMocks()
  MockEventSource.instances = []
  vi.stubGlobal('EventSource', MockEventSource as any)
  // Checklist gate query — default to no incomplete items so existing
  // upload-flow tests are unaffected; individual tests can override.
  mockGet.mockResolvedValue({ data: { items: [] } })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('UploadDocuments — form state', () => {
  it('renders the form and disables upload until required fields are filled', () => {
    render(<UploadDocuments />, { wrapper })
    expect(screen.getByText('Upload Documents')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Start Upload & Process/ })).toBeDisabled()
  })

  it('adds a PDF file via the hidden file input and enables upload after required fields set', async () => {
    render(<UploadDocuments />, { wrapper })
    const user = userEvent.setup()

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, makeFile('slip.pdf'))
    expect(await screen.findByText('slip.pdf')).toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox'), 'SALARY_SLIP')
    await user.type(screen.getByPlaceholderText('e.g. Jun 2024 · FY2023-24 · 2024-06-15'), 'Jun 2024')

    expect(screen.getByRole('button', { name: /Start Upload & Process/ })).not.toBeDisabled()
  })

  it('rejects non-PDF files', async () => {
    render(<UploadDocuments />, { wrapper })
    const user = userEvent.setup()
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, makeFile('resume.docx', 100, 'application/msword'))
    expect(screen.queryByText('resume.docx')).not.toBeInTheDocument()
  })

  it('clear all removes selected files', async () => {
    render(<UploadDocuments />, { wrapper })
    const user = userEvent.setup()
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, makeFile('slip.pdf'))
    expect(await screen.findByText('slip.pdf')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Clear all' }))
    expect(screen.queryByText('slip.pdf')).not.toBeInTheDocument()
  })

  it('shows over-limit warning and blocks upload when total size exceeds 500MB', async () => {
    render(<UploadDocuments />, { wrapper })
    const user = userEvent.setup()
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const bigFile = makeFile('big.pdf', 501 * 1024 * 1024)
    await user.upload(fileInput, bigFile)

    expect(await screen.findByText('Exceeds 500 MB or 2,000 files limit. Remove files to continue.')).toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox'), 'SALARY_SLIP')
    await user.type(screen.getByPlaceholderText('e.g. Jun 2024 · FY2023-24 · 2024-06-15'), 'Jun 2024')
    expect(screen.getByRole('button', { name: /Start Upload & Process/ })).toBeDisabled()
  })

  it('blocks upload and shows a message when required setup checklist items are incomplete', async () => {
    mockGet.mockResolvedValue({
      data: { items: [
        { item_id: 'i-1', is_platform_baseline: true, item_key: 'GRIEVANCE_OFFICER_CONFIGURED',
          title: 'Grievance Officer configured', description: null, is_required: true, completed: false },
      ] },
    })
    render(<UploadDocuments />, { wrapper })
    const user = userEvent.setup()

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, makeFile('slip.pdf'))
    await screen.findByText('slip.pdf')
    await user.selectOptions(screen.getByRole('combobox'), 'SALARY_SLIP')
    await user.type(screen.getByPlaceholderText('e.g. Jun 2024 · FY2023-24 · 2024-06-15'), 'Jun 2024')

    expect(await screen.findByText(/setup checklist item\(s\) are complete/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Start Upload & Process/ })).toBeDisabled()
  })
})

describe('UploadDocuments — upload flow', () => {
  async function fillAndUpload(user: ReturnType<typeof userEvent.setup>, fileName = 'slip.pdf') {
    render(<UploadDocuments />, { wrapper })
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, makeFile(fileName))
    await screen.findByText(fileName)
    await user.selectOptions(screen.getByRole('combobox'), 'SALARY_SLIP')
    await user.type(screen.getByPlaceholderText('e.g. Jun 2024 · FY2023-24 · 2024-06-15'), 'Jun 2024')
    await user.click(screen.getByRole('button', { name: /Start Upload & Process/ }))
  }

  it('posts multipart form data and shows the submitted summary banner', async () => {
    mockPost.mockResolvedValue({
      data: { files: [{ filename: 'slip.pdf', document_id: 'doc-1' }] },
    })
    const user = userEvent.setup()
    await fillAndUpload(user)

    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    const [url, form, config] = mockPost.mock.calls[0]
    expect(url).toBe('/v1/ingest/upload')
    expect(form).toBeInstanceOf(FormData)
    expect(config?.headers?.['Content-Type']).toBe('multipart/form-data')

    expect(await screen.findByText('1 files submitted')).toBeInTheDocument()
  })

  it('opens an SSE connection per uploaded file and updates status on message', async () => {
    mockPost.mockResolvedValue({
      data: { files: [{ filename: 'slip.pdf', document_id: 'doc-1' }] },
    })
    const user = userEvent.setup()
    await fillAndUpload(user)
    await screen.findByText('1 files submitted')

    await waitFor(() => expect(MockEventSource.instances.length).toBe(1))
    const es = MockEventSource.instances[0]
    expect(es.url).toContain('/api/v1/ingest/status/doc-1')

    es.emit({ pipeline_status: 'ROUTED' })
    expect(await screen.findByText('1 routed to vault')).toBeInTheDocument()
    expect(es.closed).toBe(true)
  })

  it('marks file as ERROR with disconnect note on SSE error before terminal status', async () => {
    mockPost.mockResolvedValue({
      data: { files: [{ filename: 'slip.pdf', document_id: 'doc-1' }] },
    })
    const user = userEvent.setup()
    await fillAndUpload(user)
    await screen.findByText('1 files submitted')

    await waitFor(() => expect(MockEventSource.instances.length).toBe(1))
    const es = MockEventSource.instances[0]
    es.triggerError()

    expect(await screen.findByText('Status stream disconnected')).toBeInTheDocument()
    expect(es.closed).toBe(true)
  })

  it('shows ERROR results and error summary count when upload API call fails', async () => {
    mockPost.mockRejectedValue({ response: { data: { detail: 'Server exploded' } } })
    const user = userEvent.setup()
    await fillAndUpload(user)

    expect(await screen.findByText('Server exploded')).toBeInTheDocument()
    expect(screen.getByText('1 errors')).toBeInTheDocument()
  })

  it('falls back to a generic failure message when the API error has no detail', async () => {
    mockPost.mockRejectedValue(new Error('network down'))
    const user = userEvent.setup()
    await fillAndUpload(user)

    expect(await screen.findByText('Upload failed')).toBeInTheDocument()
  })
})
