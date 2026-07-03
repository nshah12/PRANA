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
import { tUi } from '@/i18n'

type Step = 'identifier' | 'password' | 'totp' | 'force_password' | 'totp_setup' | 'consent'

function getStepMeta(): Record<Step, { title: string; sub: string }> {
  return {
    identifier:     { title: tUi('EMP_LOGIN_STEP_IDENTIFIER_TITLE'),      sub: tUi('EMP_LOGIN_STEP_IDENTIFIER_SUB') },
    password:       { title: tUi('EMP_LOGIN_STEP_PASSWORD_TITLE'),        sub: tUi('EMP_LOGIN_STEP_PASSWORD_SUB') },
    totp:           { title: tUi('EMP_LOGIN_STEP_TOTP_TITLE'),            sub: tUi('EMP_LOGIN_STEP_TOTP_SUB') },
    force_password: { title: tUi('EMP_LOGIN_STEP_FORCE_PASSWORD_TITLE'),  sub: tUi('EMP_LOGIN_STEP_FORCE_PASSWORD_SUB') },
    totp_setup:     { title: tUi('EMP_LOGIN_STEP_TOTP_SETUP_TITLE'),      sub: tUi('EMP_LOGIN_STEP_TOTP_SETUP_SUB') },
    consent:        { title: tUi('EMP_LOGIN_STEP_CONSENT_TITLE'),         sub: tUi('EMP_LOGIN_STEP_CONSENT_SUB') },
  }
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
    if (!val) { setError(tUi('EMP_LOGIN_ERR_IDENTIFIER_REQUIRED')); return }
    // Just advance — we pass identifier to the login call with password
    clearError()
    setStep('password')
  }

  // ── Step 2: password ──────────────────────────────────────────────────────

  async function submitPassword() {
    if (!password) { setError(tUi('EMP_LOGIN_ERR_PASSWORD_REQUIRED')); return }
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
      if (detail === 'INVALID_CREDENTIALS') setError(tUi('EMP_LOGIN_ERR_INVALID_CREDENTIALS'))
      else if (detail === 'ACCOUNT_LOCKED') setError(tUi('EMP_LOGIN_ERR_ACCOUNT_LOCKED'))
      else if (detail === 'ACCOUNT_NOT_ACTIVE') setError(tUi('EMP_LOGIN_ERR_ACCOUNT_NOT_ACTIVE'))
      else setError(tUi('EMP_LOGIN_ERR_SIGNIN_FAILED'))
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
    if (totpCode.length !== 6) { setError(tUi('EMP_LOGIN_ERR_TOTP_REQUIRED')); return }
    clearError(); setLoading(true)
    try {
      const { data } = await api.post('/auth/employee/totp', {
        step_token: stepTokenRef.current,
        code: totpCode,
      })
      await finishLogin(data.access_token)
    } catch (e: any) {
      const detail = e.response?.data?.detail
      if (detail === 'INVALID_TOTP') setError(tUi('EMP_LOGIN_ERR_TOTP_INVALID'))
      else if (detail === 'ACCOUNT_LOCKED') setError(tUi('EMP_LOGIN_ERR_TOTP_ACCOUNT_LOCKED'))
      else if (detail === 'STEP_TOKEN_EXPIRED') setError(tUi('EMP_LOGIN_ERR_STEP_TOKEN_EXPIRED'))
      else setError(tUi('EMP_LOGIN_ERR_VERIFICATION_FAILED'))
    } finally { setLoading(false) }
  }

  // ── Setup: Force password change ──────────────────────────────────────────

  async function submitForcePassword() {
    if (newPassword.length < 8) { setError(tUi('EMP_LOGIN_ERR_NEW_PASSWORD_TOO_SHORT')); return }
    if (newPassword !== confirmPwd) { setError(tUi('EMP_LOGIN_ERR_PASSWORDS_MISMATCH')); return }
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
        ? tUi('EMP_LOGIN_ERR_PASSWORD_UPDATE_TOO_SHORT')
        : tUi('EMP_LOGIN_ERR_PASSWORD_UPDATE_FAILED'))
    } finally { setLoading(false) }
  }

  // ── Setup: TOTP setup ─────────────────────────────────────────────────────

  async function loadTotpQr(token: string) {
    try {
      const { data } = await api.post('/auth/employee/setup/totp/init', { step_token: token })
      const dataUrl = await QRCode.toDataURL(data.provisioning_uri, { width: 200, margin: 1 })
      setQrDataUrl(dataUrl)
    } catch {
      setError(tUi('EMP_LOGIN_ERR_QR_LOAD_FAILED'))
    }
  }

  async function submitTotpSetup() {
    if (setupCode.length !== 6) { setError(tUi('EMP_LOGIN_ERR_SETUP_CODE_REQUIRED')); return }
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
      if (detail === 'INVALID_TOTP_CODE') setError(tUi('EMP_LOGIN_ERR_SETUP_CODE_INVALID'))
      else setError(tUi('EMP_LOGIN_ERR_VERIFICATION_FAILED'))
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
      setError(tUi('EMP_LOGIN_ERR_CONSENT_FAILED'))
    } finally { setLoading(false) }
  }

  // ── Finish ────────────────────────────────────────────────────────────────

  async function finishLogin(accessToken: string) {
    let userId = ''
    try {
      const b64 = accessToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
      const payload = JSON.parse(atob(b64))
      userId = payload.sub ?? ''
    } catch {}

    const user = { userId, name: 'Employee', email: '', mobile: '', pan_token: '', vault_url: '' }

    // Write directly to localStorage FIRST so the next page load reads the token
    // regardless of Zustand hydration timing. Zustand persist key format: { state, version }
    try {
      localStorage.setItem('prana-emp-auth', JSON.stringify({ state: { user, accessToken }, version: 0 }))
    } catch {}

    // Also update Zustand store (for same-page state, not relied on after reload)
    setAccessToken(accessToken)
    useEmpAuthStore.getState().setUser(user)
    setStepToken(null)

    window.location.href = '/emp/vault'
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
            <p className="text-slate-400 text-xs">{tUi('EMP_LOGIN_BRAND_SUBTITLE')}</p>
          </div>
        </div>

        <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 space-y-5">
          <div>
            <h1 className="text-white font-semibold text-lg">{getStepMeta()[step].title}</h1>
            <p className="text-slate-400 text-sm mt-1">{getStepMeta()[step].sub}</p>
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
                placeholder={tUi('EMP_LOGIN_PLACEHOLDER_IDENTIFIER')}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50"
              />
              <button onClick={submitIdentifier}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm">
                {tUi('EMP_LOGIN_CONTINUE')}
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
                  placeholder={tUi('EMP_LOGIN_PASSWORD_PLACEHOLDER')}
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
                {tUi('EMP_LOGIN_CONTINUE')}
              </button>
              <button onClick={() => { setStep('identifier'); setPassword('') }}
                className="w-full text-slate-400 text-xs hover:text-white">
                {tUi('EMP_LOGIN_CHANGE_IDENTIFIER')}
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
                placeholder={tUi('EMP_LOGIN_TOTP_PLACEHOLDER')}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50 tracking-widest text-center text-lg"
              />
              <button onClick={submitTotp} disabled={loading}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {loading ? <Loader2 size={16} className="animate-spin" /> : null}
                {tUi('EMP_LOGIN_SIGNIN_TO_VAULT')}
              </button>
            </div>
          )}

          {/* ── Force password change ── */}
          {step === 'force_password' && (
            <div className="space-y-3">
              <input
                type="password" autoComplete="new-password"
                value={newPassword} onChange={e => setNewPassword(e.target.value)}
                placeholder={tUi('EMP_LOGIN_NEW_PASSWORD_PLACEHOLDER')}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50"
              />
              <input
                type="password" autoComplete="new-password"
                value={confirmPwd} onChange={e => setConfirmPwd(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && submitForcePassword()}
                placeholder={tUi('EMP_LOGIN_PLACEHOLDER_CONFIRM_PWD')}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50"
              />
              <button onClick={submitForcePassword} disabled={loading}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {loading ? <Loader2 size={16} className="animate-spin" /> : null}
                {tUi('EMP_LOGIN_SET_PASSWORD_BTN')}
              </button>
            </div>
          )}

          {/* ── TOTP setup ── */}
          {step === 'totp_setup' && (
            <div className="space-y-4">
              {qrDataUrl ? (
                <div className="flex justify-center">
                  <div className="bg-white p-3 rounded-xl">
                    <img src={qrDataUrl} alt={tUi('EMP_LOGIN_QR_ALT')} className="w-40 h-40" />
                  </div>
                </div>
              ) : (
                <div className="flex justify-center py-4">
                  <QrCode size={40} className="text-slate-500 animate-pulse" />
                </div>
              )}
              <p className="text-slate-400 text-xs text-center">
                {tUi('EMP_LOGIN_TOTP_SETUP_HELP')}
              </p>
              <input
                type="text" inputMode="numeric" maxLength={6}
                value={setupCode} onChange={e => setSetupCode(e.target.value.replace(/\D/g, ''))}
                onKeyDown={e => e.key === 'Enter' && submitTotpSetup()}
                placeholder={tUi('EMP_LOGIN_PLACEHOLDER_CONFIRM_CODE')}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50 tracking-widest text-center text-lg"
              />
              <button onClick={submitTotpSetup} disabled={loading || setupCode.length < 6}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {loading ? <Loader2 size={16} className="animate-spin" /> : null}
                {tUi('EMP_LOGIN_CONFIRM_BTN')}
              </button>
            </div>
          )}

          {/* ── Consent ── */}
          {step === 'consent' && (
            <div className="space-y-4">
              <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-slate-300 text-xs space-y-2 leading-5">
                <p className="font-semibold text-white">{tUi('EMP_LOGIN_CONSENT_HEADING')}</p>
                <p>{tUi('EMP_LOGIN_CONSENT_P1')}</p>
                <p>{tUi('EMP_LOGIN_CONSENT_P2_PREFIX')} <span className="text-emerald-400">DPDP Act 2023</span>.</p>
                <p>{tUi('EMP_LOGIN_CONSENT_P3')}</p>
              </div>
              <button onClick={acceptConsent} disabled={loading}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {loading ? <Loader2 size={16} className="animate-spin" /> : null}
                {tUi('EMP_LOGIN_ACCEPT_BTN')}
              </button>
            </div>
          )}

          {error && <p className="text-red-400 text-xs text-center">{error}</p>}

          <p className="text-slate-500 text-[10px] text-center leading-4">
            {tUi('EMP_LOGIN_FOOTER_NOTE')}
          </p>
        </div>

        {/* API URL config — dev/demo use */}
        <div className="mt-4">
          <button onClick={() => setShowApiCfg(v => !v)}
            className="flex items-center gap-1.5 text-slate-600 hover:text-slate-400 text-[10px] mx-auto transition-colors">
            <Settings size={10} /> {tUi('EMP_LOGIN_DEV_API_LABEL')} {getApiBase()}
          </button>
          {showApiCfg && (
            <div className="mt-2 bg-white/5 border border-white/10 rounded-xl p-3 space-y-2">
              <p className="text-slate-400 text-[10px]">
                {tUi('EMP_LOGIN_DEV_TUNNEL_PREFIX')} <code className="text-emerald-400">cloudflared tunnel --url http://localhost:8001</code> {tUi('EMP_LOGIN_DEV_TUNNEL_SUFFIX')}
              </p>
              <input
                type="url" value={apiUrl} onChange={e => setApiUrl(e.target.value)}
                placeholder="https://abc-xyz.trycloudflare.com"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-xs placeholder-slate-600 outline-none focus:border-emerald-400/50"
              />
              <div className="flex gap-2">
                <button onClick={saveApiUrl}
                  className="flex-1 bg-emerald-600 text-white text-xs rounded-lg py-1.5 font-medium">
                  {tUi('EMP_LOGIN_SAVE_RELOAD')}
                </button>
                <button onClick={() => { setApiUrl(''); localStorage.removeItem('PRANA_API_URL'); window.location.reload() }}
                  className="text-slate-500 text-xs px-3 hover:text-slate-300">
                  {tUi('EMP_LOGIN_RESET_BTN')}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
