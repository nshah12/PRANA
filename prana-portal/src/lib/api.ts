import axios from 'axios'
import { useAuthStore } from '@/store/auth'
import { useEmpAuthStore } from '@/store/empAuth'

// Local dev: VITE_API_URL not set → '/api' → Vite proxy → localhost:8000
// GitHub Pages build: VITE_API_URL baked in from PORTAL_API_URL secret → direct API calls
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api',
  withCredentials: true,   // httpOnly refresh cookie
})

// Attach access token — employee token takes priority on /emp/* routes; org token elsewhere
api.interceptors.request.use((config) => {
  const empToken = useEmpAuthStore.getState().accessToken
  const orgToken = useAuthStore.getState().accessToken
  const isEmpUrl = config.url?.includes('/emp/') || config.url?.includes('/auth/employee/')
  const token = (isEmpUrl && empToken) ? empToken : (orgToken ?? empToken)
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
    if (err.response?.status === 401 && !original._retry && !isAuthEndpoint) {
      original._retry = true
      const isEmpRoute = window.location.pathname.startsWith('/emp/')
      const role = useAuthStore.getState().user?.role
      if (isEmpRoute) {
        try {
          const { data } = await api.post('/auth/employee/refresh', {}, { withCredentials: true })
          useEmpAuthStore.getState().setAccessToken(data.access_token)
          original.headers.Authorization = `Bearer ${data.access_token}`
          return api(original)
        } catch {
          useEmpAuthStore.getState().logout()
          window.location.href = '/emp/login'
        }
      } else {
        const refreshPath = role === 'portal_admin' ? '/auth/admin/refresh' : '/auth/org/refresh'
        try {
          const { data } = await axios.post(refreshPath, {}, { withCredentials: true })
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
