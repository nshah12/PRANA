import { describe, it, expect, beforeEach } from 'vitest'
import { useEmpAuthStore, type EmpUser } from './empAuth'

const MOCK_EMP: EmpUser = {
  userId: 'eu-1',
  name: 'Rahul Kumar',
  email: 'rahul@example.com',
  mobile: '+919000000001',
  pan_token: 'hmac-deadbeef',
  vault_url: '/emp/vault',
}

function resetStore() {
  useEmpAuthStore.setState({ user: null, accessToken: null, stepToken: null })
  localStorage.clear()
}

beforeEach(() => {
  resetStore()
})

describe('useEmpAuthStore — initial state', () => {
  it('starts with no user and no tokens', () => {
    const s = useEmpAuthStore.getState()
    expect(s.user).toBeNull()
    expect(s.accessToken).toBeNull()
    expect(s.stepToken).toBeNull()
  })
})

describe('useEmpAuthStore — actions', () => {
  it('setUser stores the employee, never a raw PAN — only pan_token (HMAC)', () => {
    useEmpAuthStore.getState().setUser(MOCK_EMP)
    const stored = useEmpAuthStore.getState().user
    expect(stored).toEqual(MOCK_EMP)
    // Privacy contract: field is named/typed pan_token, not pan — guards against
    // a future accidental rename that would smuggle a raw PAN into client state.
    expect(stored).not.toHaveProperty('pan')
    expect(stored?.pan_token).toBe('hmac-deadbeef')
  })

  it('setAccessToken stores the JWT', () => {
    useEmpAuthStore.getState().setAccessToken('emp-jwt-abc123')
    expect(useEmpAuthStore.getState().accessToken).toBe('emp-jwt-abc123')
  })

  it('setStepToken stores and clears the transient OTP/TOTP step token', () => {
    useEmpAuthStore.getState().setStepToken('step-otp-1')
    expect(useEmpAuthStore.getState().stepToken).toBe('step-otp-1')
    useEmpAuthStore.getState().setStepToken(null)
    expect(useEmpAuthStore.getState().stepToken).toBeNull()
  })

  it('logout clears every field', () => {
    useEmpAuthStore.getState().setUser(MOCK_EMP)
    useEmpAuthStore.getState().setAccessToken('emp-jwt-abc123')
    useEmpAuthStore.getState().setStepToken('step-otp-1')

    useEmpAuthStore.getState().logout()

    const s = useEmpAuthStore.getState()
    expect(s.user).toBeNull()
    expect(s.accessToken).toBeNull()
    expect(s.stepToken).toBeNull()
  })
})

describe('useEmpAuthStore — persistence (zustand persist, key "prana-emp-auth")', () => {
  it('persists user across a simulated reload', () => {
    useEmpAuthStore.getState().setUser(MOCK_EMP)
    const raw = localStorage.getItem('prana-emp-auth')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw as string)
    expect(parsed.state.user).toEqual(MOCK_EMP)
  })

  it('does NOT persist the transient stepToken', () => {
    useEmpAuthStore.getState().setStepToken('step-otp-1')
    const raw = localStorage.getItem('prana-emp-auth')
    const parsed = raw ? JSON.parse(raw) : { state: {} }
    expect(parsed.state.stepToken).toBeUndefined()
  })

  it(
    'never persists accessToken (the JWT) to localStorage — rehydrated via silent refresh',
    () => {
      useEmpAuthStore.getState().setUser(MOCK_EMP)
      useEmpAuthStore.getState().setAccessToken('emp-jwt-abc123')
      const raw = localStorage.getItem('prana-emp-auth')
      const parsed = JSON.parse(raw as string)
      expect(parsed.state.accessToken).toBeUndefined()
      expect(parsed.state.user).toBeTruthy()   // user IS persisted
    },
  )
})
