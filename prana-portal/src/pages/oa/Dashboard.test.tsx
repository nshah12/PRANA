/**
 * Dashboard tests — OA-Operator / OA-Admin landing page.
 *
 *  1. Non-OA roles (chro/cfo/ciso) get a role-specific landing card, no API calls
 *  2. Loading skeleton while stats/recent/exceptions are in flight
 *  3. Error state with retry button on stats failure
 *  4. Stat cards render with values from API
 *  5. Elevation callout shown for operator, not for admin
 *  6. Exception banner shown for admin when exceptions exist
 *  7. Recent uploads list renders documents; empty state when none
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Dashboard } from './Dashboard'
import { useAuthStore } from '@/store/auth'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

function setUser(role: 'oa_operator' | 'oa_admin' | 'chro' | 'cfo' | 'ciso') {
  useAuthStore.getState().setUser({
    userId: 'u-1', email: 'x@acme.example', displayName: 'X',
    role, tenantId: 't-1', tenantName: 'Acme Ltd',
  })
}

const STATS = { documents_pushed: 120, pending_pipeline: 5, open_exceptions: 2, employees: 340 }
const RECENT = { documents: [
  { document_id: 'd-1', doc_type: 'SALARY_SLIP', doc_period: 'Jun 2024', pipeline_status: 'ROUTED', pushed_at: new Date().toISOString() },
] }
const EXCEPTIONS = { exceptions: [{ exception_id: 'e-1' }, { exception_id: 'e-2' }] }

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.getState().logout()
})

describe('Dashboard — non-OA roles', () => {
  it('shows CHRO landing card and does not call the API', () => {
    setUser('chro')
    render(<Dashboard />, { wrapper })
    expect(screen.getByText('Workforce Overview')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open CHRO Dashboard →' })).toHaveAttribute('href', '/org/chro')
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('shows CFO landing card', () => {
    setUser('cfo')
    render(<Dashboard />, { wrapper })
    expect(screen.getByText('Financial Analytics')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open CFO Dashboard →' })).toHaveAttribute('href', '/org/cfo')
  })

  it('shows CISO landing card', () => {
    setUser('ciso')
    render(<Dashboard />, { wrapper })
    expect(screen.getByText('Security Dashboard')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open CISO Dashboard →' })).toHaveAttribute('href', '/org/ciso')
  })
})

describe('Dashboard — OA-Operator / OA-Admin', () => {
  it('shows loading skeleton while fetching', () => {
    setUser('oa_operator')
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<Dashboard />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error state with retry button on stats failure', async () => {
    setUser('oa_operator')
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/ingest/stats')) return Promise.reject(new Error('network'))
      return Promise.resolve({ data: {} })
    })
    render(<Dashboard />, { wrapper })
    await waitFor(() => expect(screen.getByText('Failed to load dashboard data.')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('renders stat cards with values from API (operator)', async () => {
    setUser('oa_operator')
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/ingest/stats')) return Promise.resolve({ data: STATS })
      if (url.includes('/ingest/documents')) return Promise.resolve({ data: RECENT })
      if (url.includes('/org/exceptions')) return Promise.resolve({ data: { exceptions: [] } })
      return Promise.resolve({ data: {} })
    })
    render(<Dashboard />, { wrapper })
    expect(await screen.findByText('120')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('340')).toBeInTheDocument()
  })

  it('shows elevation callout for operator (not admin)', async () => {
    setUser('oa_operator')
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/ingest/stats')) return Promise.resolve({ data: STATS })
      if (url.includes('/ingest/documents')) return Promise.resolve({ data: RECENT })
      if (url.includes('/org/exceptions')) return Promise.resolve({ data: { exceptions: [] } })
      return Promise.resolve({ data: {} })
    })
    render(<Dashboard />, { wrapper })
    expect(await screen.findByText('Need to view documents?')).toBeInTheDocument()
  })

  it('does not show elevation callout for admin', async () => {
    setUser('oa_admin')
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/ingest/stats')) return Promise.resolve({ data: STATS })
      if (url.includes('/ingest/documents')) return Promise.resolve({ data: RECENT })
      if (url.includes('/org/exceptions')) return Promise.resolve({ data: { exceptions: [] } })
      return Promise.resolve({ data: {} })
    })
    render(<Dashboard />, { wrapper })
    await screen.findByText('120')
    expect(screen.queryByText('Need to view documents?')).not.toBeInTheDocument()
  })

  it('shows exception banner for admin when exceptions exist', async () => {
    setUser('oa_admin')
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/ingest/stats')) return Promise.resolve({ data: STATS })
      if (url.includes('/ingest/documents')) return Promise.resolve({ data: RECENT })
      if (url.includes('/org/exceptions')) return Promise.resolve({ data: EXCEPTIONS })
      return Promise.resolve({ data: {} })
    })
    render(<Dashboard />, { wrapper })
    expect(await screen.findByText('2 documents need manual resolution')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /View exception queue/ })).toHaveAttribute('href', '/org/exceptions')
  })

  it('shows empty state when there are no recent documents', async () => {
    setUser('oa_operator')
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/ingest/stats')) return Promise.resolve({ data: STATS })
      if (url.includes('/ingest/documents')) return Promise.resolve({ data: { documents: [] } })
      if (url.includes('/org/exceptions')) return Promise.resolve({ data: { exceptions: [] } })
      return Promise.resolve({ data: {} })
    })
    render(<Dashboard />, { wrapper })
    expect(await screen.findByText('No documents uploaded yet.')).toBeInTheDocument()
  })
})
