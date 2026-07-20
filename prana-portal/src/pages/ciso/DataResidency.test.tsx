/**
 * DataResidency tests
 *
 *  1. Renders default region cards (Mumbai primary, Hyderabad DR) when API returns no `regions`
 *  2. Renders region cards from API `regions` array when present
 *  3. Renders storage breakdown rows
 *  4. Renders the "stays within AWS India regions" compliance note always
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { DataResidency } from './DataResidency'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('DataResidency', () => {
  it('renders default region cards when API returns no regions array', async () => {
    mockGet.mockResolvedValue({ data: { primary_doc_count: 1000, dr_doc_count: 1000 } })
    render(<DataResidency />, { wrapper })
    // "Mumbai (Primary)" is a static label in the component's fallback array and
    // renders on the very first paint (before the query resolves, when doc_count
    // is still undefined) — waiting on it doesn't guarantee the query has settled.
    // Wait on the doc_count values themselves instead, since those only appear
    // once `data` has actually loaded.
    expect((await screen.findAllByText('1000')).length).toBe(2)
    expect(screen.getByText('Mumbai (Primary)')).toBeInTheDocument()
    expect(screen.getByText('Hyderabad (DR)')).toBeInTheDocument()
  })

  it('renders region cards from API regions array when present', async () => {
    mockGet.mockResolvedValue({
      data: {
        regions: [
          { region: 'ap-south-1', name: 'Mumbai (Primary)', role: 'PRIMARY', status: 'ACTIVE', doc_count: 5000 },
          { region: 'ap-south-2', name: 'Hyderabad (DR)', role: 'DR', status: 'ACTIVE', doc_count: 5000 },
        ],
      },
    })
    render(<DataResidency />, { wrapper })
    await waitFor(() => expect(screen.getAllByText('5000').length).toBe(2))
  })

  it('renders storage breakdown rows', async () => {
    mockGet.mockResolvedValue({ data: {} })
    render(<DataResidency />, { wrapper })
    await waitFor(() => expect(screen.getByText('YugabyteDB (encrypted at rest)')).toBeInTheDocument())
    expect(screen.getByText('S3 document bucket')).toBeInTheDocument()
    expect(screen.getByText('S3 staging bucket')).toBeInTheDocument()
    expect(screen.getByText('Audit cold storage (Iceberg)')).toBeInTheDocument()
  })

  it('always shows the AWS India regions compliance note', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<DataResidency />, { wrapper })
    expect(screen.getByText(/stays within AWS India regions/i)).toBeInTheDocument()
  })
})
