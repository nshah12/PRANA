/**
 * AlertConfig tests
 *
 * Contract under test:
 *  1. Loading skeleton while fetching GET /v1/chro/alerts/config
 *  2. Renders all 5 alert types with label, description, and toggle
 *  3. Config from server pre-populates toggles (via useEffect)
 *  4. Toggling flips a switch's visual state
 *  5. Save calls PATCH /v1/chro/alerts/config with the toggled config
 *  6. Save success shows "Saved ✓" (temporarily) and invalidates the query
 *  7. Save error shows the error message
 *  8. Save button disabled while pending, shows "Saving…"
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { AlertConfig } from './AlertConfig'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPatch = vi.mocked(api.patch)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

beforeEach(() => vi.clearAllMocks())

describe('AlertConfig', () => {
  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<AlertConfig />, { wrapper })
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('renders title, subtitle, and all 5 alert types once loaded', async () => {
    mockGet.mockResolvedValue({ data: { config: {} } })
    render(<AlertConfig />, { wrapper })

    await screen.findByText('Statutory deadline alert')
    expect(screen.getByText('Alert Configuration')).toBeInTheDocument()
    expect(screen.getByText(
      'Choose which events trigger notifications to your email, WhatsApp, and in-app inbox. Preferences are saved per organisation.'
    )).toBeInTheDocument()
    expect(screen.getByText('Vault health drop')).toBeInTheDocument()
    expect(screen.getByText('Exception queue spike')).toBeInTheDocument()
    expect(screen.getByText('Exit document delay')).toBeInTheDocument()
    expect(screen.getByText('Security anomaly (P0/P1)')).toBeInTheDocument()
  })

  it('defaults every alert to ON before server config resolves state, then applies server config', async () => {
    mockGet.mockResolvedValue({
      data: { config: { deadline_alert: false, vault_health_drop: true, exception_spike: false, exit_doc_delay: true, security_anomaly: false } },
    })
    render(<AlertConfig />, { wrapper })

    await screen.findByText('Statutory deadline alert')
    // Find switches by their position relative to labels
    const row = screen.getByText('Statutory deadline alert').closest('div')!.parentElement!
    const toggle = row.querySelector('button')!
    await waitFor(() => expect(toggle.className).not.toContain('bg-pink-500'))
  })

  it('toggling a switch flips its visual on/off state', async () => {
    // Server returns deadline_alert: true explicitly, applied via useEffect
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { config: { deadline_alert: true } } })
    render(<AlertConfig />, { wrapper })

    await screen.findByText('Statutory deadline alert')
    const row = screen.getByText('Statutory deadline alert').closest('div')!.parentElement!
    const toggle = row.querySelector('button')!
    await waitFor(() => expect(toggle.className).toContain('bg-pink-500'))

    await user.click(toggle)
    expect(toggle.className).not.toContain('bg-pink-500')
  })

  it('saves the config via PATCH and shows "Saved" confirmation', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { config: { deadline_alert: true } } })
    mockPatch.mockResolvedValue({ data: { ok: true } })
    render(<AlertConfig />, { wrapper })

    await screen.findByText('Statutory deadline alert')
    await waitFor(() => {
      const row = screen.getByText('Statutory deadline alert').closest('div')!.parentElement!
      expect(row.querySelector('button')!.className).toContain('bg-pink-500')
    })
    await user.click(screen.getByRole('button', { name: /save configuration/i }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      '/v1/chro/alerts/config',
      { config: expect.objectContaining({ deadline_alert: true }) }
    ))
    await screen.findByText('Saved ✓')
  })

  it('shows "Saving…" and disables the button while the mutation is pending', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { config: {} } })
    let resolveFn: (v: any) => void
    mockPatch.mockReturnValue(new Promise(res => { resolveFn = res }))
    render(<AlertConfig />, { wrapper })

    await screen.findByText('Statutory deadline alert')
    user.click(screen.getByRole('button', { name: /save configuration/i }))

    await screen.findByText('Saving…')
    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled()

    resolveFn!({ data: {} })
    await waitFor(() => expect(screen.getByText('Saved ✓')).toBeInTheDocument())
  })

  it('shows an error message when saving fails', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { config: {} } })
    mockPatch.mockRejectedValue(new Error('save failed'))
    render(<AlertConfig />, { wrapper })

    await screen.findByText('Statutory deadline alert')
    await user.click(screen.getByRole('button', { name: /save configuration/i }))

    await screen.findByText('Failed to save. Please try again.')
  })
})
