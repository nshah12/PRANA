import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore, ROLE_COLOR, ROLE_LABEL, type AuthUser } from './auth'

const MOCK_USER: AuthUser = {
  userId: 'u-1',
  email: 'oa@acme.example',
  displayName: 'Priya Sharma',
  role: 'oa_admin',
  tenantId: 't-1',
  tenantName: 'Acme Ltd',
}

function resetStore() {
  useAuthStore.setState({
    user: null,
    accessToken: null,
    stepToken: null,
    requiresTotpSetup: false,
  })
  localStorage.clear()
}

beforeEach(() => {
  resetStore()
})

describe('useAuthStore — initial state', () => {
  it('starts with no user, no tokens, and totp setup not required', () => {
    const s = useAuthStore.getState()
    expect(s.user).toBeNull()
    expect(s.accessToken).toBeNull()
    expect(s.stepToken).toBeNull()
    expect(s.requiresTotpSetup).toBe(false)
  })
})

describe('useAuthStore — actions', () => {
  it('setUser stores the authenticated user', () => {
    useAuthStore.getState().setUser(MOCK_USER)
    expect(useAuthStore.getState().user).toEqual(MOCK_USER)
  })

  it('setAccessToken stores the JWT', () => {
    useAuthStore.getState().setAccessToken('jwt-abc123')
    expect(useAuthStore.getState().accessToken).toBe('jwt-abc123')
  })

  it('setStepToken stores and clears the transient step token', () => {
    useAuthStore.getState().setStepToken('step-xyz')
    expect(useAuthStore.getState().stepToken).toBe('step-xyz')
    useAuthStore.getState().setStepToken(null)
    expect(useAuthStore.getState().stepToken).toBeNull()
  })

  it('setRequiresTotpSetup toggles the first-login QR flag', () => {
    useAuthStore.getState().setRequiresTotpSetup(true)
    expect(useAuthStore.getState().requiresTotpSetup).toBe(true)
  })

  it('logout clears every field, including transient ones', () => {
    useAuthStore.getState().setUser(MOCK_USER)
    useAuthStore.getState().setAccessToken('jwt-abc123')
    useAuthStore.getState().setStepToken('step-xyz')
    useAuthStore.getState().setRequiresTotpSetup(true)

    useAuthStore.getState().logout()

    const s = useAuthStore.getState()
    expect(s.user).toBeNull()
    expect(s.accessToken).toBeNull()
    expect(s.stepToken).toBeNull()
    expect(s.requiresTotpSetup).toBe(false)
  })

  it('setting one field does not clobber sibling fields', () => {
    useAuthStore.getState().setUser(MOCK_USER)
    useAuthStore.getState().setStepToken('step-xyz')
    useAuthStore.getState().setAccessToken('jwt-abc123')

    const s = useAuthStore.getState()
    expect(s.user).toEqual(MOCK_USER)
    expect(s.stepToken).toBe('step-xyz')
    expect(s.accessToken).toBe('jwt-abc123')
  })
})

describe('useAuthStore — persistence (zustand persist, key "prana-auth")', () => {
  it('persists user across a simulated reload', () => {
    useAuthStore.getState().setUser(MOCK_USER)
    const raw = localStorage.getItem('prana-auth')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw as string)
    expect(parsed.state.user).toEqual(MOCK_USER)
  })

  it('does NOT persist the transient stepToken or requiresTotpSetup flag', () => {
    useAuthStore.getState().setStepToken('step-xyz')
    useAuthStore.getState().setRequiresTotpSetup(true)
    const raw = localStorage.getItem('prana-auth')
    const parsed = raw ? JSON.parse(raw) : { state: {} }
    expect(parsed.state.stepToken).toBeUndefined()
    expect(parsed.state.requiresTotpSetup).toBeUndefined()
  })

  it(
    'FLAG: accessToken (the JWT) is currently written to localStorage via partialize, ' +
    'contradicting prana-portal/CLAUDE.md ("JWT ... store in httpOnly cookie, never localStorage"). ' +
    'This test documents actual behavior as-is — it is not an endorsement. Fixing it requires also ' +
    'reworking lib/api.ts getEmpToken()\'s localStorage fallback (same pattern, empAuth.ts), which ' +
    'exists specifically to read the persisted token back out during a Zustand-hydration race window. ' +
    'Flagged for a deliberate decision, not silently changed here.',
    () => {
      useAuthStore.getState().setAccessToken('jwt-abc123')
      const raw = localStorage.getItem('prana-auth')
      const parsed = JSON.parse(raw as string)
      expect(parsed.state.accessToken).toBe('jwt-abc123')
    },
  )
})

describe('ROLE_COLOR / ROLE_LABEL — every UserRole is covered', () => {
  const roles = ['oa_operator', 'oa_admin', 'chro', 'cfo', 'ciso', 'portal_admin'] as const

  it.each(roles)('%s has both a color and a label', (role) => {
    expect(ROLE_COLOR[role]).toMatch(/^#[0-9A-Fa-f]{6}$/)
    expect(ROLE_LABEL[role]).toBeTruthy()
  })
})
