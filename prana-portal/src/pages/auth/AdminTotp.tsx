import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import QRCode from 'qrcode'
import { api } from '@/lib/api'
import { useAuthStore, AuthUser } from '@/store/auth'

function decodeJwtUser(token: string): AuthUser | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return {
      userId: payload.sub,
      email: '',
      displayName: 'Portal Admin',
      role: payload.role,
      tenantId: payload.tenant_id ?? null,
      tenantName: null,
    }
  } catch { return null }
}

// PA lockout is permanent (no auto-unlock) — requires another PA to unlock manually
function LockoutScreen({ onBack }: { onBack: () => void }) {
  return (
    <div className="min-h-screen bg-[#0F172A] flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-3xl border border-red-100 shadow-xl p-8 text-center">
        <div className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center text-3xl bg-red-50 border border-red-100">
          🔒
        </div>
        <h1 className="text-xl font-bold text-slate-900 mb-2">Account locked</h1>
        <p className="text-slate-500 text-sm leading-relaxed mb-6">
          Your Portal Admin account has been locked after <strong>3 failed TOTP attempts</strong>.
          PA accounts do not auto-unlock.
        </p>

        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-4 mb-6 text-left space-y-2">
          <p className="text-xs font-bold text-amber-700 uppercase tracking-wider">How to regain access</p>
          <p className="text-xs text-amber-700 leading-relaxed">
            Another Portal Admin must unlock your account via the{' '}
            <span className="font-mono bg-amber-100 px-1.5 py-0.5 rounded">Admin Console → OA Emergency</span>{' '}
            screen, or contact:
          </p>
          <a href="mailto:security@prana.in"
             className="text-xs font-mono font-semibold text-amber-700 underline">
            security@prana.in
          </a>
        </div>

        <div className="bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 mb-6 text-xs text-slate-500 text-left">
          This lockout event has been recorded in the platform audit log.
        </div>

        <button onClick={onBack}
          className="text-sm text-slate-400 hover:text-slate-600">
          ← Back to login
        </button>
      </div>
    </div>
  )
}

export function AdminTotp() {
  const navigate = useNavigate()
  const { stepToken, requiresTotpSetup, setStepToken, setRequiresTotpSetup, setUser, setAccessToken } = useAuthStore()

  const [setupPhase, setSetupPhase]   = useState<'loading' | 'qr' | 'verify'>('loading')
  const [qrDataUrl, setQrDataUrl]     = useState('')
  const [backupCodes, setBackupCodes] = useState<string[]>([])
  const [setupToken, setSetupToken]   = useState('')
  const [showBackup, setShowBackup]   = useState(false)
  const [copied, setCopied]           = useState(false)

  const [code, setCode]           = useState('')
  const [error, setError]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [isLocked, setIsLocked]   = useState(false)
  const [failCount, setFailCount] = useState(0)
  const PA_LOCK_THRESHOLD = 3   // stricter than OA (5) — matches pa_totp_lock_threshold
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!stepToken) { navigate('/admin/login'); return }
    if (requiresTotpSetup) {
      api.post('/auth/admin/totp-setup/init', { step_token: stepToken })
        .then(async (res: any) => {
          const dataUrl = await QRCode.toDataURL(res.data.provisioning_uri, {
            width: 200, margin: 1, color: { dark: '#0F172A', light: '#FFFFFF' }
          })
          setQrDataUrl(dataUrl)
          setBackupCodes(res.data.backup_codes)
          setSetupToken(res.data.setup_token)
          setSetupPhase('qr')
        })
        .catch(() => {
          setError('Failed to initialise TOTP setup. Please try again.')
          setSetupPhase('qr')
        })
    } else {
      setSetupPhase('verify')
    }
  }, [])

  useEffect(() => {
    if (setupPhase === 'verify') inputRef.current?.focus()
  }, [setupPhase])

  if (!stepToken) return null

  if (isLocked) {
    return <LockoutScreen onBack={() => navigate('/admin/login')} />
  }

  function copyBackupCodes() {
    navigator.clipboard.writeText(backupCodes.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function onVerify(e: React.FormEvent) {
    e.preventDefault()
    if (code.length !== 6) return
    setLoading(true); setError('')
    try {
      let token: string
      if (requiresTotpSetup) {
        const res: any = await api.post('/auth/admin/totp-setup/confirm', { setup_token: setupToken, code })
        token = res.data.access_token
        setRequiresTotpSetup(false)
      } else {
        const res: any = await api.post('/auth/admin/totp', { step_token: stepToken, code })
        token = res.data.access_token
      }
      setAccessToken(token)
      const u = decodeJwtUser(token)
      if (u) setUser(u)
      setStepToken(null)
      navigate('/admin/dashboard')
    } catch (e: any) {
      const detail = e.response?.data?.detail
      if (detail === 'ACCOUNT_LOCKED') {
        setIsLocked(true)
      } else if (detail === 'INVALID_TOTP' || detail === 'INVALID_CODE') {
        const next = failCount + 1
        setFailCount(next)
        const remaining = PA_LOCK_THRESHOLD - next
        if (remaining <= 1 && remaining > 0) {
          setError(`Incorrect code. ${remaining} attempt remaining — account will lock permanently.`)
        } else if (remaining > 1) {
          setError(`Incorrect code. ${remaining} attempts remaining before permanent lockout.`)
        } else {
          setError('Incorrect code.')
        }
      } else if (detail === 'STEP_TOKEN_EXPIRED' || detail === 'SETUP_TOKEN_EXPIRED') {
        setError('Session expired. Please go back and sign in again.')
      } else {
        setError(detail ?? 'Invalid code. Please try again.')
      }
      setCode('')
    } finally { setLoading(false) }
  }

  // ── QR setup screen ───────────────────────────────────────────────────────
  if (requiresTotpSetup && setupPhase !== 'verify') {
    return (
      <div className="min-h-screen bg-[#0F172A] flex items-center justify-center p-4">
        <div className="w-full max-w-sm">
          <div className="mb-6 text-center">
            <span className="font-mono text-2xl font-bold text-white">
              prana.<span className="text-amber-400">in</span>
            </span>
            <p className="text-slate-500 text-xs mt-1">Platform Admin Console</p>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl p-7 space-y-5">
            <div>
              <h1 className="text-lg font-semibold text-slate-800">Set up authenticator</h1>
              <div className="mt-2 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                <p className="text-xs text-amber-700 font-medium">
                  PA accounts lock after <strong>3</strong> failed attempts. No auto-unlock.
                </p>
              </div>
            </div>

            {setupPhase === 'loading' && (
              <div className="flex justify-center py-8">
                <div className="w-8 h-8 border-4 border-amber-200 border-t-amber-500 rounded-full animate-spin" />
              </div>
            )}

            {setupPhase === 'qr' && qrDataUrl && (
              <>
                <div className="flex justify-center">
                  <div className="p-3 rounded-xl border border-slate-100 bg-white shadow-inner">
                    <img src={qrDataUrl} alt="TOTP QR code" className="rounded-lg" />
                  </div>
                </div>

                {/* Backup codes */}
                <div className="border border-slate-200 rounded-xl overflow-hidden">
                  <button type="button" onClick={() => setShowBackup(v => !v)}
                    className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 text-left">
                    <div className="flex items-center gap-2">
                      <span className="text-sm">🔑</span>
                      <span className="text-sm font-medium text-slate-700">Backup codes</span>
                      <span className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-full px-2 py-0.5">
                        Required — no auto-unlock
                      </span>
                    </div>
                    <span className="text-slate-400 text-xs">{showBackup ? '▲' : '▼'}</span>
                  </button>
                  {showBackup && (
                    <div className="border-t border-slate-100 p-4">
                      <div className="grid grid-cols-2 gap-2 mb-3">
                        {backupCodes.map(c => (
                          <span key={c} className="font-mono text-xs text-slate-700 bg-slate-50
                                                   rounded-lg px-3 py-2 text-center border border-slate-100">
                            {c}
                          </span>
                        ))}
                      </div>
                      <button onClick={copyBackupCodes}
                        className="w-full text-xs font-medium text-amber-600 border border-amber-100
                                   rounded-xl py-2 hover:bg-amber-50 transition-colors">
                        {copied ? '✓ Copied!' : 'Copy all codes'}
                      </button>
                    </div>
                  )}
                </div>

                {error && (
                  <p className="text-sm text-red-600 bg-red-50 rounded-xl px-4 py-3">{error}</p>
                )}

                <button type="button"
                  onClick={() => { setSetupPhase('verify'); setCode('') }}
                  className="w-full text-white font-semibold py-2.5 rounded-xl hover:opacity-90 transition-opacity"
                  style={{ background: 'linear-gradient(135deg, #D97706, #B45309)' }}>
                  I've scanned it — enter code →
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ── TOTP code entry ────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0F172A] flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="font-mono text-2xl font-bold text-white">
            prana.<span className="text-amber-400">in</span>
          </span>
          <p className="text-slate-500 text-xs mt-1">Platform Admin Console</p>
        </div>

        <form onSubmit={onVerify}
              className="bg-white rounded-2xl border border-slate-200 shadow-xl p-7 space-y-5">
          <div>
            <h1 className="text-lg font-semibold text-slate-800">
              {requiresTotpSetup ? 'Confirm your authenticator' : 'Two-factor authentication'}
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              {requiresTotpSetup
                ? 'Enter the 6-digit code to activate 2FA on your account.'
                : 'Enter the 6-digit code from your authenticator app.'}
            </p>
          </div>

          {/* Attempt warning bar — only show once failed once */}
          {failCount > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-2.5">
              <p className="text-xs font-semibold text-red-700">
                {PA_LOCK_THRESHOLD - failCount} of {PA_LOCK_THRESHOLD} attempts remaining
              </p>
              <div className="flex gap-1 mt-1.5">
                {Array.from({ length: PA_LOCK_THRESHOLD }).map((_, i) => (
                  <div key={i}
                    className={`h-1.5 flex-1 rounded-full ${
                      i < failCount ? 'bg-red-400' : 'bg-red-100'
                    }`} />
                ))}
              </div>
            </div>
          )}

          <input
            ref={inputRef}
            value={code}
            onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            type="text"
            inputMode="numeric"
            placeholder="000 000"
            className="w-full border-2 border-slate-200 rounded-2xl px-4 py-5 text-3xl
                       font-mono text-center tracking-[0.6em] focus:outline-none
                       focus:border-amber-400 bg-slate-50 focus:bg-white transition-colors"
          />

          {error && (
            <div className="bg-red-50 border border-red-100 rounded-xl px-4 py-3 flex items-start gap-2">
              <span className="text-red-500 text-sm">⚠</span>
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={loading || code.length !== 6}
            className="w-full text-white font-semibold py-3 rounded-xl transition-opacity
                       disabled:opacity-40 hover:opacity-90"
            style={{ background: 'linear-gradient(135deg, #D97706, #B45309)' }}>
            {loading ? 'Verifying…' : requiresTotpSetup ? 'Activate & sign in →' : 'Verify →'}
          </button>

          <div className="text-center">
            {requiresTotpSetup ? (
              <button type="button" onClick={() => setSetupPhase('qr')}
                className="text-sm text-slate-400 hover:text-slate-600">
                ← Back to QR code
              </button>
            ) : (
              <button type="button" onClick={() => navigate('/admin/login')}
                className="text-sm text-slate-400 hover:text-slate-600">
                ← Back to login
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  )
}
