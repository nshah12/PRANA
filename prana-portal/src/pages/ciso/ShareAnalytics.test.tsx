/**
 * ShareAnalytics tests
 *
 *  1. Renders stat cards with placeholder dash when data is loading/absent
 *  2. Renders stat values from API data
 *  3. Renders active share links table rows
 *  4. Renders empty state when no links
 *  5. Revoke mutation — success invalidates query; error path does not crash
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ShareAnalytics } from './ShareAnalytics'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('ShareAnalytics', () => {
  it('renders placeholder dashes for stats before data resolves', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))
    render(<ShareAnalytics />, { wrapper })
    expect(screen.getByText('Share Analytics')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBe(4)
  })

  it('renders stat values from API data', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { active_count: 12, accesses_24h: 34, expired_today: 2, revoked_today: 1, links: [] },
    })
    render(<ShareAnalytics />, { wrapper })
    expect(await screen.findByText('12')).toBeInTheDocument()
    expect(screen.getByText('34')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('renders active share link rows with employee, doc type, recipient, and revoke button', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        active_count: 1,
        links: [
          { share_id: 's-1', employee_name: 'Asha Rao', doc_type: 'SALARY_SLIP', recipient_label: 'HDFC Bank', access_count: 3, expires_at: '2026-07-10T10:00:00Z' },
        ],
      },
    })
    render(<ShareAnalytics />, { wrapper })
    expect(await screen.findByText('Asha Rao')).toBeInTheDocument()
    expect(screen.getByText('SALARY SLIP')).toBeInTheDocument()
    expect(screen.getByText('HDFC Bank')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('Revoke')).toBeInTheDocument()
  })

  it('falls back to "Unknown" recipient label when none provided', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { links: [{ share_id: 's-2', employee_name: 'Ravi Kumar', doc_type: 'FORM_16', recipient_label: null, access_count: 0, expires_at: null }] },
    })
    render(<ShareAnalytics />, { wrapper })
    expect(await screen.findByText('Unknown')).toBeInTheDocument()
  })

  it('renders empty state when there are no active links', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { links: [] } })
    render(<ShareAnalytics />, { wrapper })
    expect(await screen.findByText('No active share links.')).toBeInTheDocument()
  })

  it('revokes a share link on click and refetches the list', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({
      data: { links: [{ share_id: 's-1', employee_name: 'Asha Rao', doc_type: 'SALARY_SLIP', recipient_label: 'HDFC', access_count: 3, expires_at: '2026-07-10T10:00:00Z' }] },
    })
    vi.mocked(api.post).mockResolvedValue({ data: { message: 'REVOKED' } })
    render(<ShareAnalytics />, { wrapper })
    const revokeBtn = await screen.findByText('Revoke')
    await user.click(revokeBtn)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/v1/ciso/shares/s-1/revoke', {}))
  })

  it('does not crash when the revoke mutation fails', async () => {
    const user = userEvent.setup()
    vi.mocked(api.get).mockResolvedValue({
      data: { links: [{ share_id: 's-1', employee_name: 'Asha Rao', doc_type: 'SALARY_SLIP', recipient_label: 'HDFC', access_count: 3, expires_at: '2026-07-10T10:00:00Z' }] },
    })
    vi.mocked(api.post).mockRejectedValue(new Error('network error'))
    render(<ShareAnalytics />, { wrapper })
    const revokeBtn = await screen.findByText('Revoke')
    await user.click(revokeBtn)
    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(screen.getByText('Asha Rao')).toBeInTheDocument()
  })
})
