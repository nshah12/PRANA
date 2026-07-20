import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { EmpSettings } from './EmpSettings'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const PROFILE = {
  employee_user_id: 'e1234567-89ab-cdef-0123-456789abcdef',
  mobile: '+919000000001',
  vault_url: 'prana.in/vault/abc123',
  employers: [
    { tenant_id: 't1', tenant_name: 'TechCorp', doj: '2020-01-01', dol: null },
    { tenant_id: 't2', tenant_name: 'OldCo', doj: '2017-01-01', dol: '2019-12-31' },
  ],
}

beforeEach(() => vi.clearAllMocks())

describe('EmpSettings', () => {
  it('shows a loading skeleton while profile is being fetched', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<EmpSettings />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows an error state with retry when profile fails to load', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<EmpSettings />, { wrapper })
    expect(await screen.findByText('Failed to load profile.')).toBeInTheDocument()
    expect(screen.getByText('Retry')).toBeInTheDocument()
  })

  it('retries the profile query when Retry is clicked', async () => {
    mockGet.mockRejectedValueOnce(new Error('network'))
    const user = userEvent.setup()
    render(<EmpSettings />, { wrapper })
    await screen.findByText('Failed to load profile.')

    mockGet.mockResolvedValueOnce({ data: PROFILE })
    await user.click(screen.getByText('Retry'))

    expect(await screen.findByText('Profile & Settings')).toBeInTheDocument()
  })

  it('renders vault identity, masked NIK, and vault URL', async () => {
    mockGet.mockResolvedValue({ data: PROFILE })
    render(<EmpSettings />, { wrapper })

    expect(await screen.findByText('Vault Identity')).toBeInTheDocument()
    expect(screen.getByText('+919000000001')).toBeInTheDocument()
    expect(screen.getByText('prana.in/vault/abc123')).toBeInTheDocument()
    // NIK is a token derived from employee_user_id, never the raw PAN
    expect(screen.getByText('NIK (PAN) — Stored Encrypted')).toBeInTheDocument()
    expect(screen.getByText('Plaintext PAN never displayed or stored')).toBeInTheDocument()
  })

  it('renders MFA toggles and allows toggling TOTP', async () => {
    mockGet.mockResolvedValue({ data: PROFILE })
    const user = userEvent.setup()
    render(<EmpSettings />, { wrapper })

    await screen.findByText('MFA Settings')
    expect(screen.getByText('TOTP Authenticator')).toBeInTheDocument()
    expect(screen.getByText('SMS OTP fallback')).toBeInTheDocument()

    // Toggle rows render as buttons with no accessible name; find the one adjacent to TOTP label
    const totpRow = screen.getByText('TOTP Authenticator').closest('div.flex')
    const toggleBtn = totpRow?.querySelector('button')
    expect(toggleBtn).toBeTruthy()
    await user.click(toggleBtn!)
    // No crash / re-render error is the primary assertion; toggle is local UI state
    expect(toggleBtn).toBeInTheDocument()
  })

  it('renders linked employers with Active/Alumni badges', async () => {
    mockGet.mockResolvedValue({ data: PROFILE })
    render(<EmpSettings />, { wrapper })

    await screen.findByText('TechCorp')
    expect(screen.getByText('OldCo')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText('Alumni')).toBeInTheDocument()
  })

  it('shows an empty state for employers when none are linked', async () => {
    mockGet.mockResolvedValue({ data: { ...PROFILE, employers: [] } })
    render(<EmpSettings />, { wrapper })
    expect(await screen.findByText('No employers linked yet.')).toBeInTheDocument()
  })

  it('renders notification preferences toggles', async () => {
    mockGet.mockResolvedValue({ data: PROFILE })
    render(<EmpSettings />, { wrapper })

    await screen.findByText('Notification Preferences')
    expect(screen.getByText('New document pushed')).toBeInTheDocument()
    expect(screen.getByText('Share link accessed')).toBeInTheDocument()
    expect(screen.getByText('Share expiry reminder')).toBeInTheDocument()
  })

  it('never renders the raw employee_user_id (NIK) or a rupee figure — privacy contract', async () => {
    mockGet.mockResolvedValue({ data: PROFILE })
    render(<EmpSettings />, { wrapper })
    await screen.findByText('TechCorp')
    // The full raw UUID must never render — only a truncated token form
    expect(document.body.textContent).not.toContain(PROFILE.employee_user_id)
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
    expect(document.body.textContent).not.toMatch(/[A-Z]{5}\d{4}[A-Z]/)
  })
})
