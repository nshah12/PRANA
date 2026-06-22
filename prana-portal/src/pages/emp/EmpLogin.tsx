/**
 * Employee login — password + TOTP → vault
 *
 * API: POST /auth/employee/login           { identifier, password }   → { next, step_token }
 *      POST /auth/employee/totp            { step_token, code }        → { access_token }
 *      POST /auth/employee/setup/password  { step_token, new_password }→ { next, step_token }
 *      POST /auth/employee/setup/totp/init { step_token }              → { provisioning_uri }
 *      POST /auth/employee/setup/totp/confirm { step_token, code }     → { next, step_token }
 *      POST /auth/employee/setup/consent   { step_token }              → { access_token }
 *
 * Portal always requires TOTP. Biometric is mobile-only.
 */
import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, ShieldCheck, Eye, EyeOff, QrCode, Settings } from 'lucide-react'
import { getApiBase } from '@/lib/api'
import QRCode from 'qrcode'
import { api } from '@/lib/api'
import { useEmpAuthStore } from '@/store/empAuth'

type Step = 'identifier' | 'password' | 'totp' | 'force_password' | 'totp_setup' | 'consent'

const STEP_META: Record<Step, { title: string; sub: string }> = {
  identifier:     { title: 'Your vault, always with you',      sub: 'Enter your email or mobile number.' },
  password:       { title: 'Welcome back',                     sub: 'Enter your PRANA password.' },
  totp:           { title: 'Two-factor check',                 sub: 'Enter the 6-digit code from your authenticator app.' },
  force_password: { title: 'Set your password',               sub: 'Your account needs a new password before you can continue.' },
  totp_setup:     { title: 'Set up authenticator',            sub: 'Scan this QR code with Google Authenticator or Authy.' },
  consent:        { title: 'Data consent',                     sub: 'Review and accept PRANA\'s data processing terms to continue.' },
}

const FLOW_STEPS: Step[] = ['identifier', 'password', 'totp']

export function EmpLogin() {
  const navigate = useNavigate()
  const { setStepToken, setAccessToken } = useEmpAuthStore()

  const [step, setStep]               = useState<Step>('identifier')
  const [identifier, setIdentifier]   = useState('')
  const [password, setPassword]       = useState('')
  const [showPwd, setShowPwd]         = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const [confirmPwd, setConfirmPwd]   = useState('')
  const [totpCode, setTotpCode]       = useState('')
  const [setupCode, setSetupCode]     = useState('')
  const [qrDataUrl, setQrDataUrl]     = useState('')
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState('')
  const stepTokenRef                  = useRef<string>('')

  function saveToken(token: string) {
    stepTokenRef.current = token
    setStepToken(token)
  }

  function clearError() { setError('') }

  // ── Step 1: identifier ────────────────────────────────────────────────────

  async function submitIdentifier() {
    const val = identifier.trim()
    if (!val) { setError('Enter your email or mobile number'); return }
    // Just advance — we pass identifier to the login call with password
    clearError()
    setStep('password')
  }

  // ── Step 2: password ──────────────────────────────────────────────────────

  async function submitPassword() {
    if (!password) { setError('Enter your password'); return }
    clearError(); setLoading(true)
    try {
      const { data } = await api.post('/auth/employee/login', {
        identifier: identifier.trim(),
        password,
      })
      saveToken(data.step_token)
      await advanceToNext(data.next, data.step_token)
    } catch (e: any) {
      const detail = e.response?.data?.detail
      if (detail === 'INVALID_CREDENTIALS') setError('Incorrect password or account not found.')
      else if (detail === 'ACCOUNT_LOCKED') setError('Account locked. Contact support.')
      else if (detail === 'ACCOUNT_NOT_ACTIVE') setError('Account not activated yet.')
      else setError('Sign in failed. Try again.')
    } finally { setLoading(false) }
  }

  // ── Route to correct next step ────────────────────────────────────────────

  async function advanceToNext(next: string, token: string) {
    if (next === 'totp') {
      setStep('totp')
    } else if (next === 'force_password') {
      setStep('force_password')
    } else if (next === 'totp_setup') {
      await loadTotpQr(token)
      setStep('totp_setup')
    } else if (next === 'consent') {
      setStep('consent')
    }
  }

  // ── Step 3a: TOTP ─────────────────────────────────────────────────────────

  async function submitTotp() {
    if (totpCode.length !== 6) { setError('Enter your 6-digit authenticator code'); return }
    clearError(); setLoading(true)
    try {
      const { data } = await api.post('/auth/employee/totp', {
        step_token: stepTokenRef.current,
        code: totpCode,
      })
      await finishLogin(data.access_token)
    } catch (e: any) {
      const detail = e.response?.data?.detail
      if (detail === 'INVALID_TOTP') setError('Incorrect code. Try again.')
      else if (detail === 'ACCOUNT_LOCKED') setError('Account locked after too many attempts.')
      else if (detail === 'STEP_TOKEN_EXPIRED') setError('Session expired. Please sign in again.')
      else setError('Verification failed.')
    } finally { setLoading(false) }
  }

  // ── Setup: Force password change ──────────────────────────────────────────

  async function submitForcePassword() {
    if (newPassword.length < 8) { setError('Password must be at least 8 characters'); return }
    if (newPassword !== confirmPwd) { setError('Passwords do not match'); return }
    clearError(); setLoading(true)
    try {
      const { data } = await api.post('/auth/employee/setup/password', {
        step_token: stepTokenRef.current,
        new_password: newPassword,
      })
      saveToken(data.step_token)
      await advanceToNext(data.next, data.step_token)
    } catch (e: any) {
      setError(e.response?.data?.detail === 'PASSWORD_TOO_SHORT'
        ? 'Password must be at least 8 characters.'
        : 'Failed to update password.')
    } finally { setLoading(false) }
  }

  // ── Setup: TOTP setup ─────────────────────────────────────────────────────

  async function loadTotpQr(token: string) {
    try {
      const { data } = await api.post('/auth/employee/setup/totp/init', { step_token: token })
      const dataUrl = await QRCode.toDataURL(data.provisioning_uri, { width: 200, margin: 1 })
      setQrDataUrl(dataUrl)
    } catch {
      setError('Failed to load QR code. Refresh and try again.')
    }
  }

  async function submitTotpSetup() {
    if (setupCode.length !== 6) { setError('Enter the 6-digit code from your authenticator app'); return }
    clearError(); setLoading(true)
    try {
      const { data } = await api.post('/auth/employee/setup/totp/confirm', {
        step_token: stepTokenRef.current,
        code: setupCode,
      })
      saveToken(data.step_token)
      await advanceToNext(data.next, data.step_token)
    } catch (e: any) {
      const detail = e.response?.data?.detail
      if (detail === 'INVALID_TOTP_CODE') setError('Code incorrect. Make sure your phone\'s time is synced.')
      else setError('Verification failed.')
    } finally { setLoading(false) }
  }

  // ── Setup: Consent ────────────────────────────────────────────────────────

  async function acceptConsent() {
    clearError(); setLoading(true)
    try {
      const { data } = await api.post('/auth/employee/setup/consent', {
        step_token: stepTokenRef.current,
      })
      await finishLogin(data.access_token)
    } catch {
      setError('Failed to record consent. Try again.')
    } finally { setLoading(false) }
  }

  // ── Finish ────────────────────────────────────────────────────────────────

  async function finishLogin(accessToken: string) {
    setAccessToken(accessToken)
    // Decode sub from JWT payload (not secret — just base64) and set minimal user
    // so RequireEmpAuth guard passes. Full profile loaded by EmpVault.
    try {
      const payload = JSON.parse(atob(accessToken.split('.')[1]))
      useEmpAuthStore.getState().setUser({
        userId:    payload.sub ?? '',
        name:      'Employee',
        email:     '',
        mobile:    '',
        pan_token: '',
        vault_url: '',
      })
    } catch { /* guard will bounce on null user */ }
    setStepToken(null)
    navigate('/emp/vault')
  }

  // ── Progress indicator (main flow only) ──────────────────────────────────

  // ── Dev API URL config ────────────────────────────────────────────────────
  const [showApiCfg, setShowApiCfg] = useState(false)
  const [apiUrl, setApiUrl] = useState(() => { try { return localStorage.getItem('PRANA_API_URL') ?? '' } catch { return '' } })

  function saveApiUrl() {
    try {
      if (apiUrl.trim()) localStorage.setItem('PRANA_API_URL', apiUrl.trim())
      else localStorage.removeItem('PRANA_API_URL')
    } catch {}
    window.location.reload()
  }

  const isSetupStep = ['force_password', 'totp_setup', 'consent'].includes(step)
  const progressIdx = FLOW_STEPS.indexOf(step as Step)

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">

        {/* Brand */}
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-cyan-400 flex items-center justify-center">
            <ShieldCheck size={20} className="text-emerald-950" />
          </div>
          <div>
            <p className="text-white font-bold text-lg tracking-tight leading-none">PRANA</p>
            <p className="text-slate-400 text-xs">Employee vault</p>
          </div>
        </div>

        <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 space-y-5">
          <div>
            <h1 className="text-white font-semibold text-lg">{STEP_META[step].title}</h1>
            <p className="text-slate-400 text-sm mt-1">{STEP_META[step].sub}</p>
          </div>

          {/* Progress dots — main flow only */}
          {!isSetupStep && (
            <div className="flex gap-1.5">
              {FLOW_STEPS.map((s, i) => (
                <div key={s} className={`h-1 rounded-full flex-1 transition-colors ${
                  s === step ? 'bg-emerald-400'
                  : i < progressIdx ? 'bg-emerald-700'
                  : 'bg-white/10'
                }`} />
              ))}
            </div>
          )}

          {/* ── Identifier ── */}
          {step === 'identifier' && (
            <div className="space-y-3">
              <input
                type="text" autoComplete="username"
                value={identifier} onChange={e => setIdentifier(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && submitIdentifier()}
                placeholder="Email or mobile number"
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50"
              />
              <button onClick={submitIdentifier}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm">
                Continue →
              </button>
            </div>
          )}

          {/* ── Password ── */}
          {step === 'password' && (
            <div className="space-y-3">
              <div className="relative">
                <input
                  type={showPwd ? 'text' : 'password'} autoComplete="current-password"
                  value={password} onChange={e => setPassword(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && submitPassword()}
                  placeholder="Password"
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 pr-10 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50"
                />
                <button onClick={() => setShowPwd(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white">
                  {showPwd ? <EyeOff size={16}/> : <Eye size={16}/>}
                </button>
              </div>
              <button onClick={submitPassword} disabled={loading}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {loading ? <Loader2 size={16} className="animate-spin" /> : null}
                Continue →
              </button>
              <button onClick={() => { setStep('identifier'); setPassword('') }}
                className="w-full text-slate-400 text-xs hover:text-white">
                ← Change identifier
              </button>
            </div>
          )}

          {/* ── TOTP ── */}
          {step === 'totp' && (
            <div className="space-y-3">
              <input
                type="text" inputMode="numeric" maxLength={6} autoComplete="one-time-code"
                value={totpCode} onChange={e => setTotpCode(e.target.value.replace(/\D/g, ''))}
                onKeyDown={e => e.key === 'Enter' && submitTotp()}
                placeholder="6-digit code"
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50 tracking-widest text-center text-lg"
              />
              <button onClick={submitTotp} disabled={loading}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {loading ? <Loader2 size={16} className="animate-spin" /> : null}
                Sign in to vault →
              </button>
            </div>
          )}

          {/* ── Force password change ── */}
          {step === 'force_password' && (
            <div className="space-y-3">
              <input
                type="password" autoComplete="new-password"
                value={newPassword} onChange={e => setNewPassword(e.target.value)}
                placeholder="New password (min 8 chars)"
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50"
              />
              <input
                type="password" autoComplete="new-password"
                value={confirmPwd} onChange={e => setConfirmPwd(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && submitForcePassword()}
                placeholder="Confirm new password"
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50"
              />
              <button onClick={submitForcePassword} disabled={loading}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {loading ? <Loader2 size={16} className="animate-spin" /> : null}
                Set password →
              </button>
            </div>
          )}

          {/* ── TOTP setup ── */}
          {step === 'totp_setup' && (
            <div className="space-y-4">
              {qrDataUrl ? (
                <div className="flex justify-center">
                  <div className="bg-white p-3 rounded-xl">
                    <img src={qrDataUrl} alt="TOTP QR code" className="w-40 h-40" />
                  </div>
                </div>
              ) : (
                <div className="flex justify-center py-4">
                  <QrCode size={40} className="text-slate-500 animate-pulse" />
                </div>
              )}
              <p className="text-slate-400 text-xs text-center">
                Scan with Google Authenticator, Authy, or any TOTP app.
                Then enter the code below.
              </p>
              <input
                type="text" inputMode="numeric" maxLength={6}
                value={setupCode} onChange={e => setSetupCode(e.target.value.replace(/\D/g, ''))}
                onKeyDown={e => e.key === 'Enter' && submitTotpSetup()}
                placeholder="Enter 6-digit code to confirm"
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50 tracking-widest text-center text-lg"
              />
              <button onClick={submitTotpSetup} disabled={loading || setupCode.length < 6}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {loading ? <Loader2 size={16} className="animate-spin" /> : null}
                Confirm →
              </button>
            </div>
          )}

          {/* ── Consent ── */}
          {step === 'consent' && (
            <div className="space-y-4">
              <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-slate-300 text-xs space-y-2 leading-5">
                <p className="font-semibold text-white">Data Processing Consent</p>
                <p>PRANA stores your career documents (salary slips, Form 16, offer letters) on your behalf.</p>
                <p>Your employer pushes these documents to your vault. You retain full ownership and can request deletion at any time under the <span className="text-emerald-400">DPDP Act 2023</span>.</p>
                <p>Raw salary figures and PAN are never stored in plaintext. AI insights (not raw data) are shown in your vault.</p>
              </div>
              <button onClick={acceptConsent} disabled={loading}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {loading ? <Loader2 size={16} className="animate-spin" /> : null}
                I accept · Open my vault →
              </button>
            </div>
          )}

          {error && <p className="text-red-400 text-xs text-center">{error}</p>}

          <p className="text-slate-500 text-[10px] text-center leading-4">
            Biometric stays on device · No salary figures shown · PRANA will never ask for your password via email
          </p>
        </div>

        {/* API URL config — dev/demo use */}
        <div className="mt-4">
          <button onClick={() => setShowApiCfg(v => !v)}
            className="flex items-center gap-1.5 text-slate-600 hover:text-slate-400 text-[10px] mx-auto transition-colors">
            <Settings size={10} /> API: {getApiBase()}
          </button>
          {showApiCfg && (
            <div className="mt-2 bg-white/5 border border-white/10 rounded-xl p-3 space-y-2">
              <p className="text-slate-400 text-[10px]">
                Run <code className="text-emerald-400">cloudflared tunnel --url http://localhost:8001</code> and paste the HTTPS URL below.
              </p>
              <input
                type="url" value={apiUrl} onChange={e => setApiUrl(e.target.value)}
                placeholder="https://abc-xyz.trycloudflare.com"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-xs placeholder-slate-600 outline-none focus:border-emerald-400/50"
              />
              <div className="flex gap-2">
                <button onClick={saveApiUrl}
                  className="flex-1 bg-emerald-600 text-white text-xs rounded-lg py-1.5 font-medium">
                  Save &amp; reload
                </button>
                <button onClick={() => { setApiUrl(''); localStorage.removeItem('PRANA_API_URL'); window.location.reload() }}
                  className="text-slate-500 text-xs px-3 hover:text-slate-300">
                  Reset
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
