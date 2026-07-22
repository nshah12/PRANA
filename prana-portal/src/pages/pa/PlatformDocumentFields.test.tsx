/**
 * PlatformDocumentFields tests
 *
 *  1. Loading state
 *  2. Error state with retry
 *  3. Empty state — no platform-default manifests configured
 *  4. Renders doc type list and the first doc type's fields, safe fields pre-checked
 *  5. Toggling a field and saving calls PUT with the full manifest + updated safe_fields
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { PlatformDocumentFields } from './PlatformDocumentFields'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), put: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPut = vi.mocked(api.put)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

function makeManifest(overrides: Partial<any> = {}) {
  return {
    manifest_id: 'm-1',
    doc_type: 'SALARY_SLIP',
    required_fields: ['designation'],
    identity_fields: ['employee_id'],
    optional_fields: ['leave_balance_days'],
    classification_signals: [],
    signal_weights: [],
    confidence_threshold: 0.75,
    supported_formats: ['pdf'],
    safe_fields: ['designation'],
    is_active: true,
    ...overrides,
  }
}

beforeEach(() => vi.clearAllMocks())

describe('PlatformDocumentFields', () => {
  it('shows a loading skeleton before data resolves', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    const { container } = render(<PlatformDocumentFields />, { wrapper })
    expect(container.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows an error state with a retry button on load failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<PlatformDocumentFields />, { wrapper })
    expect(await screen.findByText('Failed to load document field manifests.')).toBeInTheDocument()
    expect(screen.getByText('Retry')).toBeInTheDocument()
  })

  it('shows an empty state when no platform-default manifests are configured', async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0 } })
    render(<PlatformDocumentFields />, { wrapper })
    expect(await screen.findByText('No platform-default manifests configured yet.')).toBeInTheDocument()
  })

  it('renders the doc type list and pre-checks safe fields for the first doc type', async () => {
    mockGet.mockResolvedValue({ data: { items: [makeManifest()], total: 1 } })
    render(<PlatformDocumentFields />, { wrapper })

    expect(await screen.findByText('SALARY_SLIP')).toBeInTheDocument()
    await waitFor(() => {
      const designationToggle = screen.getByText('designation').closest('label')!.querySelector('div')!
      expect(designationToggle.className).toMatch(/bg-emerald-600/)
    })
    const leaveToggle = screen.getByText('leave_balance_days').closest('label')!.querySelector('div')!
    expect(leaveToggle.className).not.toMatch(/bg-emerald-600/)
  })

  it('toggling a field and saving calls PUT with the full manifest and updated safe_fields', async () => {
    mockGet.mockResolvedValue({ data: { items: [makeManifest()], total: 1 } })
    mockPut.mockResolvedValue({ data: {} })
    render(<PlatformDocumentFields />, { wrapper })
    await screen.findByText('leave_balance_days')

    const user = userEvent.setup()
    await user.click(screen.getByText('leave_balance_days'))
    await user.click(screen.getByRole('button', { name: /Save changes/ }))

    await waitFor(() => expect(mockPut).toHaveBeenCalledWith('/admin/manifests/SALARY_SLIP', expect.objectContaining({
      required_fields: ['designation'],
      identity_fields: ['employee_id'],
      optional_fields: ['leave_balance_days'],
      safe_fields: expect.arrayContaining(['designation', 'leave_balance_days']),
    })))
    expect(await screen.findByText('Saved')).toBeInTheDocument()
  })
})
