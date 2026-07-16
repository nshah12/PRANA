import axios from 'axios'
import { useAuthStore } from '@/store/auth'
import { useEmpAuthStore } from '@/store/empAuth'

// Priority: localStorage (user override) → VITE_API_URL (build-time) → /api (Vite proxy, local dev)
export function getApiBase(): string {
  try { const u = localStorage.getItem('PRANA_API_URL'); if (u) return u } catch {}
  return import.meta.env.VITE_API_URL ?? '/api'
}

export const api = axios.create({
  baseURL: getApiBase(),
  withCredentials: true,
})

// Access tokens live in memory only (never localStorage). On reload the store starts with
// a null token; the first request 401s and the response interceptor silently refreshes via
// the httpOnly refresh cookie, so no persisted token is needed.
api.interceptors.request.use((config) => {
  const empToken = useEmpAuthStore.getState().accessToken
  const orgToken = useAuthStore.getState().accessToken
  const onEmpPage = typeof window !== 'undefined' && window.location.pathname.startsWith('/emp/')
  const token = onEmpPage ? (empToken ?? orgToken) : (orgToken ?? empToken)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Silent refresh on 401 — skip for auth endpoints to avoid redirect loops
const AUTH_PATHS = ['/auth/org/login', '/auth/org/totp', '/auth/org/refresh', '/auth/org/logout',
                    '/auth/admin/login', '/auth/admin/totp', '/auth/admin/refresh', '/auth/admin/logout',
                    '/auth/admin/totp-setup', '/auth/org/totp-setup',
                    '/auth/employee/login', '/auth/employee/request-otp', '/auth/employee/verify-otp',
                    '/auth/employee/complete', '/auth/employee/totp', '/auth/employee/refresh']

// Single-flight refresh: several requests can 401 in the same tick (e.g. a
// dashboard firing parallel queries right after login). Without sharing one
// in-flight promise, each would call /refresh independently — the backend
// rotates the refresh token per call, so only the first succeeds and the
// rest 401 on an already-rotated token, each wrongly triggering a full
// logout+redirect and clobbering the session the first call just restored.
let empRefreshPromise: Promise<string> | null = null
let orgRefreshPromise: Promise<string> | null = null

function refreshEmpToken(): Promise<string> {
  if (!empRefreshPromise) {
    empRefreshPromise = api.post('/auth/employee/refresh', {}, { withCredentials: true })
      .then(({ data }) => {
        useEmpAuthStore.getState().setAccessToken(data.access_token)
        return data.access_token as string
      })
      .finally(() => { empRefreshPromise = null })
  }
  return empRefreshPromise
}

function refreshOrgToken(refreshPath: string): Promise<string> {
  if (!orgRefreshPromise) {
    orgRefreshPromise = api.post(refreshPath, {}, { withCredentials: true })
      .then(({ data }) => {
        useAuthStore.getState().setAccessToken(data.access_token)
        return data.access_token as string
      })
      .finally(() => { orgRefreshPromise = null })
  }
  return orgRefreshPromise
}

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    const isAuthEndpoint = AUTH_PATHS.some(p => original.url?.includes(p))
    if (err.response?.status === 401 && !original._retry && !isAuthEndpoint) {
      original._retry = true
      const isEmpRoute = window.location.pathname.startsWith('/emp/')
      const role = useAuthStore.getState().user?.role
      if (isEmpRoute) {
        try {
          const accessToken = await refreshEmpToken()
          original.headers.Authorization = `Bearer ${accessToken}`
          return api(original)
        } catch {
          useEmpAuthStore.getState().logout()
          window.location.href = '/emp/login'
        }
      } else {
        const refreshPath = role === 'portal_admin' ? '/auth/admin/refresh' : '/auth/org/refresh'
        try {
          const accessToken = await refreshOrgToken(refreshPath)
          original.headers.Authorization = `Bearer ${accessToken}`
          return api(original)
        } catch {
          useAuthStore.getState().logout()
          window.location.href = role === 'portal_admin' ? '/admin/login' : '/org/login'
        }
      }
    }
    return Promise.reject(err)
  },
)
