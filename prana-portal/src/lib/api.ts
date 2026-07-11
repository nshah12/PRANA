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
                    '/auth/employee/request-otp', '/auth/employee/verify-otp',
                    '/auth/employee/complete', '/auth/employee/totp', '/auth/employee/refresh']

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    const isAuthEndpoint = AUTH_PATHS.some(p => original.url?.includes(p))
    console.warn('[API ERR]', err.response?.status, original?.url, 'retry:', original?._retry, 'isAuth:', isAuthEndpoint)
    if (err.response?.status === 401 && !original._retry && !isAuthEndpoint) {
      original._retry = true
      const isEmpRoute = window.location.pathname.startsWith('/emp/')
      const role = useAuthStore.getState().user?.role
      if (isEmpRoute) {
        try {
          console.warn('[API REFRESH] attempting employee refresh...')
          const { data } = await api.post('/auth/employee/refresh', {}, { withCredentials: true })
          console.warn('[API REFRESH] success, new token:', data.access_token?.slice(-8))
          useEmpAuthStore.getState().setAccessToken(data.access_token)
          original.headers.Authorization = `Bearer ${data.access_token}`
          return api(original)
        } catch (refreshErr: any) {
          console.error('[API REFRESH FAILED]', refreshErr?.response?.status, refreshErr?.response?.data)
          useEmpAuthStore.getState().logout()
          window.location.href = '/emp/login'
        }
      } else {
        const refreshPath = role === 'portal_admin' ? '/auth/admin/refresh' : '/auth/org/refresh'
        try {
          const { data } = await api.post(refreshPath, {}, { withCredentials: true })
          useAuthStore.getState().setAccessToken(data.access_token)
          original.headers.Authorization = `Bearer ${data.access_token}`
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
