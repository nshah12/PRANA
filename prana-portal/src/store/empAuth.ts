import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface EmpUser {
  userId: string
  name: string
  email: string
  mobile: string
  pan_token: string          // HMAC — never raw PAN
  vault_url: string
}

interface EmpAuthState {
  user: EmpUser | null
  accessToken: string | null
  stepToken: string | null   // transient — between OTP and TOTP steps
  setUser: (user: EmpUser) => void
  setAccessToken: (token: string) => void
  setStepToken: (token: string | null) => void
  logout: () => void
}

export const useEmpAuthStore = create<EmpAuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      stepToken: null,
      setUser: (user) => set({ user }),
      setAccessToken: (accessToken) => set({ accessToken }),
      setStepToken: (stepToken) => set({ stepToken }),
      logout: () => set({ user: null, accessToken: null, stepToken: null }),
    }),
    {
      name: 'prana-emp-auth',
      partialize: (s) => ({ user: s.user, accessToken: s.accessToken }),
    },
  ),
)
