/**
 * UserManagement tests
 *
 *  1. Loading state
 *  2. Error state — shows load-failed message (RED: source had no isError handling; fixed to add it)
 *  3. Empty state — no users found (RED: source had no empty-state handling; fixed to add it)
 *  4. Renders user rows with role select and status badge
 *  5. Changing role calls PATCH role mutation
 *  6. Deactivate: confirms, calls DELETE, only shown for ACTIVE users
 *  7. MIN_ADMIN_CONSTRAINT error on deactivate shows alert
 *  8. Invite user modal: opens, submits, closes on success
 *  9. Invite user modal: shows API error message on failure
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { UserManagement } from './UserManagement'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
import { api } from '@/lib/api'
const mockGet = vi.mocked(api.get)
const mockPost = vi.mocked(api.post)
const mockPatch = vi.mocked(api.patch)
const mockDelete = vi.mocked(api.delete)

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>
}

function makeUsers(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    oa_user_id: `u-${i}`,
    display_name: `User ${i}`,
    email: `user${i}@acme.in`,
    role: 'oa_operator',
    status: 'ACTIVE',
    created_at: '2024-01-01T00:00:00Z',
  }))
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.restoreAllMocks())

describe('UserManagement', () => {
  it('shows loading state while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<UserManagement />, { wrapper })
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows error state when users fail to load', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    render(<UserManagement />, { wrapper })
    expect(await screen.findByText('Failed to load users.')).toBeInTheDocument()
  })

  it('shows empty state when there are no users', async () => {
    mockGet.mockResolvedValue({ data: { users: [] } })
    render(<UserManagement />, { wrapper })
    expect(await screen.findByText('No users found.')).toBeInTheDocument()
  })

  it('renders user rows with role select and status badge', async () => {
    mockGet.mockResolvedValue({ data: { users: makeUsers(2) } })
    render(<UserManagement />, { wrapper })
    expect(await screen.findByText('User 0')).toBeInTheDocument()
    expect(screen.getByText('user0@acme.in')).toBeInTheDocument()
    expect(screen.getAllByText('ACTIVE').length).toBe(2)
    const roleSelects = screen.getAllByRole('combobox')
    expect((roleSelects[0] as HTMLSelectElement).value).toBe('oa_operator')
  })

  it('changing the role select calls the role-change mutation', async () => {
    mockGet.mockResolvedValue({ data: { users: makeUsers(1) } })
    mockPatch.mockResolvedValue({ data: {} })
    render(<UserManagement />, { wrapper })
    await screen.findByText('User 0')

    const user = userEvent.setup()
    await user.selectOptions(screen.getByRole('combobox'), 'oa_admin')

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/v1/org/users/u-0/role', { role: 'oa_admin' }))
  })

  it('deactivate: confirms, calls DELETE, and is only shown for ACTIVE users', async () => {
    mockGet.mockResolvedValue({
      data: { users: [makeUsers(1)[0], { ...makeUsers(1)[0], oa_user_id: 'u-9', status: 'INACTIVE', display_name: 'Inactive Guy' }] },
    })
    mockDelete.mockResolvedValue({ data: {} })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<UserManagement />, { wrapper })

    await screen.findByText('User 0')
    expect(screen.getAllByRole('button', { name: /Deactivate/ }).length).toBe(1)

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Deactivate/ }))

    expect(confirmSpy).toHaveBeenCalledWith('Deactivate User 0?')
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/v1/org/users/u-0'))
  })

  it('shows the min-admin alert when deactivation is blocked', async () => {
    mockGet.mockResolvedValue({ data: { users: makeUsers(1) } })
    mockDelete.mockRejectedValue({ response: { data: { detail: 'MIN_ADMIN_CONSTRAINT' } } })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
    render(<UserManagement />, { wrapper })

    await screen.findByText('User 0')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Deactivate/ }))

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith(
      'Cannot deactivate — this would leave no OA-Admin in the organisation.',
    ))
  })

  it('opens the invite-user modal, submits, and closes on success', async () => {
    mockGet.mockResolvedValue({ data: { users: [] } })
    mockPost.mockResolvedValue({ data: {} })
    render(<UserManagement />, { wrapper })
    await screen.findByText('No users found.')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Invite user/ }))
    expect(screen.getByText('User Management')).toBeInTheDocument() // sanity: page still rendered
    expect(screen.getAllByText('Invite user').length).toBeGreaterThan(0)

    const dialog = screen.getByText('Full name').closest('form') as HTMLElement
    await user.type(dialog.querySelector('input') as HTMLInputElement, 'Neha Kapoor')
    const emailInput = screen.getByText('Work email').parentElement!.querySelector('input') as HTMLInputElement
    await user.type(emailInput, 'neha@acme.in')

    await user.click(screen.getByRole('button', { name: 'Invite' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/org/users', {
      display_name: 'Neha Kapoor', email: 'neha@acme.in', role: 'oa_operator',
    }))
    // modal closes — form fields no longer present
    expect(screen.queryByText('Full name')).not.toBeInTheDocument()
  })

  it('shows an error message inside the modal when invite fails', async () => {
    mockGet.mockResolvedValue({ data: { users: [] } })
    mockPost.mockRejectedValue({ response: { data: { detail: 'Email already in use' } } })
    render(<UserManagement />, { wrapper })
    await screen.findByText('No users found.')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Invite user/ }))
    const dialog = screen.getByText('Full name').closest('form') as HTMLElement
    await user.type(dialog.querySelector('input') as HTMLInputElement, 'Neha Kapoor')
    const emailInput = screen.getByText('Work email').parentElement!.querySelector('input') as HTMLInputElement
    await user.type(emailInput, 'neha@acme.in')
    await user.click(screen.getByRole('button', { name: 'Invite' }))

    expect(await screen.findByText('Email already in use')).toBeInTheDocument()
  })

  // -- Resend welcome email -------------------------------------------------------

  it('shows a "Resend welcome email" action for every user regardless of status', async () => {
    mockGet.mockResolvedValue({ data: { users: makeUsers(2) } })
    render(<UserManagement />, { wrapper })
    await screen.findByText('User 0')
    expect(screen.getAllByText('Resend welcome email').length).toBe(2)
  })

  it('resending posts to the resend-welcome endpoint and shows the success message', async () => {
    mockGet.mockResolvedValue({ data: { users: makeUsers(1) } })
    mockPost.mockResolvedValue({ data: { message: 'OA_WELCOME_EMAIL_RESENT' } })
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
    const user = userEvent.setup()
    render(<UserManagement />, { wrapper })

    await screen.findByText('User 0')
    await user.click(screen.getByText('Resend welcome email'))

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/v1/org/users/u-0/resend-welcome'))
    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith('Welcome email resent.'))
  })

  it('shows the mapped error message when resend fails', async () => {
    mockGet.mockResolvedValue({ data: { users: makeUsers(1) } })
    mockPost.mockRejectedValue({ response: { data: { detail: 'USER_NOT_FOUND' } } })
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
    const user = userEvent.setup()
    render(<UserManagement />, { wrapper })

    await screen.findByText('User 0')
    await user.click(screen.getByText('Resend welcome email'))

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith('No account found with these details.'))
  })
})
