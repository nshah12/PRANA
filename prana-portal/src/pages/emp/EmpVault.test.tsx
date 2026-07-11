import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { EmpVault } from './EmpVault'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const PROFILE = {
  employers: [
    { tenant_id: 't1', tenant_name: 'TechCorp', doj: '2020-01-01', dol: null, designation: 'Engineer' },
    { tenant_id: 't2', tenant_name: 'OldCo', doj: '2017-01-01', dol: '2019-12-31', designation: 'Analyst' },
  ],
  vault_url: 'prana.in/vault/abc123',
  active_since: '2017-01-01',
}

const DOCS = {
  documents: [
    { document_id: 'd1', tenant_id: 't1', doc_type: 'SALARY_SLIP', doc_period: '2024-01', pushed_at: '2024-02-01', is_self_upload: false, original_filename: 'jan.pdf' },
    { document_id: 'd2', tenant_id: 't2', doc_type: 'FORM_16', doc_period: '2019', pushed_at: '2020-01-01', is_self_upload: true, original_filename: 'form16.pdf' },
  ],
}

const SHARES = { shares: [{ token_id: 's1', is_active: true, expires_at: new Date(Date.now() + 86400000).toISOString() }] }

function mockAllEndpoints({ profile = PROFILE, docs = DOCS, shares = SHARES } = {}) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/vault/profile') return Promise.resolve({ data: profile })
    if (url === '/v1/vault/documents') return Promise.resolve({ data: docs })
    if (url === '/v1/vault/share') return Promise.resolve({ data: shares })
    return Promise.reject(new Error('unexpected url: ' + url))
  })
}

beforeEach(() => vi.clearAllMocks())

describe('EmpVault', () => {
  it('shows a loading skeleton while documents are being fetched', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<EmpVault />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows an empty state when there are no documents', async () => {
    mockAllEndpoints({ docs: { documents: [] } })
    render(<EmpVault />, { wrapper })
    expect(await screen.findByText('No documents found')).toBeInTheDocument()
    expect(screen.getByText('Try a different filter or search term.')).toBeInTheDocument()
  })

  it('renders documents grouped by employer with stat cards', async () => {
    mockAllEndpoints()
    render(<EmpVault />, { wrapper })

    expect((await screen.findAllByText('TechCorp')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('OldCo').length).toBeGreaterThan(0)
    expect(screen.getByText('SALARY SLIP')).toBeInTheDocument()
    expect(screen.getByText('FORM 16')).toBeInTheDocument()

    // Stat card: total documents
    expect(screen.getByText('Total Documents')).toBeInTheDocument()
  })

  it('shows the vault URL and copies it to the clipboard', async () => {
    mockAllEndpoints()
    // userEvent.setup() installs its own navigator.clipboard stub (for its
    // copy()/paste() APIs) — if the spy is set up BEFORE setup() runs, setup()
    // clobbers it, and this test's `writeText` reference is no longer the one
    // the button's onClick handler actually calls. Set up the spy AFTER.
    const user = userEvent.setup()
    if (!navigator.clipboard) {
      Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn() }, configurable: true })
    }
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined)
    render(<EmpVault />, { wrapper })

    expect(await screen.findByText('prana.in/vault/abc123')).toBeInTheDocument()
    const btn = screen.getByRole('button', { name: /copy url/i })
    console.error('DEBUG btn.outerHTML:', btn.outerHTML)
    console.error('DEBUG navigator.clipboard === original:', navigator.clipboard.writeText === writeText.getMockImplementation())
    await user.click(btn)
    console.error('DEBUG writeText calls:', writeText.mock.calls)
    expect(writeText).toHaveBeenCalledWith('https://prana.in/vault/abc123')
    expect(await screen.findByText('Copied!')).toBeInTheDocument()
  })

  it('filters documents by search term', async () => {
    mockAllEndpoints()
    const user = userEvent.setup()
    render(<EmpVault />, { wrapper })

    await screen.findAllByText('TechCorp')
    const search = screen.getByPlaceholderText('Search documents…')
    await user.type(search, 'form_16')

    await waitFor(() => expect(screen.queryByText('SALARY SLIP')).not.toBeInTheDocument())
    expect(screen.getByText('FORM 16')).toBeInTheDocument()
  })

  it('filters documents by employer pill — only matching org section remains', async () => {
    mockAllEndpoints()
    const user = userEvent.setup()
    render(<EmpVault />, { wrapper })

    await screen.findAllByText('TechCorp')
    // Employer pill uses first word of employer name
    await user.click(screen.getByRole('button', { name: 'TechCorp' }))

    await waitFor(() => expect(screen.queryByText('SALARY SLIP')).toBeInTheDocument())
    expect(screen.queryByText('FORM 16')).not.toBeInTheDocument()
  })

  it('never renders a raw rupee figure anywhere in the vault view — privacy contract', async () => {
    mockAllEndpoints()
    render(<EmpVault />, { wrapper })
    await screen.findAllByText('TechCorp')
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
  })
})
