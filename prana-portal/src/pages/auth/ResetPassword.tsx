import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { tUi } from '@/i18n'

interface Form { new_password: string; confirm: string }

const RULES = [
  { label: 'At least 12 characters',              test: (p: string) => p.length >= 12 },
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
              i < passed ? colors[passed] : 'bg-slate-200'
            }`} />
        ))}
      </div>
      {password.length > 0 && (
        <p className={`text-xs font-medium ${passed >= 4 ? 'text-emerald-600' : passed >= 2 ? 'text-amber-600' : 'text-red-500'}`}>
          {labels[passed]}
        </p>
      )}
      <ul className="space-y-1">
        {RULES.map(r => {
          const ok = r.test(password)
          return (
            <li key={r.label} className={`text-xs flex items-center gap-1.5 ${ok ? 'text-emerald-600' : 'text-slate-400'}`}>
              <span className="text-[10px]">{ok ? '✓' : '○'}</span>
              {r.label}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function ResetPassword() {
  const navigate  = useNavigate()
  const { stepToken, setStepToken } = useAuthStore()
  const [error, setError]     = useState('')
  const [showPw, setShowPw]   = useState(false)
  const [showCf, setShowCf]   = useState(false)
  const { register, handleSubmit, watch, formState: { isSubmitting } } = useForm<Form>()
  const password = watch('new_password', '')
  const allRulesPassed = RULES.every(r => r.test(password))

  async function onSubmit(data: Form) {
    if (data.new_password !== data.confirm) { setError(tUi('RESET_PASSWORD_MISMATCH')); return }
    if (!allRulesPassed) { setError(tUi('RESET_PASSWORD_REQUIREMENTS_NOT_MET')); return }
    setError('')
    try {
      const res = await api.post('/auth/org/password-reset', {
        step_token:   stepToken,
        new_password: data.new_password,
      })
      // API returns a fresh step_token valid for the TOTP step
      setStepToken(res.data.step_token)
      navigate('/org/totp')
    } catch (e: any) {
      const detail = e.response?.data?.detail
      if (detail === 'STEP_TOKEN_EXPIRED') {
        setError(tUi('RESET_PASSWORD_SESSION_EXPIRED'))
      } else if (detail === 'PASSWORD_TOO_SHORT') {
        setError(tUi('RESET_PASSWORD_TOO_SHORT'))
      } else {
        setError(detail ?? tUi('RESET_PASSWORD_FAILED_DEFAULT'))
      }
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-6">
          <div className="w-14 h-14 rounded-2xl mx-auto mb-3 flex items-center justify-center text-2xl"
            style={{ background: 'linear-gradient(135deg, #6366F1, #22D3EE)' }}>
            🔑
          </div>
          <h1 className="text-xl font-bold text-slate-900">{tUi('EMP_LOGIN_STEP_FORCE_PASSWORD_TITLE')}</h1>
          <p className="text-slate-500 text-sm mt-1">
            {tUi('RESET_PASSWORD_SUB')}
          </p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)}
              className="bg-white rounded-2xl border border-slate-200 shadow-sm p-7 space-y-5">

          {/* New password */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              {tUi('RESET_PASSWORD_NEW_LABEL')}
            </label>
            <div className="relative">
              <input
                {...register('new_password', { required: true, minLength: 12 })}
                type={showPw ? 'text' : 'password'}
                placeholder={tUi('RESET_PASSWORD_MIN_CHARS_PLACEHOLDER')}
                className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm pr-10
                           focus:outline-none focus:ring-2 focus:ring-violet-400 bg-slate-50 focus:bg-white
                           transition-colors"
              />
              <button type="button" onClick={() => setShowPw(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-sm">
                {showPw ? '🙈' : '👁'}
              </button>
            </div>
            {password.length > 0 && <StrengthBar password={password} />}
          </div>

          {/* Confirm */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              {tUi('RESET_PASSWORD_CONFIRM_LABEL')}
            </label>
            <div className="relative">
              <input
                {...register('confirm', { required: true })}
                type={showCf ? 'text' : 'password'}
                placeholder={tUi('RESET_PASSWORD_REENTER_PLACEHOLDER')}
                className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm pr-10
                           focus:outline-none focus:ring-2 focus:ring-violet-400 bg-slate-50 focus:bg-white
                           transition-colors"
              />
              <button type="button" onClick={() => setShowCf(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-sm">
                {showCf ? '🙈' : '👁'}
              </button>
            </div>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-100 rounded-xl px-4 py-3 flex items-start gap-2">
              <span className="text-red-500 text-sm">⚠</span>
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitting || !allRulesPassed}
            className="w-full text-white font-semibold py-2.5 rounded-xl transition-opacity
                       disabled:opacity-40 hover:opacity-90"
            style={{ background: 'linear-gradient(135deg, #6366F1, #8B5CF6)' }}
          >
            {isSubmitting ? 'Saving…' : 'Set password & continue →'}
          </button>
        </form>

        <p className="text-center text-xs text-slate-400 mt-4">
          {tUi('RESET_PASSWORD_ARGON_NOTE')}
        </p>
      </div>
    </div>
  )
}
