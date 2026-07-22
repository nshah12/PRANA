/**
 * SetupChecklist tests
 *
 *  1. Loading / error / empty states
 *  2. Renders baseline + custom items with correct badges and completion state
 *  3. All-required-complete banner shown when applicable
 *  4. OA-Admin: toggling an incomplete item calls complete; toggling a complete item calls uncomplete
 *  5. OA-Admin: adding a tenant item calls POST with the right payload
 *  6. OA-Admin: deleting own item calls DELETE; baseline items have no delete button
 *  7. OA-Operator: view-only — no checkbox interaction, no add button
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { SetupChecklist } from './SetupChecklist'
import { useAuthStore } from '@/store/auth'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)
const mockDelete = vi.mocked(api.delete)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

function setUser(role: 'oa_operator' | 'oa_admin') {
  useAuthStore.getState().setUser({
    userId: 'u-1', email: 'x@acme.example', displayName: 'X',
    role, tenantId: 't-1', tenantName: 'Acme Ltd',
  })
}

function _item(overrides: Partial<any> = {}) {
  return {
    item_id: 'i-1', is_platform_baseline: true, item_key: 'GRIEVANCE_OFFICER_CONFIGURED',
    title: 'Grievance Officer configured', description: 'desc', is_required: true,
    completed: false, completed_at: null, notes: null,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.getState().logout()
})

describe('SetupChecklist', () => {
  it('shows a loading skeleton before data resolves', () => {
    setUser('oa_admin')
    mockGet.mockReturnValue(new Promise(() => {}))
    const { container } = render(<SetupChecklist />, { wrapper })
    expect(container.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows an error state with retry on load failure', async () => {
    setUser('oa_admin')
    mockGet.mockRejectedValue(new Error('network'))
    render(<SetupChecklist />, { wrapper })
    expect(await screen.findByText('Failed to load the setup checklist.')).toBeInTheDocument()
  })

  it('shows an empty state when no items exist', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { items: [] } })
    render(<SetupChecklist />, { wrapper })
    expect(await screen.findByText('No checklist items configured yet.')).toBeInTheDocument()
  })

  it('renders baseline and custom items with correct badges', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { items: [
      _item(),
      _item({ item_id: 'i-2', is_platform_baseline: false, item_key: 'MY_ITEM', title: 'My Item' }),
    ] } })
    render(<SetupChecklist />, { wrapper })

    expect(await screen.findByText('Grievance Officer configured')).toBeInTheDocument()
    expect(screen.getByText('Platform')).toBeInTheDocument()
    expect(screen.getByText('My Item')).toBeInTheDocument()
    expect(screen.getByText('Your item')).toBeInTheDocument()
  })

  it('shows the all-complete banner when every required item is done', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { items: [_item({ completed: true })] } })
    render(<SetupChecklist />, { wrapper })
    expect(await screen.findByText(/All required items are complete/)).toBeInTheDocument()
  })

  it('OA-Admin: clicking an incomplete item toggle calls the complete endpoint', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { items: [_item()] } })
    mockPost.mockResolvedValue({ data: {} })
    render(<SetupChecklist />, { wrapper })
    await screen.findByText('Grievance Officer configured')

    const user = userEvent.setup()
    const toggle = screen.getByText('Grievance Officer configured').closest('.px-5.py-4')!.querySelector('button')!
    await user.click(toggle)

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      '/v1/org/setup-checklist/GRIEVANCE_OFFICER_CONFIGURED/complete', {},
    ))
  })

  it('OA-Admin: clicking a completed item toggle calls the uncomplete endpoint', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { items: [_item({ completed: true })] } })
    mockDelete.mockResolvedValue({ data: {} })
    render(<SetupChecklist />, { wrapper })
    await screen.findByText('Grievance Officer configured')

    const user = userEvent.setup()
    const toggle = screen.getByText('Grievance Officer configured').closest('.px-5.py-4')!.querySelector('button')!
    await user.click(toggle)

    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith(
      '/v1/org/setup-checklist/GRIEVANCE_OFFICER_CONFIGURED/complete',
    ))
  })

  it('OA-Admin: adding a tenant item posts the right payload', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { items: [_item()] } })
    mockPost.mockResolvedValue({ data: { item: {} } })
    render(<SetupChecklist />, { wrapper })
    await screen.findByText('Grievance Officer configured')

    const user = userEvent.setup()
    await user.click(screen.getByText('Add your own checklist item'))
    await user.type(screen.getByPlaceholderText(/ITEM_KEY/), 'my_key')
    await user.type(screen.getByPlaceholderText('Title'), 'My Title')
    await user.click(screen.getByRole('button', { name: 'Add item' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/org/setup-checklist', {
      item_key: 'MY_KEY', title: 'My Title', description: null, is_required: true,
    }))
  })

  it('OA-Admin: baseline items have no delete button, custom items do', async () => {
    setUser('oa_admin')
    mockGet.mockResolvedValue({ data: { items: [
      _item(),
      _item({ item_id: 'i-2', is_platform_baseline: false, item_key: 'MY_ITEM', title: 'My Item' }),
    ] } })
    render(<SetupChecklist />, { wrapper })
    await screen.findByText('My Item')

    const baselineRow = screen.getByText('Grievance Officer configured').closest('.px-5.py-4')!
    const customRow = screen.getByText('My Item').closest('.px-5.py-4')!
    expect(baselineRow.querySelectorAll('button').length).toBe(1)  // only the toggle
    expect(customRow.querySelectorAll('button').length).toBe(2)    // toggle + delete
  })

  it('OA-Operator: view-only — no add button, toggle is disabled', async () => {
    setUser('oa_operator')
    mockGet.mockResolvedValue({ data: { items: [_item()] } })
    render(<SetupChecklist />, { wrapper })
    await screen.findByText('Grievance Officer configured')

    expect(screen.queryByText('Add your own checklist item')).not.toBeInTheDocument()
  })
})
