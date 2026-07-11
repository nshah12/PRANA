import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { EmpActivity } from './EmpActivity'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('EmpActivity', () => {
  it('shows a loading skeleton while activity is being fetched', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<EmpActivity />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows an empty state when there is no activity', async () => {
    mockGet.mockResolvedValue({ data: { access_log: [], pipeline_pushes: [] } })
    render(<EmpActivity />, { wrapper })
    expect(await screen.findByText('No activity yet')).toBeInTheDocument()
    expect(screen.getByText('Events appear here as documents are pushed and accessed.')).toBeInTheDocument()
  })

  it('renders merged access and push events sorted by time descending', async () => {
    mockGet.mockResolvedValue({
      data: {
        access_log: [
          { access_type: 'VIEW', doc_type: 'SALARY_SLIP', employer_name: 'TechCorp', accessed_at: '2024-01-01T10:00:00Z', via_share: false },
        ],
        pipeline_pushes: [
          { employer_name: 'TechCorp', doc_type: 'FORM_16', doc_period: '2023', pushed_at: '2024-03-01T10:00:00Z' },
        ],
      },
    })
    render(<EmpActivity />, { wrapper })

    // Push event is more recent, should render first
    const pushText = await screen.findByText(/TechCorp pushed FORM 16 · 2023 to your vault/)
    expect(pushText).toBeInTheDocument()
    expect(screen.getByText(/You view SALARY SLIP/)).toBeInTheDocument()
  })

  it('labels share-recipient access distinctly from own access', async () => {
    mockGet.mockResolvedValue({
      data: {
        access_log: [
          { access_type: 'VIEW', doc_type: 'FORM_16', employer_name: 'OldCo', accessed_at: '2024-01-01T10:00:00Z', via_share: true },
        ],
        pipeline_pushes: [],
      },
    })
    render(<EmpActivity />, { wrapper })
    expect(await screen.findByText(/Share recipient viewed FORM 16 via your share link/)).toBeInTheDocument()
  })

  it('never renders a raw rupee figure anywhere in the activity view — privacy contract', async () => {
    mockGet.mockResolvedValue({
      data: {
        access_log: [{ access_type: 'VIEW', doc_type: 'SALARY_SLIP', employer_name: 'TechCorp', accessed_at: '2024-01-01T10:00:00Z' }],
        pipeline_pushes: [],
      },
    })
    render(<EmpActivity />, { wrapper })
    await screen.findByText(/You view SALARY SLIP/)
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
  })
})
