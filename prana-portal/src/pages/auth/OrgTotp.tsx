import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import QRCode from 'qrcode'
import { api } from '@/lib/api'
import { useAuthStore, AuthUser } from '@/store/auth'

// Lockout screen — shown when ACCOUNT_LOCKED error received
// Countdown from lockout_cooldown_minutes (default 30 from platform_config)
function LockoutScreen({ onBack }: { onBack: () => void }) {
  const LOCK_MINUTES = 30
  const [remaining, setRemaining] = useState(LOCK_MINUTES * 60)

  useEffect(() => {
    const id = setInterval(() => setRemaining(s => Math.max(0, s - 1)), 1000)
    return () => clearInterval(id)
  }, [])

  const mm = String(Math.floor(remaining / 60)).padStart(2, '0')
  const ss = String(remaining % 60).padStart(2, '0')

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-3xl border border-red-100 shadow-sm p-8 text-center">
        <div className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center text-3xl bg-red-50 border border-red-100">
          🔒
        </div>
        <h1 className="text-xl font-bold text-slate-900 mb-2">Account temporarily locked</h1>
        <p className="text-slate-500 text-sm leading-relaxed mb-6">
          Too many incorrect TOTP attempts. Your account has been locked for{' '}
          <strong>{LOCK_MINUTES} minutes</strong> to protect against unauthorised access.
        </p>

        {remaining > 0 ? (
          <div className="bg-red-50 border border-red-100 rounded-2xl px-6 py-4 mb-6 inline-block">
            <p className="text-xs text-red-500 uppercase tracking-widest mb-1 font-semibold">Unlocks in</p>
            <p className="text-3xl font-mono font-bold text-red-600">{mm}:{ss}</p>
          </div>
        ) : (
          <div className="bg-emerald-50 border border-emerald-100 rounded-2xl px-6 py-4 mb-6">
            <p className="text-sm text-emerald-700 font-medium">Lock period expired — you can try again.</p>
          </div>
        )}

        <div className="bg-amber-50 border border-amber-100 rounded-xl px-4 py-3 mb-6 text-left">
          <p className="text-xs font-semibold text-amber-700 mb-1">Need immediate access?</p>
          <p className="text-xs text-amber-600 leading-relaxed">
            Contact your OA-Admin to unlock your account manually via the User Management screen.
          </p>
        </div>

        <button onClick={onBack}
          className="text-sm text-slate-400 hover:text-slate-600">
          ← Back to login
        </button>
      </div>
    </div>
  )
}

function decodeJwtUser(token: string): AuthUser | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return {
      userId: payload.sub,
      email: '',
      displayName: payload.role ?? '',
      role: payload.role,
      tenantId: payload.tenant_id ?? null,
      tenantName: null,
    }
  } catch { return null }
}

// Step indicator for QR setup flow
function SetupSteps({ active }: { active: 0 | 1 | 2 }) {
  const steps = ['Install app', 'Scan QR', 'Enter code']
  return (
    <div className="flex items-center justify-center gap-0 mb-8">
      {steps.map((s, i) => (
        <div key={i} className="flex items-center">
          <div className="flex flex-col items-center">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold
                            transition-all ${i <= active
                              ? 'text-white'
                              : 'bg-slate-100 text-slate-400'}`}
              style={i <= active ? { background: 'linear-gradient(135deg, #6366F1, #22D3EE)' } : {}}>
              {i < active ? '✓' : i + 1}
            </div>
            <span className={`text-[10px] mt-1 font-medium ${i <= active ? 'text-indigo-600' : 'text-slate-400'}`}>
              {s}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div className={`w-16 h-px mx-1 mb-4 ${i < active ? 'bg-indigo-400' : 'bg-slate-200'}`} />
          )}
        </div>
      ))}
    </div>
  )
}

const TOTP_APPS = [
  { name: 'Google Authenticator', icon: '🔐', note: 'iOS & Android' },
  { name: 'Microsoft Authenticator', icon: '🛡', note: 'iOS & Android' },
  { name: 'Authy', icon: '🔑', note: 'iOS, Android & Desktop' },
]

export function OrgTotp() {
  const navigate = useNavigate()
  const { stepToken, requiresTotpSetup, setStepToken, setRequiresTotpSetup, setUser, setAccessToken } = useAuthStore()

  const [setupPhase, setSetupPhase]   = useState<'loading' | 'install' | 'qr' | 'verify'>('loading')
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
  const LOCK_THRESHOLD = 5   // matches oa_totp_lock_threshold platform_config default
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!stepToken) { navigate('/org/login'); return }
    if (requiresTotpSetup) {
      setSetupPhase('install')
    } else {
      setSetupPhase('verify')
    }
  }, [])

  useEffect(() => {
    if (setupPhase === 'verify') inputRef.current?.focus()
  }, [setupPhase])

  async function loadQr() {
    setSetupPhase('loading')
    try {
      const res: any = await api.post('/auth/org/totp-setup/init', { step_token: stepToken })
      const uri = res.data.provisioning_uri
      const dataUrl = await QRCode.toDataURL(uri, { width: 220, margin: 2, color: { dark: '#0F172A', light: '#FFFFFF' } })
      setQrDataUrl(dataUrl)
      setBackupCodes(res.data.backup_codes)
      setSetupToken(res.data.setup_token)
      setSetupPhase('qr')
    } catch {
      setError('Failed to initialise TOTP setup. Please go back and try again.')
      setSetupPhase('qr')
    }
  }

  if (!stepToken) return null

  if (isLocked) {
    return <LockoutScreen onBack={() => navigate('/org/login')} />
  }

  async function onVerify(e: React.FormEvent) {
    e.preventDefault()
    if (code.length !== 6) return
    setLoading(true); setError('')
    try {
      let token: string
      if (requiresTotpSetup) {
        const res: any = await api.post('/auth/org/totp-setup/confirm', { setup_token: setupToken, code })
        token = res.data.access_token
        setRequiresTotpSetup(false)
      } else {
        const res: any = await api.post('/auth/org/totp', { step_token: stepToken, code })
        token = res.data.access_token
      }
      setAccessToken(token)
      const u = decodeJwtUser(token)
      if (u) setUser(u)
      setStepToken(null)
      navigate('/org/dashboard')
    } catch (e: any) {
      const detail = e.response?.data?.detail
      if (detail === 'ACCOUNT_LOCKED') {
        setIsLocked(true)
      } else if (detail === 'INVALID_TOTP') {
        const next = failCount + 1
        setFailCount(next)
        const remaining = LOCK_THRESHOLD - next
        if (remaining <= 2 && remaining > 0) {
          setError(`Incorrect code. ${remaining} attempt${remaining === 1 ? '' : 's'} remaining before lockout.`)
        } else {
          setError('Incorrect code. Please check your authenticator app and try again.')
        }
      } else if (detail === 'STEP_TOKEN_EXPIRED') {
        setError('Session expired. Please go back and log in again.')
      } else {
        setError(detail ?? 'Invalid code. Please try again.')
      }
      setCode('')
    } finally {
      setLoading(false)
    }
  }

  function copyBackupCodes() {
    navigator.clipboard.writeText(backupCodes.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const cardClass = "w-full max-w-md bg-white rounded-3xl border border-slate-200 shadow-sm"

  // ── Step 0: Install app ───────────────────────────────────────────────
  if (requiresTotpSetup && setupPhase === 'install') {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className={cardClass}>
          <div className="p-8">
            <SetupSteps active={0} />

            <div className="text-center mb-6">
              <div className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center text-3xl"
                style={{ background: 'linear-gradient(135deg, #6366F1, #22D3EE)' }}>
                📱
              </div>
              <h1 className="text-xl font-bold text-slate-900 mb-2">Install an authenticator app</h1>
              <p className="text-slate-500 text-sm leading-relaxed">
                Download one of these free TOTP apps before scanning the QR code.
                If you already have one, skip ahead.
              </p>
            </div>

            <div className="space-y-2 mb-6">
              {TOTP_APPS.map(a => (
                <div key={a.name} className="flex items-center gap-3 bg-slate-50 rounded-xl p-3 border border-slate-100">
                  <span className="text-xl">{a.icon}</span>
                  <div>
                    <p className="text-sm font-medium text-slate-800">{a.name}</p>
                    <p className="text-xs text-slate-400">{a.note}</p>
                  </div>
                </div>
              ))}
            </div>

            <button onClick={loadQr}
              className="w-full text-white font-semibold py-3 rounded-xl hover:opacity-90 transition-opacity"
              style={{ background: 'linear-gradient(135deg, #6366F1, #22D3EE)' }}>
              I have an app — show QR code →
            </button>

            <button type="button" onClick={() => navigate('/org/login')}
              className="w-full mt-3 text-sm text-slate-400 hover:text-slate-600 text-center">
              ← Back to login
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ── Step 1: QR scan ───────────────────────────────────────────────────
  if (requiresTotpSetup && (setupPhase === 'loading' || setupPhase === 'qr')) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className={cardClass}>
          <div className="p-8">
            <SetupSteps active={1} />

            <div className="text-center mb-6">
              <h1 className="text-xl font-bold text-slate-900 mb-2">Scan the QR code</h1>
              <p className="text-slate-500 text-sm">
                Open your authenticator app, tap <strong>+</strong> or <strong>Add account</strong>,
                then scan this code.
              </p>
            </div>

            {setupPhase === 'loading' ? (
              <div className="flex justify-center py-12">
                <div className="w-10 h-10 border-4 border-indigo-100 border-t-indigo-500 rounded-full animate-spin" />
              </div>
            ) : qrDataUrl ? (
              <>
                {/* QR with decorative border */}
                <div className="flex justify-center mb-5">
                  <div className="p-4 rounded-2xl border-2 border-indigo-100 bg-white shadow-inner">
                    <img src={qrDataUrl} alt="TOTP QR code" className="rounded-lg" />
                  </div>
                </div>

                {/* Backup codes */}
                <div className="border border-slate-200 rounded-2xl overflow-hidden mb-4">
                  <button type="button" onClick={() => setShowBackup(v => !v)}
                    className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 text-left">
                    <div className="flex items-center gap-2">
                      <span className="text-sm">🔑</span>
                      <span className="text-sm font-medium text-slate-700">Backup codes</span>
                      <span className="text-xs text-amber-600 bg-amber-50 border border-amber-100 rounded-full px-2 py-0.5">
                        Save these now
                      </span>
                    </div>
                    <span className="text-slate-400 text-xs">{showBackup ? '▲ Hide' : '▼ Show'}</span>
                  </button>
                  {showBackup && (
                    <div className="border-t border-slate-100 p-4">
                      <div className="grid grid-cols-2 gap-2 mb-3">
                        {backupCodes.map(c => (
                          <span key={c} className="font-mono text-xs text-slate-700 bg-slate-50 rounded-lg
                                                   px-3 py-2 text-center border border-slate-100">
                            {c}
                          </span>
                        ))}
                      </div>
                      <button onClick={copyBackupCodes}
                        className="w-full text-xs font-medium text-indigo-600 border border-indigo-100
                                   rounded-xl py-2 hover:bg-indigo-50 transition-colors">
                        {copied ? '✓ Copied!' : 'Copy all codes'}
                      </button>
                    </div>
                  )}
                </div>

                {error && (
                  <p className="text-sm text-red-600 bg-red-50 rounded-xl px-4 py-3 mb-4">{error}</p>
                )}

                <button onClick={() => { setSetupPhase('verify'); setCode('') }}
                  className="w-full text-white font-semibold py-3 rounded-xl hover:opacity-90 transition-opacity"
                  style={{ background: 'linear-gradient(135deg, #6366F1, #22D3EE)' }}>
                  I've scanned it — enter code →
                </button>

                <button type="button" onClick={() => setSetupPhase('install')}
                  className="w-full mt-3 text-sm text-slate-400 hover:text-slate-600 text-center">
                  ← Back
                </button>
              </>
            ) : (
              <p className="text-sm text-red-600 bg-red-50 rounded-xl px-4 py-3 text-center">{error}</p>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ── Step 2 / Normal verify: Enter 6-digit code ────────────────────────
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className={cardClass}>
        <div className="p-8">
          {requiresTotpSetup && <SetupSteps active={2} />}

          <div className="text-center mb-6">
            <div className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center text-3xl"
              style={{ background: 'linear-gradient(135deg, #6366F1, #22D3EE)' }}>
              🔐
            </div>
            <h1 className="text-xl font-bold text-slate-900 mb-2">
              {requiresTotpSetup ? 'Confirm your authenticator' : 'Two-factor authentication'}
            </h1>
            <p className="text-slate-500 text-sm leading-relaxed">
              {requiresTotpSetup
                ? 'Enter the 6-digit code from your authenticator app to activate 2FA on your account.'
                : 'Enter the 6-digit code shown in your authenticator app.'}
            </p>
          </div>

          <form onSubmit={onVerify} className="space-y-4">
            {/* 6-digit input */}
            <div>
              <input
                ref={inputRef}
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                type="text"
                inputMode="numeric"
                placeholder="000 000"
                className="w-full border-2 border-slate-200 rounded-2xl px-4 py-5 text-3xl
                           font-mono text-center tracking-[0.6em] focus:outline-none
                           focus:border-indigo-400 bg-slate-50 focus:bg-white transition-colors"
              />
              <p className="text-center text-xs text-slate-400 mt-2">
                Code refreshes every 30 seconds in your app
              </p>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-100 rounded-xl px-4 py-3 flex items-center gap-2">
                <span className="text-red-500">⚠</span>
                <p className="text-sm text-red-600">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading || code.length !== 6}
              className="w-full text-white font-semibold py-3 rounded-xl transition-opacity
                         disabled:opacity-40 hover:opacity-90"
              style={{ background: 'linear-gradient(135deg, #6366F1, #22D3EE)' }}>
              {loading ? 'Verifying…' : requiresTotpSetup ? 'Activate & sign in →' : 'Verify →'}
            </button>
          </form>

          <div className="mt-4 text-center space-y-1">
            {requiresTotpSetup && (
              <button type="button" onClick={() => setSetupPhase('qr')}
                className="text-sm text-slate-400 hover:text-slate-600 block w-full">
                ← Back to QR code
              </button>
            )}
            {!requiresTotpSetup && (
              <button type="button" onClick={() => navigate('/org/login')}
                className="text-sm text-slate-400 hover:text-slate-600 block w-full">
                ← Back to login
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
