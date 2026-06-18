import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/auth'

interface LoginForm { email: string; password: string }

const CAPABILITIES = [
  { icon: '🏢', text: 'Tenant onboarding & provisioning' },
  { icon: '📊', text: 'Platform-wide meta dashboard' },
  { icon: '🛡', text: 'SecOps — anomaly & incident response' },
  { icon: '🔑', text: 'Crypto health & KMS key management' },
]

export function AdminLogin() {
  const navigate = useNavigate()
  const { setStepToken, setRequiresTotpSetup } = useAuthStore()
  const [error, setError] = useState('')
  const [showPw, setShowPw] = useState(false)
  const { register, handleSubmit, formState: { isSubmitting } } = useForm<LoginForm>()

  async function onSubmit(data: LoginForm) {
    setError('')
    try {
      const res = await api.post('/auth/admin/login', data)
      setStepToken(res.data.step_token)
      setRequiresTotpSetup(!!res.data.requires_totp_setup)
      navigate('/admin/totp')
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Login failed. Verify your @prana.in credentials.')
    }
  }

  return (
    <div className="min-h-screen flex">

      {/* ── Left branding panel ── */}
      <div className="hidden lg:flex lg:w-[48%] flex-col justify-between p-12 relative overflow-hidden"
        style={{ background: 'linear-gradient(145deg, #0F172A 0%, #1C1917 50%, #292524 100%)' }}>

        {/* Decorative blobs */}
        <div className="absolute top-0 right-0 w-64 h-64 rounded-full opacity-10"
          style={{ background: 'radial-gradient(circle, #F59E0B, transparent)', transform: 'translate(30%, -30%)' }} />
        <div className="absolute bottom-0 left-0 w-80 h-80 rounded-full opacity-10"
          style={{ background: 'radial-gradient(circle, #EF4444, transparent)', transform: 'translate(-30%, 30%)' }} />

        {/* PA badge */}
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-xl bg-amber-500 flex items-center justify-center">
              <span className="text-white font-bold text-sm">PA</span>
            </div>
            <span className="font-mono text-2xl font-bold text-white tracking-tight">
              prana.<span className="text-amber-400">in</span>
            </span>
          </div>
          <p className="text-slate-500 text-xs pl-12">Platform Admin Console</p>
        </div>

        {/* Warning notice */}
        <div className="relative z-10">
          <div className="bg-amber-500/10 border border-amber-500/20 rounded-2xl p-5 mb-8">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-amber-400 text-lg">⚠</span>
              <span className="text-amber-400 text-xs font-bold uppercase tracking-wider">Restricted access</span>
            </div>
            <p className="text-slate-400 text-xs leading-relaxed">
              This console is for PRANA platform staff only. Access requires a
              verified <span className="text-amber-400 font-mono">@prana.in</span> email address and TOTP.
              All actions are logged and audited.
            </p>
          </div>

          <h2 className="text-3xl font-extrabold text-white leading-tight mb-4">
            Platform Admin<br />
            <span style={{ background: 'linear-gradient(135deg, #F59E0B, #EF4444)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>
              Console
            </span>
          </h2>

          <div className="space-y-3">
            {CAPABILITIES.map(c => (
              <div key={c.text} className="flex items-center gap-3">
                <span className="text-lg w-8 text-center flex-shrink-0">{c.icon}</span>
                <span className="text-slate-300 text-sm">{c.text}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="relative z-10">
          <p className="text-slate-600 text-xs">
            Locked after 3 failed TOTP attempts. TOTP lockout: 30 minutes.
          </p>
        </div>
      </div>

      {/* ── Right form panel ── */}
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-50">
        <div className="w-full max-w-md">

          {/* Mobile logo */}
          <div className="lg:hidden mb-8 text-center">
            <span className="font-mono text-2xl font-bold text-slate-900">
              prana.<span className="text-amber-500">in</span>
            </span>
          </div>

          <div className="bg-white rounded-3xl border border-slate-200 shadow-sm p-8">
            <div className="mb-6">
              <div className="inline-flex items-center gap-2 bg-amber-50 border border-amber-100
                              rounded-full px-3 py-1 mb-4">
                <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                <span className="text-[10px] font-bold text-amber-600 uppercase tracking-widest">Platform Admin only</span>
              </div>
              <h1 className="text-2xl font-extrabold text-slate-900">Admin sign in</h1>
              <p className="text-slate-400 text-sm mt-1">
                Your <span className="font-mono text-amber-600">@prana.in</span> email is required
              </p>
            </div>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                  Admin email
                </label>
                <input
                  {...register('email', { required: true })}
                  type="email"
                  placeholder="you@prana.in"
                  className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm font-mono
                             focus:outline-none focus:ring-2 focus:ring-amber-400 bg-slate-50 focus:bg-white
                             transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                  Password
                </label>
                <div className="relative">
                  <input
                    {...register('password', { required: true })}
                    type={showPw ? 'text' : 'password'}
                    className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm pr-10
                               focus:outline-none focus:ring-2 focus:ring-amber-400 bg-slate-50 focus:bg-white
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
                style={{ background: 'linear-gradient(135deg, #D97706, #B45309)' }}
              >
                {isSubmitting ? 'Authenticating…' : 'Continue to TOTP →'}
              </button>
            </form>

            <div className="mt-6 pt-5 border-t border-slate-100 text-center">
              <p className="text-xs text-slate-400">
                Organisation login?{' '}
                <button onClick={() => navigate('/org/login')} className="text-violet-600 font-semibold hover:underline">
                  Sign in here
                </button>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
