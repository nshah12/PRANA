import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type UserRole = 'oa_operator' | 'oa_admin' | 'chro' | 'cfo' | 'ciso' | 'portal_admin'

export interface AuthUser {
  userId: string
  email: string
  displayName: string
  role: UserRole
  tenantId: string | null
  tenantName: string | null
}

interface AuthState {
  user: AuthUser | null
  accessToken: string | null
  stepToken: string | null          // transient — between login steps
  requiresTotpSetup: boolean        // true on first login — show QR screen
  setUser: (user: AuthUser) => void
  setAccessToken: (token: string) => void
  setStepToken: (token: string | null) => void
  setRequiresTotpSetup: (v: boolean) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      stepToken: null,
      requiresTotpSetup: false,
      setUser: (user) => set({ user }),
      setAccessToken: (accessToken) => set({ accessToken }),
      setStepToken: (stepToken) => set({ stepToken }),
      setRequiresTotpSetup: (requiresTotpSetup) => set({ requiresTotpSetup }),
      logout: () => set({ user: null, accessToken: null, stepToken: null, requiresTotpSetup: false }),
    }),
    {
      name: 'prana-auth',
      partialize: (s) => ({ user: s.user, accessToken: s.accessToken }),
    },
  ),
)

// Role colour map (matches PRANA_Portal_v52.html spec)
export const ROLE_COLOR: Record<UserRole, string> = {
  oa_operator: '#10B981',
  oa_admin:    '#8B5CF6',
  chro:        '#EC4899',
  cfo:         '#6366F1',
  ciso:        '#EF4444',
  portal_admin:'#F59E0B',
}

export const ROLE_LABEL: Record<UserRole, string> = {
  oa_operator:  'OA-Operator',
  oa_admin:     'OA-Admin',
  chro:         'CHRO',
  cfo:          'CFO',
  ciso:         'CISO',
  portal_admin: 'Portal Admin',
}
