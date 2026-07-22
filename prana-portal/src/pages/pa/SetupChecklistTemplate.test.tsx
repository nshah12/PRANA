/**
 * SetupChecklistTemplate tests
 *
 *  1. Loading / error / empty states
 *  2. Renders baseline items with required/inactive badges
 *  3. Adding a new baseline item posts the right payload
 *  4. Editing an item calls PATCH with the updated fields
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { SetupChecklistTemplate } from './SetupChecklistTemplate'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)
const mockPatch = vi.mocked(api.patch)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

function _item(overrides: Partial<any> = {}) {
  return {
    item_id: 'i-1', item_key: 'GRIEVANCE_OFFICER_CONFIGURED', title: 'Grievance Officer configured',
    description: 'desc', display_order: 10, is_active: true, is_required: true,
    ...overrides,
  }
}

beforeEach(() => vi.clearAllMocks())

describe('SetupChecklistTemplate', () => {
  it('shows a loading skeleton before data resolves', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    const { container } = render(<SetupChecklistTemplate />, { wrapper })
    expect(container.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('shows an error state with retry on load failure', async () => {
    mockGet.mockRejectedValue(new Error('network'))
    render(<SetupChecklistTemplate />, { wrapper })
    expect(await screen.findByText('Failed to load the setup checklist template.')).toBeInTheDocument()
  })

  it('shows an empty state when no baseline items exist', async () => {
    mockGet.mockResolvedValue({ data: { items: [] } })
    render(<SetupChecklistTemplate />, { wrapper })
    expect(await screen.findByText('No platform-baseline checklist items configured yet.')).toBeInTheDocument()
  })

  it('renders baseline items with key and inactive badge', async () => {
    mockGet.mockResolvedValue({ data: { items: [_item({ is_active: false })] } })
    render(<SetupChecklistTemplate />, { wrapper })
    expect(await screen.findByText('Grievance Officer configured')).toBeInTheDocument()
    expect(screen.getByText('GRIEVANCE_OFFICER_CONFIGURED')).toBeInTheDocument()
    expect(screen.getByText('Inactive')).toBeInTheDocument()
  })

  it('adds a new baseline item with the right payload', async () => {
    mockGet.mockResolvedValue({ data: { items: [] } })
    mockPost.mockResolvedValue({ data: { item: {} } })
    render(<SetupChecklistTemplate />, { wrapper })
    await screen.findByText('No platform-baseline checklist items configured yet.')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Add baseline item/ }))
    await user.type(screen.getByPlaceholderText(/ITEM_KEY/), 'new_key')
    await user.type(screen.getByPlaceholderText('Title'), 'New Item')
    await user.click(screen.getByRole('button', { name: 'Create Rule' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/admin/setup-checklist', {
      item_key: 'NEW_KEY', title: 'New Item', description: null, is_required: true, display_order: 0,
    }))
  })

  it('editing an item calls PATCH with the updated fields', async () => {
    mockGet.mockResolvedValue({ data: { items: [_item()] } })
    mockPatch.mockResolvedValue({ data: { item: {} } })
    render(<SetupChecklistTemplate />, { wrapper })
    await screen.findByText('Grievance Officer configured')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Edit/ }))
    const titleInput = screen.getByDisplayValue('Grievance Officer configured')
    await user.clear(titleInput)
    await user.type(titleInput, 'Updated Title')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/admin/setup-checklist/i-1', expect.objectContaining({
      title: 'Updated Title',
    })))
  })
})
