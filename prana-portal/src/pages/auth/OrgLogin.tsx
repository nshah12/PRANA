import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/auth'

interface LoginForm { email: string; password: string }

function ForgotPasswordModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
         onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl p-7 max-w-sm w-full"
           onClick={e => e.stopPropagation()}>
        <div className="text-center mb-5">
          <div className="w-12 h-12 rounded-xl mx-auto mb-3 flex items-center justify-center text-2xl bg-violet-50">
            🔑
          </div>
          <h2 className="text-lg font-bold text-slate-900">Password reset</h2>
        </div>
        <div className="space-y-3 text-sm text-slate-600 leading-relaxed">
          <p>
            Password resets for organisation accounts are handled by your{' '}
            <strong>OA-Admin</strong>. They can reset your password from the{' '}
            <span className="font-mono text-xs bg-slate-100 px-1.5 py-0.5 rounded">
              User Management
            </span>{' '}
            screen.
          </p>
          <p>
            If you are the OA-Admin and have lost access, contact{' '}
            <a href="mailto:support@prana.in"
               className="text-violet-600 hover:underline font-medium">
              support@prana.in
            </a>{' '}
            with your organisation domain and registered email.
          </p>
        </div>
        <button onClick={onClose}
          className="w-full mt-6 bg-violet-600 hover:bg-violet-700 text-white font-medium
                     py-2.5 rounded-xl transition-colors text-sm">
          Got it
        </button>
      </div>
    </div>
  )
}

const FEATURES = [
  { icon: '🗄', text: 'One permanent vault — across every employer' },
  { icon: '🤖', text: '6-stage AI pipeline — insights, never raw ₹' },
  { icon: '🔒', text: 'AES-256 + DEK/KEK encryption per employee' },
  { icon: '📋', text: 'DPDP Act 2023 compliant from day one' },
]

export function OrgLogin() {
  const navigate = useNavigate()
  const { setStepToken, setRequiresTotpSetup } = useAuthStore()
  const [error, setError]           = useState('')
  const [showPw, setShowPw]         = useState(false)
  const [showForgot, setShowForgot] = useState(false)
  const { register, handleSubmit, formState: { isSubmitting } } = useForm<LoginForm>()

  async function onSubmit(data: LoginForm) {
    setError('')
    try {
      const res = await api.post('/auth/org/login', data)
      setStepToken(res.data.step_token)
      setRequiresTotpSetup(!!res.data.requires_totp_setup)
      if (res.data.requires_password_reset) {
        navigate('/org/reset')
      } else {
        navigate('/org/totp')
      }
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Login failed. Check your credentials.')
    }
  }

  return (
    <div className="min-h-screen flex">
      {showForgot && <ForgotPasswordModal onClose={() => setShowForgot(false)} />}

      {/* ── Left branding panel ── */}
      <div className="hidden lg:flex lg:w-[48%] flex-col justify-between p-12 relative overflow-hidden"
        style={{ background: 'linear-gradient(145deg, #0F172A 0%, #1E1B4B 50%, #312E81 100%)' }}>

        {/* Decorative blobs */}
        <div className="absolute top-0 right-0 w-64 h-64 rounded-full opacity-10"
          style={{ background: 'radial-gradient(circle, #8B5CF6, transparent)', transform: 'translate(30%, -30%)' }} />
        <div className="absolute bottom-0 left-0 w-80 h-80 rounded-full opacity-10"
          style={{ background: 'radial-gradient(circle, #22D3EE, transparent)', transform: 'translate(-30%, 30%)' }} />

        {/* Logo */}
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #6366F1, #22D3EE, #34D399)' }}>
              <span className="text-white font-bold">P</span>
            </div>
            <span className="font-mono text-2xl font-bold text-white tracking-tight">
              prana.<span className="text-sky-400">in</span>
            </span>
          </div>
          <p className="text-slate-400 text-xs pl-12">Organisation Portal</p>
        </div>

        {/* Main copy */}
        <div className="relative z-10">
          <h2 className="text-4xl font-extrabold text-white leading-tight mb-4">
            Your employees'<br />
            career vault,<br />
            <span style={{ background: 'linear-gradient(135deg, #22D3EE, #34D399)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>
              always ready.
            </span>
          </h2>
          <p className="text-slate-400 text-sm leading-relaxed max-w-xs mb-8">
            Push salary slips, Form 16, and offer letters to employee vaults automatically.
            Employees share; you stay compliant.
          </p>

          <div className="space-y-3">
            {FEATURES.map(f => (
              <div key={f.text} className="flex items-center gap-3">
                <span className="text-lg w-8 text-center flex-shrink-0">{f.icon}</span>
                <span className="text-slate-300 text-sm">{f.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Footer quote */}
        <div className="relative z-10">
          <div className="border-l-2 border-violet-500 pl-4">
            <p className="text-slate-300 text-sm italic">"One vault. Every employer. Forever yours."</p>
          </div>
        </div>
      </div>

      {/* ── Right form panel ── */}
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-50">
        <div className="w-full max-w-md">

          {/* Mobile logo */}
          <div className="lg:hidden mb-8 text-center">
            <span className="font-mono text-2xl font-bold text-slate-900">
              prana.<span className="text-sky-500">in</span>
            </span>
          </div>

          <div className="bg-white rounded-3xl border border-slate-200 shadow-sm p-8">
            <div className="mb-6">
              <div className="inline-flex items-center gap-2 bg-violet-50 border border-violet-100
                              rounded-full px-3 py-1 mb-4">
                <div className="w-1.5 h-1.5 rounded-full bg-violet-500" />
                <span className="text-[10px] font-bold text-violet-600 uppercase tracking-widest">Organisation access</span>
              </div>
              <h1 className="text-2xl font-extrabold text-slate-900">Welcome back</h1>
              <p className="text-slate-400 text-sm mt-1">Sign in with your organisation work email</p>
            </div>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                  Work email
                </label>
                <input
                  {...register('email', { required: true })}
                  type="email"
                  placeholder="you@company.in"
                  className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm
                             focus:outline-none focus:ring-2 focus:ring-violet-400 bg-slate-50 focus:bg-white
                             transition-colors"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">Password</label>
                  <button type="button" onClick={() => setShowForgot(true)} className="text-xs text-violet-600 hover:underline">Forgot password?</button>
                </div>
                <div className="relative">
                  <input
                    {...register('password', { required: true })}
                    type={showPw ? 'text' : 'password'}
                    className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm pr-10
                               focus:outline-none focus:ring-2 focus:ring-violet-400 bg-slate-50 focus:bg-white
                               transition-colors"
                  />
                  <button type="button" onClick={() => setShowPw(v => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                    {showPw ? '🙈' : '👁'}
                  </button>
                </div>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-100 rounded-xl px-4 py-3 flex items-start gap-2">
                  <span className="text-red-500 text-sm mt-0.5">⚠</span>
                  <p className="text-sm text-red-600">{error}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full text-white font-semibold py-3 rounded-xl transition-opacity
                           disabled:opacity-50 hover:opacity-90"
                style={{ background: 'linear-gradient(135deg, #6366F1, #8B5CF6)' }}
              >
                {isSubmitting ? 'Signing in…' : 'Continue to 2FA →'}
              </button>
            </form>

            <div className="mt-6 pt-5 border-t border-slate-100 text-center">
              <p className="text-xs text-slate-400">
                Portal Admin (PRANA staff)?{' '}
                <button onClick={() => navigate('/admin/login')} className="text-amber-600 font-semibold hover:underline">
                  Sign in here
                </button>
              </p>
            </div>
          </div>

          <p className="text-center text-xs text-slate-400 mt-6">
            New organisation?{' '}
            <button onClick={() => navigate('/register')} className="text-indigo-600 hover:underline">
              Register your org
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
