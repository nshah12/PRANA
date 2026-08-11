/**
 * Landing page for the EMPLOYEE_CREDENTIALS_ISSUED email/SMS link.
 *
 * The server-generated temp password (routers/employees.py) is never disclosed
 * anywhere — this is the only way a newly onboarded employee ever gets a usable
 * password. A web page, not a mobile deep link, since a brand-new employee has
 * very likely not installed the app yet.
 *
 * API: POST /auth/employee/password-setup/verify { token }              → { valid, email }
 *      POST /auth/employee/password-setup        { token, new_password } → { message }
 */
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { ShieldCheck } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

interface Form { new_password: string; confirm: string }

const RULES = [
  { label: 'At least 8 characters',                test: (p: string) => p.length >= 8 },
  { label: 'One uppercase letter (A–Z)',           test: (p: string) => /[A-Z]/.test(p) },
  { label: 'One number (0–9)',                     test: (p: string) => /\d/.test(p) },
  { label: 'One special character (!@#$…)',        test: (p: string) => /[^a-zA-Z0-9]/.test(p) },
]

function StrengthBar({ password }: { password: string }) {
  const passed = RULES.filter(r => r.test(password)).length
  const colors = ['bg-red-400', 'bg-amber-400', 'bg-amber-400', 'bg-emerald-400', 'bg-emerald-500']
  const labels = ['', 'Weak', 'Fair', 'Good', 'Strong']

  return (
    <div className="space-y-2">
      <div className="flex gap-1">
        {[0, 1, 2, 3].map(i => (
          <div key={i}
            className={`h-1 flex-1 rounded-full transition-colors duration-300 ${
              i < passed ? colors[passed] : 'bg-white/10'
            }`} />
        ))}
      </div>
      {password.length > 0 && (
        <p className={`text-xs font-medium ${passed >= 4 ? 'text-emerald-400' : passed >= 2 ? 'text-amber-400' : 'text-red-400'}`}>
          {labels[passed]}
        </p>
      )}
    </div>
  )
}

type LinkState = 'checking' | 'invalid' | 'valid' | 'done'

export function EmpSetPassword() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''

  const [linkState, setLinkState] = useState<LinkState>('checking')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const { register, handleSubmit, watch, formState: { isSubmitting } } = useForm<Form>()
  const password = watch('new_password', '')
  const allRulesPassed = RULES.every(r => r.test(password))

  useEffect(() => {
    if (!token) { setLinkState('invalid'); return }
    api.post('/auth/employee/password-setup/verify', { token })
      .then(res => { setEmail(res.data.email); setLinkState('valid') })
      .catch(() => setLinkState('invalid'))
  }, [token])

  async function onSubmit(data: Form) {
    if (data.new_password !== data.confirm) { setError(tUi('EMP_SET_PASSWORD_MISMATCH')); return }
    if (!allRulesPassed) { setError(tUi('RESET_PASSWORD_REQUIREMENTS_NOT_MET')); return }
    setError('')
    try {
      await api.post('/auth/employee/password-setup', { token, new_password: data.new_password })
      setLinkState('done')
    } catch (e: any) {
      const detail = e.response?.data?.detail
      if (detail === 'SETUP_TOKEN_EXPIRED') {
        setLinkState('invalid')
      } else if (detail === 'PASSWORD_TOO_SHORT') {
        setError(tUi('EMP_SET_PASSWORD_TOO_SHORT'))
      } else {
        setError(tUi('EMP_LOGIN_ERR_SIGNIN_FAILED'))
      }
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
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
            <h1 className="text-white font-semibold text-lg">{tUi('EMP_SET_PASSWORD_TITLE')}</h1>
            {linkState === 'valid' && (
              <p className="text-slate-400 text-sm mt-1">{tUi('EMP_SET_PASSWORD_SUB_FOR', { email })}</p>
            )}
          </div>

          {linkState === 'checking' && (
            <p className="text-slate-400 text-sm text-center py-4">{tUi('EMP_SET_PASSWORD_CHECKING_LINK')}</p>
          )}

          {linkState === 'invalid' && (
            <div className="text-center space-y-2 py-2">
              <p className="text-white font-medium text-sm">{tUi('EMP_SET_PASSWORD_INVALID_LINK_TITLE')}</p>
              <p className="text-slate-400 text-xs">{tUi('EMP_SET_PASSWORD_INVALID_LINK_BODY')}</p>
            </div>
          )}

          {linkState === 'done' && (
            <div className="text-center space-y-4 py-2">
              <p className="text-white font-medium text-sm">{tUi('EMP_SET_PASSWORD_SUCCESS_TITLE')}</p>
              <p className="text-slate-400 text-xs">{tUi('EMP_SET_PASSWORD_SUCCESS_BODY')}</p>
              <button onClick={() => navigate('/emp/login')}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm">
                {tUi('EMP_SET_PASSWORD_GO_TO_LOGIN_BTN')}
              </button>
            </div>
          )}

          {linkState === 'valid' && (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div className="space-y-1.5">
                <input
                  {...register('new_password', { required: true, minLength: 8 })}
                  type="password" autoComplete="new-password"
                  placeholder={tUi('EMP_SET_PASSWORD_MIN_CHARS_PLACEHOLDER')}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50"
                />
                {password.length > 0 && <StrengthBar password={password} />}
              </div>

              <input
                {...register('confirm', { required: true })}
                type="password" autoComplete="new-password"
                placeholder={tUi('EMP_SET_PASSWORD_REENTER_PLACEHOLDER')}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm placeholder-slate-500 outline-none focus:border-emerald-400/50"
              />

              {error && <p className="text-red-400 text-xs text-center">{error}</p>}

              <button type="submit" disabled={isSubmitting || !allRulesPassed}
                className="w-full bg-gradient-to-r from-emerald-400 to-cyan-400 text-emerald-950 font-semibold rounded-xl py-2.5 text-sm disabled:opacity-50">
                {tUi('EMP_SET_PASSWORD_SUBMIT_BTN')}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
