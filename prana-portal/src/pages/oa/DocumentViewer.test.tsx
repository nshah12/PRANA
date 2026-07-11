/**
 * DocumentViewer tests — OA document list with view/delete actions.
 *
 *  1. Loading state shows loading row
 *  2. Error state — shows error message (RED: source had no isError handling; fixed to add it)
 *  3. Empty state — no documents
 *  4. Renders document rows with fields formatted; no raw PAN/salary rendered anywhere
 *  5. Doc type filter select sends doc_type param
 *  6. View button opens document in a new tab at the watermarked API endpoint
 *  7. Delete button — visible only for oa_admin, confirms, calls DELETE, and refetches
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { DocumentViewer } from './DocumentViewer'
import { useAuthStore } from '@/store/auth'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockDelete = vi.mocked(api.delete)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

function setUser(role: 'oa_operator' | 'oa_admin') {
  useAuthStore.getState().setUser({
    userId: 'u-1', email: 'x@acme.example', displayName: 'X',
    role, tenantId: 't-1', tenantName: 'Acme Ltd',
  })
}

function makeDocs(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    document_id: `doc-${i}`,
    doc_type: 'SALARY_SLIP',
    doc_period: `Jun 202${i}`,
    pipeline_status: 'ROUTED',
    pushed_at: new Date().toISOString(),
  }))
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.getState().logout()
})

describe('DocumentViewer', () => {
  it('shows loading state while fetching', () => {
    setUser('oa_operator')
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<DocumentViewer />, { wrapper })
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows an error message when the documents query fails', async () => {
    setUser('oa_operator')
    mockGet.mockRejectedValue(new Error('network down'))
    render(<DocumentViewer />, { wrapper })
    expect(await screen.findByText('Failed to load documents.')).toBeInTheDocument()
  })

  it('shows empty state when there are no documents', async () => {
    setUser('oa_operator')
    mockGet.mockResolvedValue({ data: { documents: [] } })
    render(<DocumentViewer />, { wrapper })
    expect(await screen.findByText('No documents found.')).toBeInTheDocument()
  })

  it('renders document rows with formatted fields and never shows raw PAN/salary figures', async () => {
    setUser('oa_operator')
    mockGet.mockResolvedValue({ data: { documents: makeDocs(2) } })
    render(<DocumentViewer />, { wrapper })
    expect(await screen.findByText('Jun 2020')).toBeInTheDocument()
    const tbody = document.querySelector('tbody') as HTMLElement
    expect(within(tbody).getAllByText('SALARY SLIP').length).toBe(2)
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
    expect(document.body.textContent).not.toMatch(/\b[A-Z]{5}\d{4}[A-Z]\b/) // PAN pattern
  })

  it('sends doc_type filter param when the select changes', async () => {
    setUser('oa_operator')
    mockGet.mockResolvedValue({ data: { documents: [] } })
    render(<DocumentViewer />, { wrapper })
    await waitFor(() => expect(mockGet).toHaveBeenCalled())

    const user = userEvent.setup()
    await user.selectOptions(screen.getByRole('combobox'), 'FORM_16')

    await waitFor(() => {
      const lastCall = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      expect(lastCall[1]?.params?.doc_type).toBe('FORM_16')
    })
  })

  it('opens the document in a new tab via the watermarked vault endpoint', async () => {
    setUser('oa_operator')
    mockGet.mockResolvedValue({ data: { documents: makeDocs(1) } })
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    render(<DocumentViewer />, { wrapper })

    const user = userEvent.setup()
    await screen.findByText('Jun 2020')
    await user.click(screen.getByRole('button', { name: /View/ }))

    expect(openSpy).toHaveBeenCalledWith('/api/v1/vault/documents/doc-0', '_blank')
    openSpy.mockRestore()
  })

  it('does not show a Delete button for oa_operator', async () => {
    setUser('oa_operator')
    mockGet.mockResolvedValue({ data: { documents: makeDocs(1) } })
    render(<DocumentViewer />, { wrapper })
    await screen.findByText('Jun 2020')
    expect(screen.queryByRole('button', { name: /Delete/ })).not.toBeInTheDocument()
  })

  it('oa_admin can delete a document after confirming, then refetches', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { documents: makeDocs(1) } })
    mockDelete.mockResolvedValue({ data: {} })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<DocumentViewer />, { wrapper })

    const user = userEvent.setup()
    await screen.findByText('Jun 2020')
    await user.click(screen.getByRole('button', { name: /Delete/ }))

    expect(confirmSpy).toHaveBeenCalledWith('Mark this document as deleted? This cannot be undone.')
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/v1/ingest/documents/doc-0'))
    // refetch triggers a second GET call
    await waitFor(() => expect(mockGet.mock.calls.length).toBeGreaterThan(1))
    confirmSpy.mockRestore()
  })

  it('does not call the delete API when confirm is cancelled', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { documents: makeDocs(1) } })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<DocumentViewer />, { wrapper })

    const user = userEvent.setup()
    await screen.findByText('Jun 2020')
    await user.click(screen.getByRole('button', { name: /Delete/ }))

    expect(mockDelete).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })
})
