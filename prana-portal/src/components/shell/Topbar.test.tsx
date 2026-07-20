/**
 * Topbar tests
 *
 * Contract under test (from src/components/shell/Topbar.tsx):
 *  1. Renders nothing when there is no logged-in user
 *  2. Renders brand, avatar initials, display name, and role label for a logged-in user
 *  3. Clicking the profile chip opens the dropdown menu; clicking again closes it
 *  4. Dropdown shows role-specific menu items (different per role) that navigate on click
 *  5. Dropdown shows tenant name section when user.tenantName is set
 *  6. Clicking "Sign out" calls the org logout endpoint, clears the store, and navigates to /org/login
 *  7. portal_admin role calls the admin logout endpoint and navigates to /admin/login
 *  8. Clicking outside the menu closes it
 *
 * Used in src/App.tsx PortalLayout as: <Topbar /> — no props, reads useAuthStore directly.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAuthStore, type AuthUser } from '@/store/auth'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...(actual as any), useNavigate: () => mockNavigate }
})

import { Topbar } from './Topbar'

const oaOperatorUser: AuthUser = {
  userId: 'u-1',
  email: 'operator@acme.example',
  displayName: 'Priya Sharma',
  role: 'oa_operator',
  tenantId: 't-1',
  tenantName: 'Acme Corp',
}

const portalAdminUser: AuthUser = {
  userId: 'u-2',
  email: 'admin@prana.in',
  displayName: 'Rahul Verma',
  role: 'portal_admin',
  tenantId: null,
  tenantName: null,
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: null, accessToken: null, stepToken: null, requiresTotpSetup: false })
})

describe('Topbar — no user', () => {
  it('renders nothing when there is no logged-in user', () => {
    const { container } = render(<Topbar />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('Topbar — logged-in oa_operator', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: oaOperatorUser })
  })

  it('renders brand, initials, name and role label', () => {
    render(<Topbar />)
    expect(screen.getByText('prana.')).toBeInTheDocument()
    expect(screen.getByText('PS')).toBeInTheDocument() // initials from "Priya Sharma"
    expect(screen.getByText('Priya Sharma')).toBeInTheDocument()
    expect(screen.getByText('OA-Operator')).toBeInTheDocument()
  })

  it('opens the dropdown on click and shows role-specific menu items + tenant name', async () => {
    const user = userEvent.setup()
    render(<Topbar />)

    expect(screen.queryByText('My profile')).not.toBeInTheDocument()
    await user.click(screen.getByText('Priya Sharma'))

    expect(screen.getByText('My profile')).toBeInTheDocument()
    expect(screen.getByText('Org settings')).toBeInTheDocument()
    // oa_operator menu must NOT include "User management" (that's oa_admin only)
    expect(screen.queryByText('User management')).not.toBeInTheDocument()

    expect(screen.getByText('Organisation')).toBeInTheDocument()
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
  })

  it('closes the dropdown when the profile chip is clicked again', async () => {
    const user = userEvent.setup()
    render(<Topbar />)

    const chip = screen.getAllByText('Priya Sharma')[0]
    await user.click(chip)
    expect(screen.getByText('My profile')).toBeInTheDocument()

    await user.click(chip)
    expect(screen.queryByText('My profile')).not.toBeInTheDocument()
  })

  it('navigates to the menu item path and closes the dropdown on click', async () => {
    const user = userEvent.setup()
    render(<Topbar />)

    await user.click(screen.getByText('Priya Sharma'))
    await user.click(screen.getByText('Org settings'))

    expect(mockNavigate).toHaveBeenCalledWith('/org/settings')
    expect(screen.queryByText('My profile')).not.toBeInTheDocument()
  })

  it('signs out via the org logout endpoint and navigates to /org/login', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: {} })
    const user = userEvent.setup()
    render(<Topbar />)

    await user.click(screen.getByText('Priya Sharma'))
    await user.click(screen.getByText('Sign out'))

    expect(api.post).toHaveBeenCalledWith('/auth/org/logout')
    expect(useAuthStore.getState().user).toBeNull()
    expect(mockNavigate).toHaveBeenCalledWith('/org/login')
  })

  it('closes the dropdown when clicking outside', async () => {
    const user = userEvent.setup()
    render(
      <div>
        <div data-testid="outside">Outside area</div>
        <Topbar />
      </div>,
    )

    await user.click(screen.getByText('Priya Sharma'))
    expect(screen.getByText('My profile')).toBeInTheDocument()

    await user.click(screen.getByTestId('outside'))
    expect(screen.queryByText('My profile')).not.toBeInTheDocument()
  })
})

describe('Topbar — logged-in portal_admin', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: portalAdminUser })
  })

  it('shows portal_admin specific menu items and no tenant section', async () => {
    const user = userEvent.setup()
    render(<Topbar />)

    expect(screen.getByText('RV')).toBeInTheDocument() // initials from "Rahul Verma"
    expect(screen.getByText('Portal Admin')).toBeInTheDocument()

    await user.click(screen.getByText('Rahul Verma'))
    expect(screen.getByText('Platform config')).toBeInTheDocument()
    expect(screen.getByText('Tenant directory')).toBeInTheDocument()
    expect(screen.queryByText('Organisation')).not.toBeInTheDocument()
  })

  it('signs out via the admin logout endpoint and navigates to /admin/login', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: {} })
    const user = userEvent.setup()
    render(<Topbar />)

    await user.click(screen.getByText('Rahul Verma'))
    await user.click(screen.getByText('Sign out'))

    expect(api.post).toHaveBeenCalledWith('/auth/admin/logout')
    expect(mockNavigate).toHaveBeenCalledWith('/admin/login')
  })
})
