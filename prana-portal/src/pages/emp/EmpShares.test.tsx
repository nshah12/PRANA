import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { EmpShares } from './EmpShares'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockDelete = vi.mocked(api.delete)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

const ACTIVE_SHARE = {
  token_id: 's1', share_url: 'https://prana.in/share/s1', label: 'Salary slip for HDFC loan',
  expires_at: new Date(Date.now() + 3 * 3600000).toISOString(), created_at: '2024-01-01T00:00:00Z',
  view_count: 3, usage_limit: null, document_count: 1, is_active: true,
}
const EXPIRED_SHARE = {
  token_id: 's2', share_url: 'https://prana.in/share/s2', label: null,
  expires_at: new Date(Date.now() - 3600000).toISOString(), created_at: '2023-01-01T00:00:00Z',
  view_count: 1, usage_limit: null, document_count: 2, is_active: true,
}

beforeEach(() => vi.clearAllMocks())

describe('EmpShares', () => {
  it('shows a loading skeleton while shares are being fetched', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<EmpShares />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows an empty state when there are no shares', async () => {
    mockGet.mockResolvedValue({ data: { shares: [] } })
    render(<EmpShares />, { wrapper })
    expect(await screen.findByText('No share links yet')).toBeInTheDocument()
    expect(screen.getByText('Create one from your Vault to share documents securely.')).toBeInTheDocument()
  })

  it('renders summary cards and active/inactive sections', async () => {
    mockGet.mockResolvedValue({ data: { shares: [ACTIVE_SHARE, EXPIRED_SHARE] } })
    render(<EmpShares />, { wrapper })

    expect(await screen.findByText('Salary slip for HDFC loan')).toBeInTheDocument()
    expect(screen.getByText('Active links')).toBeInTheDocument()
    expect(screen.getByText('Total views')).toBeInTheDocument()
    expect(screen.getByText('Expired/Revoked')).toBeInTheDocument()
    expect(screen.getByText('Expired / Revoked')).toBeInTheDocument() // section heading for inactive group
  })

  it('shows the correct summary line with active/views/inactive counts', async () => {
    mockGet.mockResolvedValue({ data: { shares: [ACTIVE_SHARE, EXPIRED_SHARE] } })
    render(<EmpShares />, { wrapper })
    await screen.findByText('Salary slip for HDFC loan')
    expect(screen.getByText('1 active · 4 total views · 1 expired / revoked')).toBeInTheDocument()
  })

  it('opens the revoke confirmation modal and revokes the share', async () => {
    mockGet.mockResolvedValue({ data: { shares: [ACTIVE_SHARE] } })
    mockDelete.mockResolvedValue({ data: {} })
    const user = userEvent.setup()
    render(<EmpShares />, { wrapper })

    await screen.findByText('Salary slip for HDFC loan')
    // Trash icon button on the active share card
    const card = screen.getByText('Salary slip for HDFC loan').closest('div.bg-white')!
    const revokeIconBtn = card.querySelector('button')
    await user.click(revokeIconBtn!)

    expect(await screen.findByText('Revoke this link?')).toBeInTheDocument()
    expect(screen.getByText(/Salary slip for HDFC loan.*will stop working immediately\. This cannot be undone\./)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Revoke' }))
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/v1/vault/shares/s1'))
  })

  it('closes the revoke modal on Cancel without calling the API', async () => {
    mockGet.mockResolvedValue({ data: { shares: [ACTIVE_SHARE] } })
    const user = userEvent.setup()
    render(<EmpShares />, { wrapper })

    await screen.findByText('Salary slip for HDFC loan')
    const card = screen.getByText('Salary slip for HDFC loan').closest('div.bg-white')!
    await user.click(card.querySelector('button')!)
    await screen.findByText('Revoke this link?')

    await user.click(screen.getByText('Cancel'))
    expect(screen.queryByText('Revoke this link?')).not.toBeInTheDocument()
    expect(mockDelete).not.toHaveBeenCalled()
  })

  it('shows the expiry badge with hours remaining for a soon-to-expire share', async () => {
    mockGet.mockResolvedValue({ data: { shares: [ACTIVE_SHARE] } })
    render(<EmpShares />, { wrapper })
    expect(await screen.findByText(/Expires in \dh/)).toBeInTheDocument()
  })

  it('shows a "Revoked / expired" badge for an inactive/expired share', async () => {
    mockGet.mockResolvedValue({ data: { shares: [EXPIRED_SHARE] } })
    render(<EmpShares />, { wrapper })
    expect(await screen.findByText('Revoked / expired')).toBeInTheDocument()
  })

  it('opens the share link in a new tab via the Open link', async () => {
    mockGet.mockResolvedValue({ data: { shares: [ACTIVE_SHARE] } })
    render(<EmpShares />, { wrapper })
    await screen.findByText('Salary slip for HDFC loan')
    const openLink = screen.getByText('Open').closest('a')
    expect(openLink).toHaveAttribute('href', 'https://prana.in/share/s1')
    expect(openLink).toHaveAttribute('target', '_blank')
  })

  it('never renders a raw rupee figure or PAN-shaped value anywhere — privacy contract', async () => {
    mockGet.mockResolvedValue({ data: { shares: [ACTIVE_SHARE, EXPIRED_SHARE] } })
    render(<EmpShares />, { wrapper })
    await screen.findByText('Salary slip for HDFC loan')
    expect(document.body.textContent).not.toMatch(/₹\s*[\d,]+/)
    expect(document.body.textContent).not.toMatch(/[A-Z]{5}\d{4}[A-Z]/)
  })
})
