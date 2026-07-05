import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { RequireAuth, RequireEmpAuth } from './App'
import { useAuthStore } from '@/store/auth'
import { useEmpAuthStore } from '@/store/empAuth'
import type { AuthUser } from '@/store/auth'
import type { EmpUser } from '@/store/empAuth'

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

  it('renders the protected content once a user is present', () => {
    useAuthStore.getState().setUser(MOCK_USER)
    renderAtPath('/org/dashboard')
    expect(screen.getByText('Org Dashboard')).toBeInTheDocument()
  })

  it('an admin-role user unlocks the /admin path the same way', () => {
    useAuthStore.getState().setUser({ ...MOCK_USER, role: 'portal_admin' })
    renderAtPath('/admin/dashboard')
    expect(screen.getByText('Admin Dashboard')).toBeInTheDocument()
  })
})

describe('RequireEmpAuth', () => {
  it('redirects to /emp/login when neither user nor accessToken is set', () => {
    renderAtPath('/emp/vault')
    expect(screen.getByText('Emp Login Page')).toBeInTheDocument()
    expect(screen.queryByText('Emp Vault')).not.toBeInTheDocument()
  })

  it('renders protected content when user is set', () => {
    useEmpAuthStore.getState().setUser(MOCK_EMP)
    renderAtPath('/emp/vault')
    expect(screen.getByText('Emp Vault')).toBeInTheDocument()
  })

  it('renders protected content when only accessToken is set (pre-user-hydration window)', () => {
    // finishLogin sets accessToken before user — RequireEmpAuth must not bounce
    // a legitimately-logging-in employee back to /emp/login in that brief window.
    useEmpAuthStore.getState().setAccessToken('emp-jwt-abc123')
    renderAtPath('/emp/vault')
    expect(screen.getByText('Emp Vault')).toBeInTheDocument()
  })
})
