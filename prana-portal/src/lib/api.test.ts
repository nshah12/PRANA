import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import axios from 'axios'
import { api, getApiBase } from './api'
import { useAuthStore } from '@/store/auth'
import { useEmpAuthStore } from '@/store/empAuth'

// Axios interceptors aren't individually exported — the standard way to unit-test
// interceptor logic without a real network call is to invoke the registered
// handler functions directly off the instance's internal handlers array. This is
// implementation-detail-reliant but stable across axios 1.x and is the accepted
// pattern for this kind of test.
const requestFulfilled = (api.interceptors.request as any).handlers[0].fulfilled
const responseRejected = (api.interceptors.response as any).handlers[0].rejected

function setLocation(pathname: string) {
  const original = window.location
  // jsdom's window.location isn't directly reassignable — delete + replace.
  // @ts-expect-error intentional override for test isolation
  delete window.location
  // @ts-expect-error partial Location stub — only fields the code under test reads
  window.location = { pathname, href: '' }
  return () => {
    // @ts-expect-error restore
    delete window.location
    // @ts-expect-error restoring the real Location object, same setter-type quirk as above
    window.location = original
  }
}

function resetStores() {
  useAuthStore.setState({ user: null, accessToken: null, stepToken: null, requiresTotpSetup: false })
  useEmpAuthStore.setState({ user: null, accessToken: null, stepToken: null })
}

let restoreLocation: () => void

beforeEach(() => {
  resetStores()
  restoreLocation = setLocation('/org/dashboard')
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  restoreLocation()
  vi.restoreAllMocks()
})

describe('getApiBase', () => {
  it('falls back to the Vite proxy path when no override is set', () => {
    localStorage.removeItem('PRANA_API_URL')
    expect(getApiBase()).toBe(import.meta.env.VITE_API_URL ?? '/api')
  })

  it('prefers a localStorage override when present (manual API-host switch)', () => {
    localStorage.setItem('PRANA_API_URL', 'https://staging.prana.in')
    expect(getApiBase()).toBe('https://staging.prana.in')
    localStorage.removeItem('PRANA_API_URL')
  })
})

describe('request interceptor — token attachment', () => {
  it('attaches the org token on an /org page', () => {
    restoreLocation()
    restoreLocation = setLocation('/org/dashboard')
    useAuthStore.getState().setAccessToken('org-token')
    const config = requestFulfilled({ headers: {} })
    expect(config.headers.Authorization).toBe('Bearer org-token')
  })

  it('falls back to the employee token on an /org page if no org token exists', () => {
    restoreLocation()
    restoreLocation = setLocation('/org/dashboard')
    useEmpAuthStore.getState().setAccessToken('emp-token')
    const config = requestFulfilled({ headers: {} })
    expect(config.headers.Authorization).toBe('Bearer emp-token')
  })

  it('attaches the employee token on an /emp/ page', () => {
    restoreLocation()
    restoreLocation = setLocation('/emp/vault')
    useEmpAuthStore.getState().setAccessToken('emp-token')
    const config = requestFulfilled({ headers: {} })
    expect(config.headers.Authorization).toBe('Bearer emp-token')
  })

  it('falls back to the org token on an /emp/ page if no employee token exists', () => {
    restoreLocation()
    restoreLocation = setLocation('/emp/vault')
    useAuthStore.getState().setAccessToken('org-token')
    const config = requestFulfilled({ headers: {} })
    expect(config.headers.Authorization).toBe('Bearer org-token')
  })

  it('sets no Authorization header when neither token is present', () => {
    const config = requestFulfilled({ headers: {} })
    expect(config.headers.Authorization).toBeUndefined()
  })

  it('reads the employee token via the localStorage fallback during the hydration-timing window', () => {
    // getEmpToken() falls back to reading "prana-emp-auth" directly when the
    // Zustand store hasn't hydrated its in-memory state yet.
    localStorage.setItem('prana-emp-auth', JSON.stringify({ state: { accessToken: 'hydrating-token' }, version: 0 }))
    restoreLocation()
    restoreLocation = setLocation('/emp/vault')
    const config = requestFulfilled({ headers: {} })
    expect(config.headers.Authorization).toBe('Bearer hydrating-token')
    localStorage.removeItem('prana-emp-auth')
  })
})

function make401Error(url: string, retried = false) {
  return {
    config: { url, headers: {}, _retry: retried },
    response: { status: 401, data: { error: 'UNAUTHORIZED' } },
  }
}

describe('response interceptor — non-401 / already-retried / auth-endpoint passthrough', () => {
  it('rejects non-401 errors without attempting a refresh', async () => {
    const err = { config: { url: '/v1/vault/documents', headers: {} }, response: { status: 500 } }
    await expect(responseRejected(err)).rejects.toBe(err)
  })

  it('rejects a 401 from an AUTH_PATHS-listed endpoint without attempting a refresh (no redirect loop)', async () => {
    const err = make401Error('/auth/org/login')
    await expect(responseRejected(err)).rejects.toBe(err)
  })

  it('rejects a 401 that has already been retried once, rather than retrying forever', async () => {
    const err = make401Error('/v1/vault/documents', /* retried */ true)
    await expect(responseRejected(err)).rejects.toBe(err)
  })
})

describe('response interceptor — employee 401 refresh flow', () => {
  it('on successful refresh: stores the new token and retries the original request', async () => {
    restoreLocation()
    restoreLocation = setLocation('/emp/vault')
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({ data: { access_token: 'new-emp-token' } } as any)

    const err = make401Error('/v1/vault/documents')
    // The interceptor's final step re-dispatches `api(original)`, which is a real
    // network call in this test environment and will reject (no server running) —
    // that's fine, it's outside what this test verifies, and the outer .catch
    // below swallows it so it doesn't fail the assertions.
    await responseRejected(err).catch(() => {})

    expect(postSpy).toHaveBeenCalledWith('/auth/employee/refresh', {}, { withCredentials: true })
    expect(useEmpAuthStore.getState().accessToken).toBe('new-emp-token')
  })

  it('on failed refresh: logs the employee out and redirects to /emp/login', async () => {
    restoreLocation()
    restoreLocation = setLocation('/emp/vault')
    useEmpAuthStore.getState().setUser({
      userId: 'eu-1', name: 'x', email: 'x@x.com', mobile: '+91', pan_token: 'x', vault_url: '/emp/vault',
    })
    vi.spyOn(api, 'post').mockRejectedValueOnce(new Error('refresh failed'))

    const err = make401Error('/v1/vault/documents')
    await responseRejected(err).catch(() => {})

    expect(useEmpAuthStore.getState().user).toBeNull()
    expect(window.location.href).toBe('/emp/login')
  })
})

describe('response interceptor — org/admin 401 refresh flow', () => {
  it('refreshes via /auth/org/refresh for a non-portal_admin role, through the shared api client', async () => {
    restoreLocation()
    restoreLocation = setLocation('/org/dashboard')
    useAuthStore.getState().setUser({
      userId: 'u-1', email: 'x@x.com', displayName: 'x', role: 'oa_admin', tenantId: 't-1', tenantName: 'Acme',
    })
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({ data: { access_token: 'new-org-token' } } as any)
    const axiosPostSpy = vi.spyOn(axios, 'post')

    const err = make401Error('/v1/org/employees')
    await responseRejected(err).catch(() => {})

    // Regression guard: the org/admin refresh path previously called the bare
    // `axios.post(...)` import instead of the configured `api` instance, silently
    // bypassing getApiBase() (VITE_API_URL / the local /api proxy). In a
    // deployment where the portal and API are on different origins, that resolves
    // against the portal's own origin instead of the real API host and the
    // refresh 404s. Fixed to go through `api.post`, matching the employee path.
    expect(postSpy).toHaveBeenCalledWith('/auth/org/refresh', {}, { withCredentials: true })
    expect(axiosPostSpy).not.toHaveBeenCalled()
    expect(useAuthStore.getState().accessToken).toBe('new-org-token')
  })

  it('refreshes via /auth/admin/refresh when role is portal_admin', async () => {
    restoreLocation()
    restoreLocation = setLocation('/admin/dashboard')
    useAuthStore.getState().setUser({
      userId: 'pa-1', email: 'pa@prana.in', displayName: 'PA', role: 'portal_admin', tenantId: null, tenantName: null,
    })
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce({ data: { access_token: 'new-admin-token' } } as any)

    const err = make401Error('/admin/tenants')
    await responseRejected(err).catch(() => {})

    expect(postSpy).toHaveBeenCalledWith('/auth/admin/refresh', {}, { withCredentials: true })
    expect(useAuthStore.getState().accessToken).toBe('new-admin-token')
  })

  it('on failed refresh: logs out and redirects to the role-appropriate login page', async () => {
    restoreLocation()
    restoreLocation = setLocation('/admin/dashboard')
    useAuthStore.getState().setUser({
      userId: 'pa-1', email: 'pa@prana.in', displayName: 'PA', role: 'portal_admin', tenantId: null, tenantName: null,
    })
    vi.spyOn(api, 'post').mockRejectedValueOnce(new Error('refresh failed'))

    const err = make401Error('/admin/tenants')
    await responseRejected(err).catch(() => {})

    expect(useAuthStore.getState().user).toBeNull()
    expect(window.location.href).toBe('/admin/login')
  })
})
