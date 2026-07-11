import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

import { PipelineHealth } from './PipelineHealth'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK = {
  counts: { QUEUED: 5, ENCRYPTING: 1, SCANNING: 2, EXTRACTING: 3, RESOLVING: 4, ROUTED: 100, EXCEPTION: 6 },
  latency: {
    QUEUED: { p50: 1, p95: 3 },
    ENCRYPTING: { p50: 0.5, p95: 1 },
    SCANNING: { p50: 2, p95: 5 },
    EXTRACTING: { p50: 10, p95: 20 },
    RESOLVING: { p50: 4, p95: 8 },
  },
}

beforeEach(() => vi.clearAllMocks())

describe('PipelineHealth', () => {
  it('shows dash placeholders for counts while loading', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<PipelineHealth />, { wrapper })
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('renders stage counts from data', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<PipelineHealth />, { wrapper })
    await waitFor(() => expect(screen.getByText('5')).toBeInTheDocument())
    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getByText('6')).toBeInTheDocument()
  })

  it('navigates to exceptions queue when clicking exception stage with count > 0', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    render(<PipelineHealth />, { wrapper })
    await waitFor(() => expect(screen.getByText('6')).toBeInTheDocument())
    const exceptionCard = screen.getByText('6').closest('button')!
    await user.click(exceptionCard)
    expect(mockNavigate).toHaveBeenCalledWith('/admin/exceptions')
  })

  it('renders per-stage latency p50/p95', async () => {
    mockGet.mockResolvedValue({ data: MOCK })
    render(<PipelineHealth />, { wrapper })
    await waitFor(() => expect(screen.getAllByText(/p50:/).length).toBeGreaterThan(0))
    expect(screen.getAllByText(/p95:/).length).toBeGreaterThan(0)
  })

  it('refetches when refresh button is clicked', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: MOCK })
    render(<PipelineHealth />, { wrapper })
    await waitFor(() => expect(screen.getByText('100')).toBeInTheDocument())
    mockGet.mockClear()
    await user.click(screen.getByRole('button', { name: /refresh/i }))
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/admin/pipeline-health'))
  })
})
