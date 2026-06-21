/**
 * DigestSettings tests — TDD RED → GREEN → REFACTOR
 *
 *  1. Shows "not available" for non-digest roles (oa_operator, oa_admin)
 *  2. Shows loading skeleton while fetching
 *  3. Shows error message on API failure
 *  4. Renders recipient input for CHRO role
 *  5. Renders schedule toggles (weekly, monthly, quarterly)
 *  6. Renders sections checkboxes (role-specific)
 *  7. Renders format radio buttons (email / email_pdf)
 *  8. Save button is present
 *  9. Role badge shows correct role label
 * 10. API endpoint is role-appropriate (/v1/chro/digest/settings)
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { DigestSettings } from './DigestSettings'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), put: vi.fn() } }))
vi.mock('@/store/auth', () => ({
  useAuthStore: vi.fn(),
}))

import { api } from '@/lib/api'
import { useAuthStore } from '@/store/auth'

const mockGet = vi.mocked(api.get)
const mockUseAuthStore = vi.mocked(useAuthStore)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const MOCK_SETTINGS = {
  digest_settings: {
    recipients: ['hr@acme.com'],
    schedules: {
      weekly:    { enabled: true,  day: 'MON', time: '08:00' },
      monthly:   { enabled: false, day_of_month: 1, time: '08:00' },
      quarterly: { enabled: false, time: '08:00' },
    },
    sections: [],
    format: 'email',
    active: true,
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  // Default: CHRO role
  mockUseAuthStore.mockImplementation((selector: any) =>
    selector({ user: { role: 'chro' } })
  )
})

describe('DigestSettings', () => {
  it('shows role-restricted message for oa_operator', () => {
    mockUseAuthStore.mockImplementation((selector: any) =>
      selector({ user: { role: 'oa_operator' } })
    )
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<DigestSettings />, { wrapper })
    expect(screen.getByText(/only available for chro/i)).toBeInTheDocument()
  })

  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<DigestSettings />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows error message on API failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<DigestSettings />, { wrapper })
    await waitFor(() =>
      expect(screen.getByText(/failed to load digest settings/i)).toBeInTheDocument()
    )
  })

  it('renders recipient input section', async () => {
    mockGet.mockResolvedValue({ data: MOCK_SETTINGS })
    render(<DigestSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText(/recipients/i)).toBeInTheDocument())
    expect(screen.getByPlaceholderText(/add recipient email/i)).toBeInTheDocument()
  })

  it('renders schedule toggles for all 3 periods', async () => {
    mockGet.mockResolvedValue({ data: MOCK_SETTINGS })
    render(<DigestSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText(/delivery schedule/i)).toBeInTheDocument())
    expect(screen.getByText(/weekly/i)).toBeInTheDocument()
    expect(screen.getByText(/monthly/i)).toBeInTheDocument()
    expect(screen.getByText(/quarterly/i)).toBeInTheDocument()
  })

  it('renders content section checkboxes for CHRO role', async () => {
    mockGet.mockResolvedValue({ data: MOCK_SETTINGS })
    render(<DigestSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText(/vault completeness score/i)).toBeInTheDocument())
    expect(screen.getByText(/documents processed/i)).toBeInTheDocument()
    expect(screen.getByText(/open exceptions/i)).toBeInTheDocument()
  })

  it('renders delivery format radio buttons', async () => {
    mockGet.mockResolvedValue({ data: MOCK_SETTINGS })
    render(<DigestSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText(/email only/i)).toBeInTheDocument())
    expect(screen.getByText(/email \+ pdf attachment/i)).toBeInTheDocument()
  })

  it('renders save button', async () => {
    mockGet.mockResolvedValue({ data: MOCK_SETTINGS })
    render(<DigestSettings />, { wrapper })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument()
    )
  })

  it('shows CHRO role badge', async () => {
    mockGet.mockResolvedValue({ data: MOCK_SETTINGS })
    render(<DigestSettings />, { wrapper })
    // Badge text is exactly "CHRO digest" — use exact match to avoid collision with subtitle
    await waitFor(() => expect(screen.getByText('CHRO digest')).toBeInTheDocument())
  })

  it('calls CHRO-specific API endpoint', async () => {
    mockGet.mockResolvedValue({ data: MOCK_SETTINGS })
    render(<DigestSettings />, { wrapper })
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    const url: string = mockGet.mock.calls[0][0]
    expect(url).toBe('/v1/chro/digest/settings')
  })

  it('calls CFO-specific API endpoint when role is cfo', async () => {
    mockUseAuthStore.mockImplementation((selector: any) =>
      selector({ user: { role: 'cfo' } })
    )
    mockGet.mockResolvedValue({ data: MOCK_SETTINGS })
    render(<DigestSettings />, { wrapper })
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    const url: string = mockGet.mock.calls[0][0]
    expect(url).toBe('/v1/cfo/digest/settings')
  })

  it('renders CFO-specific sections when role is cfo', async () => {
    mockUseAuthStore.mockImplementation((selector: any) =>
      selector({ user: { role: 'cfo' } })
    )
    mockGet.mockResolvedValue({ data: MOCK_SETTINGS })
    render(<DigestSettings />, { wrapper })
    await waitFor(() => expect(screen.getByText(/headcount vs budget/i)).toBeInTheDocument())
    expect(screen.getByText(/exits & joiners/i)).toBeInTheDocument()
  })
})
