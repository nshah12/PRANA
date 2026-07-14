import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { RequireAuth, RequireEmpAuth } from './App'
import { useAuthStore } from '@/store/auth'
import { useEmpAuthStore } from '@/store/empAuth'
import type { AuthUser } from '@/store/auth'
import type { EmpUser } from '@/store/empAuth'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'
const mockPost = vi.mocked(api.post)

const MOCK_USER: AuthUser = {
  userId: 'u-1',
  email: 'oa@acme.example',
  displayName: 'Priya Sharma',
  role: 'oa_admin',
  tenantId: 't-1',
  tenantName: 'Acme Ltd',
}

const MOCK_EMP: EmpUser = {
  userId: 'eu-1',
  name: 'Rahul Kumar',
  email: 'rahul@example.com',
  mobile: '+919000000001',
  pan_token: 'hmac-deadbeef',
  vault_url: '/emp/vault',
}

function resetStores() {
  useAuthStore.setState({ user: null, accessToken: null, stepToken: null, requiresTotpSetup: false })
  useEmpAuthStore.setState({ user: null, accessToken: null, stepToken: null })
}

beforeEach(() => {
  resetStores()
  vi.clearAllMocks()
})

function renderAtPath(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/org/login" element={<div>Org Login Page</div>} />
        <Route path="/admin/login" element={<div>Admin Login Page</div>} />
        <Route path="/emp/login" element={<div>Emp Login Page</div>} />
        <Route
          path="/org/dashboard"
          element={<RequireAuth><div>Org Dashboard</div></RequireAuth>}
        />
        <Route
          path="/admin/dashboard"
          element={<RequireAuth><div>Admin Dashboard</div></RequireAuth>}
        />
        <Route
          path="/emp/vault"
          element={<RequireEmpAuth><div>Emp Vault</div></RequireEmpAuth>}
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RequireAuth', () => {
  it('redirects to /org/login when no user and path is under /org', () => {
    renderAtPath('/org/dashboard')
    expect(screen.getByText('Org Login Page')).toBeInTheDocument()
    expect(screen.queryByText('Org Dashboard')).not.toBeInTheDocument()
  })

  it('redirects to /admin/login (not /org/login) when no user and path is under /admin', () => {
    renderAtPath('/admin/dashboard')
    expect(screen.getByText('Admin Login Page')).toBeInTheDocument()
    expect(screen.queryByText('Org Login Page')).not.toBeInTheDocument()
  })

  it('renders the protected content once a user is present and accessToken already set (skips bootstrap)', () => {
    useAuthStore.getState().setUser(MOCK_USER)
    useAuthStore.getState().setAccessToken('org-jwt-existing')
    renderAtPath('/org/dashboard')
    expect(screen.getByText('Org Dashboard')).toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('an admin-role user unlocks the /admin path the same way', () => {
    useAuthStore.getState().setUser({ ...MOCK_USER, role: 'portal_admin' })
    useAuthStore.getState().setAccessToken('admin-jwt-existing')
    renderAtPath('/admin/dashboard')
    expect(screen.getByText('Admin Dashboard')).toBeInTheDocument()
  })

  it('bootstraps: user persisted but no in-memory accessToken (fresh tab/reload) proactively refreshes before rendering', async () => {
    mockPost.mockResolvedValue({ data: { access_token: 'org-jwt-refreshed' } })
    useAuthStore.getState().setUser(MOCK_USER)
    renderAtPath('/org/dashboard')

    // Not rendered synchronously — the bootstrap refresh is in flight first.
    expect(screen.queryByText('Org Dashboard')).not.toBeInTheDocument()
    expect(await screen.findByText('Org Dashboard')).toBeInTheDocument()
    expect(mockPost).toHaveBeenCalledWith('/auth/org/refresh', {}, { withCredentials: true })
    expect(useAuthStore.getState().accessToken).toBe('org-jwt-refreshed')
  })

  it('bootstraps via /auth/admin/refresh (not /auth/org/refresh) for a portal_admin user', async () => {
    mockPost.mockResolvedValue({ data: { access_token: 'admin-jwt-refreshed' } })
    useAuthStore.getState().setUser({ ...MOCK_USER, role: 'portal_admin' })
    renderAtPath('/admin/dashboard')

    expect(await screen.findByText('Admin Dashboard')).toBeInTheDocument()
    expect(mockPost).toHaveBeenCalledWith('/auth/admin/refresh', {}, { withCredentials: true })
  })

  it('bootstrap failure (expired/invalid session) logs out and redirects to login instead of hanging', async () => {
    mockPost.mockRejectedValue(new Error('refresh failed'))
    useAuthStore.getState().setUser(MOCK_USER)
    renderAtPath('/org/dashboard')

    expect(await screen.findByText('Org Login Page')).toBeInTheDocument()
    expect(useAuthStore.getState().user).toBeNull()
  })
})

describe('RequireEmpAuth', () => {
  it('redirects to /emp/login when neither user nor accessToken is set', () => {
    renderAtPath('/emp/vault')
    expect(screen.getByText('Emp Login Page')).toBeInTheDocument()
    expect(screen.queryByText('Emp Vault')).not.toBeInTheDocument()
  })

  it('renders protected content when user and accessToken are both already set (skips bootstrap)', () => {
    useEmpAuthStore.getState().setUser(MOCK_EMP)
    useEmpAuthStore.getState().setAccessToken('emp-jwt-existing')
    renderAtPath('/emp/vault')
    expect(screen.getByText('Emp Vault')).toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('bootstraps: user persisted but no in-memory accessToken proactively refreshes before rendering', async () => {
    mockPost.mockResolvedValue({ data: { access_token: 'emp-jwt-refreshed' } })
    useEmpAuthStore.getState().setUser(MOCK_EMP)
    renderAtPath('/emp/vault')

    expect(screen.queryByText('Emp Vault')).not.toBeInTheDocument()
    expect(await screen.findByText('Emp Vault')).toBeInTheDocument()
    expect(mockPost).toHaveBeenCalledWith('/auth/employee/refresh', {}, { withCredentials: true })
    expect(useEmpAuthStore.getState().accessToken).toBe('emp-jwt-refreshed')
  })

  it('bootstrap failure logs out and redirects to /emp/login instead of hanging', async () => {
    mockPost.mockRejectedValue(new Error('refresh failed'))
    useEmpAuthStore.getState().setUser(MOCK_EMP)
    renderAtPath('/emp/vault')

    expect(await screen.findByText('Emp Login Page')).toBeInTheDocument()
    expect(useEmpAuthStore.getState().user).toBeNull()
  })

  it('renders protected content when only accessToken is set (pre-user-hydration window)', () => {
    // finishLogin sets accessToken before user — RequireEmpAuth must not bounce
    // a legitimately-logging-in employee back to /emp/login in that brief window.
    useEmpAuthStore.getState().setAccessToken('emp-jwt-abc123')
    renderAtPath('/emp/vault')
    expect(screen.getByText('Emp Vault')).toBeInTheDocument()
  })
})
