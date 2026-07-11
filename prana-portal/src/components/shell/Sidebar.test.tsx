/**
 * Sidebar tests
 *
 * Contract under test (from src/components/shell/Sidebar.tsx):
 *  1. Renders nothing when there is no logged-in user
 *  2. Renders role-specific nav items — different sets for oa_operator vs oa_admin vs portal_admin
 *  3. Base path is /org for normal roles, /admin for portal_admin
 *  4. Renders tenant name block when user.tenantName is set, omits it otherwise (portal_admin has no tenant)
 *  5. portal_admin nav is grouped into labelled, collapsible sections; clicking a group header
 *     toggles its visibility
 *  6. Badge counts render for oa_admin (exceptions/elevations) once the sidebar-badges query resolves
 *
 * Used in src/App.tsx PortalLayout as: <Sidebar /> — no props, reads useAuthStore + fetches badge counts.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore, type AuthUser } from '@/store/auth'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
import { Sidebar } from './Sidebar'

const oaOperatorUser: AuthUser = {
  userId: 'u-1',
  email: 'operator@acme.example',
  displayName: 'Priya Sharma',
  role: 'oa_operator',
  tenantId: 't-1',
  tenantName: 'Acme Corp',
}

const oaAdminUser: AuthUser = {
  ...oaOperatorUser,
  userId: 'u-2',
  role: 'oa_admin',
}

const portalAdminUser: AuthUser = {
  userId: 'u-3',
  email: 'admin@prana.in',
  displayName: 'Rahul Verma',
  role: 'portal_admin',
  tenantId: null,
  tenantName: null,
}

function renderSidebar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: null, accessToken: null, stepToken: null, requiresTotpSetup: false })
  // Default: no badge data needed unless a test opts in
  vi.mocked(api.get).mockResolvedValue({ data: {} })
})

describe('Sidebar — no user', () => {
  it('renders nothing when there is no logged-in user', () => {
    const { container } = renderSidebar()
    expect(container).toBeEmptyDOMElement()
  })
})

describe('Sidebar — oa_operator role', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: oaOperatorUser })
  })

  it('renders the oa_operator nav items with /org base path', () => {
    renderSidebar()
    expect(screen.getByText('Dashboard').closest('a')).toHaveAttribute('href', '/org/dashboard')
    expect(screen.getByText('Employee Master').closest('a')).toHaveAttribute('href', '/org/employees')
    expect(screen.getByText('Upload Documents').closest('a')).toHaveAttribute('href', '/org/upload')
    expect(screen.getByText('Storage').closest('a')).toHaveAttribute('href', '/org/storage')
    expect(screen.getByText('Request Elevation').closest('a')).toHaveAttribute('href', '/org/elevation')

    // oa_operator does not get oa_admin-only items
    expect(screen.queryByText('User Management')).not.toBeInTheDocument()
    expect(screen.queryByText('Exception Queue')).not.toBeInTheDocument()
  })

  it('renders the tenant name block', () => {
    renderSidebar()
    expect(screen.getByText('Organisation')).toBeInTheDocument()
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
  })
})

describe('Sidebar — oa_admin role', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: oaAdminUser })
  })

  it('renders the oa_admin nav items, distinct from oa_operator', () => {
    renderSidebar()
    expect(screen.getByText('Document Viewer').closest('a')).toHaveAttribute('href', '/org/documents')
    expect(screen.getByText('Exception Queue').closest('a')).toHaveAttribute('href', '/org/exceptions')
    expect(screen.getByText('User Management').closest('a')).toHaveAttribute('href', '/org/users')
    expect(screen.getByText('Elevation Approvals').closest('a')).toHaveAttribute('href', '/org/elevations')
    expect(screen.getByText('HRMS Integration').closest('a')).toHaveAttribute('href', '/org/hrms')

    // oa_admin does not get the oa_operator-only "Request Elevation" item
    expect(screen.queryByText('Request Elevation')).not.toBeInTheDocument()
  })

  it('shows exception + elevation badge counts once the sidebar-badges query resolves', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/v1/org/exceptions/count') return Promise.resolve({ data: { count: 5 } })
      if (url === '/v1/org/elevations/pending-count') return Promise.resolve({ data: { count: 2 } })
      return Promise.resolve({ data: {} })
    })
    renderSidebar()

    await waitFor(() => expect(screen.getByText('5')).toBeInTheDocument())
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('does not show badges when counts are zero', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/v1/org/exceptions/count') return Promise.resolve({ data: { count: 0 } })
      if (url === '/v1/org/elevations/pending-count') return Promise.resolve({ data: { count: 0 } })
      return Promise.resolve({ data: {} })
    })
    renderSidebar()

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v1/org/exceptions/count'))
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })
})

describe('Sidebar — portal_admin role', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: portalAdminUser })
  })

  it('renders grouped nav with /admin base path and no tenant block', () => {
    renderSidebar()
    expect(screen.getByText('OVERVIEW')).toBeInTheDocument()
    expect(screen.getByText('TENANT MANAGEMENT')).toBeInTheDocument()
    expect(screen.getByText('Meta Dashboard').closest('a')).toHaveAttribute('href', '/admin/dashboard')
    expect(screen.getByText('Tenant Directory').closest('a')).toHaveAttribute('href', '/admin/tenants')

    expect(screen.queryByText('Organisation')).not.toBeInTheDocument()
  })

  it('toggles a collapsible group closed and open again on header click', async () => {
    const user = userEvent.setup()
    renderSidebar()

    // TENANT MANAGEMENT is collapsible (per Sidebar.tsx navForRole) and open by default
    expect(screen.getByText('Tenant Directory')).toBeInTheDocument()

    await user.click(screen.getByText('TENANT MANAGEMENT'))
    expect(screen.queryByText('Tenant Directory')).not.toBeInTheDocument()

    await user.click(screen.getByText('TENANT MANAGEMENT'))
    expect(screen.getByText('Tenant Directory')).toBeInTheDocument()
  })
})
