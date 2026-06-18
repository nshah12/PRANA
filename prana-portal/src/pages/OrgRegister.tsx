import { useState, useRef, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'

const GRAD = 'linear-gradient(135deg, #6366F1 0%, #22D3EE 55%, #34D399 100%)'

const INDUSTRIES   = ['IT & Software', 'BFSI', 'Manufacturing', 'Healthcare & Pharma',
                      'Education', 'Retail & E-commerce', 'Telecom', 'Infrastructure & Construction',
                      'FMCG', 'Media & Entertainment', 'Logistics', 'Other']
const HEADCOUNTS   = ['1–50', '51–200', '201–500', '501–1000', '1001–5000', '5000+']
const ENTITY_TYPES = ['Private Limited Company', 'Public Limited Company', 'Partnership Firm',
                      'LLP', 'Proprietorship', 'Government / PSU', 'Trust / NGO', 'Other']

function GradBtn({ children, className = '', type = 'button', disabled = false, onClick }: {
  children: React.ReactNode; className?: string; type?: 'button' | 'submit'; disabled?: boolean; onClick?: () => void
}) {
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      style={{ background: disabled ? undefined : GRAD }}
      className={`text-white font-semibold rounded-xl px-6 py-3 text-sm transition-opacity
                  hover:opacity-90 disabled:opacity-50 disabled:bg-slate-300 ${className}`}>
      {children}
    </button>
  )
}

// Progress indicator
function Steps({ active }: { active: 0 | 1 | 2 }) {
  const labels = ['Your details', 'Verify email', 'Registration']
  return (
    <div className="flex items-center justify-center gap-0 mb-10">
      {labels.map((l, i) => (
        <div key={i} className="flex items-center">
          <div className="flex flex-col items-center">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
              i < active  ? 'bg-emerald-500 text-white'
              : i === active ? 'text-white' : 'bg-slate-100 text-slate-400'
            }`}
              style={i === active ? { background: GRAD } : {}}>
              {i < active ? '✓' : i + 1}
            </div>
            <span className={`text-[10px] mt-1 font-medium ${i <= active ? 'text-indigo-600' : 'text-slate-400'}`}>
              {l}
            </span>
          </div>
          {i < labels.length - 1 && (
            <div className={`w-16 h-px mx-1 mb-4 transition-colors ${i < active ? 'bg-emerald-400' : 'bg-slate-200'}`} />
          )}
        </div>
      ))}
    </div>
  )
}

const inp = "w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"

// ── Step 0: Initial details ──────────────────────────────────────────────────
function StepInit({ onNext }: {
  onNext: (sessionToken: string, email: string, orgName: string, contactName: string) => void
}) {
  const [form, setForm] = useState({ email: '', org_name: '', contact_name: '', how_heard: '' })
  const sf = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const mutation = useMutation({
    mutationFn: () => api.post('/public/org-register/init', form),
    onSuccess: (res) => {
      onNext(res.data.session_token, form.email, form.org_name, form.contact_name)
    },
  })

  return (
    <form onSubmit={e => { e.preventDefault(); mutation.mutate() }} className="space-y-5">
      <div className="text-center mb-6">
        <h2 className="text-xl font-bold text-slate-900 mb-1">Tell us about your organisation</h2>
        <p className="text-slate-400 text-sm">
          We'll send a verification code to your corporate email address.
        </p>
      </div>

      <div>
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
          Corporate email address <span className="text-red-400">*</span>
        </label>
        <input className={inp} required type="email" value={form.email} onChange={sf('email')}
          placeholder="you@yourcompany.in" />
        <p className="text-[11px] text-slate-400 mt-1">
          Must be a business email — we'll send an OTP to verify it's yours.
        </p>
      </div>

      <div>
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
          Organisation name <span className="text-red-400">*</span>
        </label>
        <input className={inp} required value={form.org_name} onChange={sf('org_name')}
          placeholder="TechCorp Solutions Private Limited" />
      </div>

      <div>
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
          Your name <span className="text-red-400">*</span>
        </label>
        <input className={inp} required value={form.contact_name} onChange={sf('contact_name')}
          placeholder="Ananya Krishnamurthy" />
      </div>

      <div>
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
          How did you hear about PRANA?
        </label>
        <select className={inp} value={form.how_heard} onChange={sf('how_heard')}>
          <option value="">Select…</option>
          {['LinkedIn', 'Google Search', 'Referral from another org', 'Events / Conference',
            'News / Media', 'Nasscom / Industry body', 'Other'].map(o => <option key={o}>{o}</option>)}
        </select>
      </div>

      {mutation.isError && (
        <div className="bg-red-50 border border-red-100 rounded-xl px-4 py-3 text-sm text-red-600">
          {(mutation.error as any)?.response?.data?.detail ?? 'Something went wrong. Please try again.'}
        </div>
      )}

      <GradBtn type="submit" disabled={mutation.isPending} className="w-full !py-3.5 !text-base !rounded-xl">
        {mutation.isPending ? 'Sending OTP…' : 'Send verification code →'}
      </GradBtn>
    </form>
  )
}

// ── Step 1: OTP verification ─────────────────────────────────────────────────
function StepVerifyOtp({ sessionToken, email, orgName, onNext, onBack }: {
  sessionToken: string; email: string; orgName: string
  onNext: (verifiedToken: string, prefilled: any) => void
  onBack: () => void
}) {
  const [otp, setOtp] = useState('')
  const [resent, setResent] = useState(false)
  const [countdown, setCountdown] = useState(30)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  useEffect(() => {
    if (countdown <= 0) return
    const t = setTimeout(() => setCountdown(c => c - 1), 1000)
    return () => clearTimeout(t)
  }, [countdown])

  const mutation = useMutation({
    mutationFn: () => api.post('/public/org-register/verify', { session_token: sessionToken, otp }),
    onSuccess: (res) => {
      onNext(res.data.verified_token, res.data.form_data ?? {})
    },
  })

  const resendMut = useMutation({
    mutationFn: () => api.post('/public/org-register/init', {
      email, org_name: orgName, contact_name: '', how_heard: '',
    }),
    onSuccess: () => { setResent(true); setCountdown(30) },
  })

  return (
    <div className="space-y-5">
      <div className="text-center mb-6">
        <div className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center text-3xl"
          style={{ background: GRAD }}>📧</div>
        <h2 className="text-xl font-bold text-slate-900 mb-1">Check your email</h2>
        <p className="text-slate-400 text-sm leading-relaxed">
          We've sent a 6-digit verification code to<br />
          <strong className="text-slate-700">{email}</strong>
        </p>
      </div>

      <form onSubmit={e => { e.preventDefault(); mutation.mutate() }} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 text-center">
            Enter 6-digit code
          </label>
          <input
            ref={inputRef}
            value={otp}
            onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
            type="text"
            inputMode="numeric"
            placeholder="000000"
            className="w-full border-2 border-slate-200 rounded-2xl px-4 py-5 text-3xl
                       font-mono text-center tracking-[0.6em] focus:outline-none
                       focus:border-indigo-400 bg-slate-50 focus:bg-white transition-colors"
          />
          <p className="text-center text-xs text-slate-400 mt-2">Code expires in 10 minutes</p>
        </div>

        {mutation.isError && (
          <div className="bg-red-50 border border-red-100 rounded-xl px-4 py-3 flex items-center gap-2">
            <span className="text-red-500">⚠</span>
            <p className="text-sm text-red-600">
              {(mutation.error as any)?.response?.data?.detail ?? 'Incorrect code. Please try again.'}
            </p>
          </div>
        )}

        {resent && (
          <div className="bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-3 text-sm text-emerald-700 text-center">
            ✓ New code sent to {email}
          </div>
        )}

        <GradBtn type="submit" disabled={mutation.isPending || otp.length !== 6}
          className="w-full !py-3.5 !text-base !rounded-xl">
          {mutation.isPending ? 'Verifying…' : 'Verify →'}
        </GradBtn>
      </form>

      <div className="text-center space-y-2">
        <p className="text-xs text-slate-400">
          Didn't receive it?{' '}
          {countdown > 0 ? (
            <span className="text-slate-400">Resend in {countdown}s</span>
          ) : (
            <button onClick={() => resendMut.mutate()}
              disabled={resendMut.isPending}
              className="text-indigo-600 font-medium hover:underline disabled:opacity-50">
              {resendMut.isPending ? 'Sending…' : 'Resend code'}
            </button>
          )}
        </p>
        <button onClick={onBack} className="text-sm text-slate-400 hover:text-slate-600">
          ← Change email address
        </button>
      </div>
    </div>
  )
}

// ── Step 2: Full registration form ───────────────────────────────────────────
function StepComplete({ verifiedToken, prefilled, email, onDone }: {
  verifiedToken: string; prefilled: any; email: string
  onDone: (appId: string, orgName: string) => void
}) {
  const [form, setForm] = useState({
    org_name:       prefilled.org_name ?? '',
    domain:         '',
    entity_type:    '',
    industry:       '',
    headcount_band: '',
    contact_name:   prefilled.contact_name ?? '',
    contact_email:  email,
    contact_mobile: '',
    message:        '',
    how_heard:      prefilled.how_heard ?? '',
  })
  const [agree, setAgree] = useState(false)
  const sf = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const mutation = useMutation({
    mutationFn: () => api.post('/public/org-register/complete', {
      ...form,
      verified_token: verifiedToken,
      agreed_to_dpa: agree,
    }),
    onSuccess: (res) => onDone(res.data.application_id, form.org_name),
  })

  return (
    <form onSubmit={e => { e.preventDefault(); mutation.mutate() }} className="space-y-6">
      <div className="text-center mb-2">
        <div className="inline-flex items-center gap-2 bg-emerald-50 border border-emerald-100
                        rounded-full px-3 py-1 mb-4">
          <span className="text-emerald-500 text-xs font-bold">✓ Email verified</span>
          <span className="text-slate-400 text-xs">{email}</span>
        </div>
        <h2 className="text-xl font-bold text-slate-900 mb-1">Complete your registration</h2>
        <p className="text-slate-400 text-sm">Fill in the remaining details about your organisation.</p>
      </div>

      {/* Organisation */}
      <div>
        <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Organisation</h3>
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Legal name <span className="text-red-400">*</span>
            </label>
            <input className={inp} required value={form.org_name} onChange={sf('org_name')}
              placeholder="TechCorp Solutions Private Limited" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">
                Primary domain <span className="text-red-400">*</span>
              </label>
              <input className={inp} required value={form.domain} onChange={sf('domain')}
                placeholder="techcorp.in" />
              <p className="text-[10px] text-slate-400 mt-1">Used to verify employee work emails</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Entity type</label>
              <select className={inp} value={form.entity_type} onChange={sf('entity_type')}>
                <option value="">Select…</option>
                {ENTITY_TYPES.map(e => <option key={e}>{e}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Industry</label>
              <select className={inp} value={form.industry} onChange={sf('industry')}>
                <option value="">Select…</option>
                {INDUSTRIES.map(i => <option key={i}>{i}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Employee headcount</label>
              <select className={inp} value={form.headcount_band} onChange={sf('headcount_band')}>
                <option value="">Select…</option>
                {HEADCOUNTS.map(h => <option key={h}>{h}</option>)}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Contact (pre-filled, allow editing) */}
      <div>
        <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Primary contact</h3>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">
                Your name <span className="text-red-400">*</span>
              </label>
              <input className={inp} required value={form.contact_name} onChange={sf('contact_name')}
                placeholder="Ananya Krishnamurthy" />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Mobile</label>
              <input className={inp} type="tel" value={form.contact_mobile} onChange={sf('contact_mobile')}
                placeholder="+91 98765 43210" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Verified email</label>
            <input className={`${inp} bg-emerald-50 text-slate-500 cursor-not-allowed`}
              value={email} readOnly />
          </div>
        </div>
      </div>

      {/* Message */}
      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">
          Any specific requirements or questions?
        </label>
        <textarea className={`${inp} resize-none h-20`} value={form.message} onChange={sf('message')}
          placeholder="Tell us about your HRMS, integration needs, or any questions…" />
      </div>

      {/* DPDP */}
      <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-4">
        <label className="flex items-start gap-3 cursor-pointer">
          <input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)}
            className="mt-0.5 accent-indigo-500" required />
          <span className="text-xs text-slate-600 leading-relaxed">
            I confirm that I have authority to register this organisation and agree to PRANA's{' '}
            <a href="#" className="text-indigo-600 underline">Data Processing Agreement</a>,{' '}
            <a href="#" className="text-indigo-600 underline">Privacy Policy</a>, and{' '}
            <a href="#" className="text-indigo-600 underline">Terms of Use</a>. <span className="text-red-400">*</span>
          </span>
        </label>
      </div>

      {mutation.isError && (
        <div className="bg-red-50 border border-red-100 rounded-xl px-4 py-3 text-sm text-red-600">
          {(mutation.error as any)?.response?.data?.detail ?? 'Submission failed. Please try again.'}
        </div>
      )}

      <GradBtn type="submit" disabled={mutation.isPending || !agree}
        className="w-full !py-4 !text-base !rounded-xl">
        {mutation.isPending ? 'Submitting…' : 'Submit registration application →'}
      </GradBtn>
    </form>
  )
}

// ── Success screen ────────────────────────────────────────────────────────────
function SuccessScreen({ appId, orgName, email }: { appId: string; orgName: string; email: string }) {
  const navigate = useNavigate()
  return (
    <div className="text-center py-8">
      <div className="w-20 h-20 rounded-full mx-auto mb-6 flex items-center justify-center text-4xl"
        style={{ background: GRAD }}>🎉</div>
      <h1 className="text-2xl font-extrabold text-slate-900 mb-3">Application received!</h1>
      <p className="text-slate-500 text-sm leading-relaxed mb-3 max-w-sm mx-auto">
        Thank you for registering <strong>{orgName}</strong> on PRANA.
        Our team will review and reach you at <strong>{email}</strong> within 1–2 business days.
      </p>
      <p className="text-xs text-slate-400 mb-6 font-mono">
        Reference: <span className="text-slate-600">{appId?.slice(0, 8).toUpperCase()}</span>
      </p>
      <button onClick={() => navigate('/')} className="text-sm text-indigo-600 font-medium hover:underline">
        ← Back to home
      </button>
    </div>
  )
}

// ── Page shell ────────────────────────────────────────────────────────────────
export function OrgRegister() {
  const navigate = useNavigate()
  const [step, setStep] = useState<0 | 1 | 2>(0)
  const [sessionToken, setSessionToken] = useState('')
  const [verifiedToken, setVerifiedToken] = useState('')
  const [email, setEmail] = useState('')
  const [orgName, setOrgName] = useState('')
  const [prefilled, setPrefilled] = useState<any>({})
  const [done, setDone] = useState<{ appId: string; orgName: string } | null>(null)

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <nav className="bg-white border-b border-slate-100 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
          <button onClick={() => navigate('/')} className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: GRAD }}>
              <span className="text-white font-bold text-sm">P</span>
            </div>
            <span className="font-mono font-bold text-slate-900 text-lg tracking-tight">
              PRANA<span className="text-indigo-500">·</span>
            </span>
          </button>
          <button onClick={() => navigate('/')} className="text-sm text-slate-400 hover:text-slate-600">
            ← Back to home
          </button>
        </div>
      </nav>

      <div className="max-w-lg mx-auto px-6 py-12">
        {/* Hero */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 bg-indigo-50 border border-indigo-100
                          rounded-full px-4 py-1.5 mb-4">
            <span className="text-[10px] font-bold tracking-widest text-indigo-500 uppercase">
              Organisation self-registration
            </span>
          </div>
          <h1 className="text-3xl font-extrabold text-slate-900">Register on PRANA</h1>
        </div>

        <div className="bg-white rounded-3xl border border-slate-200 shadow-sm p-8">
          {!done && <Steps active={step} />}

          {done ? (
            <SuccessScreen appId={done.appId} orgName={done.orgName} email={email} />
          ) : step === 0 ? (
            <StepInit onNext={(token, em, org, name) => {
              setSessionToken(token); setEmail(em); setOrgName(org)
              setPrefilled((f: any) => ({ ...f, org_name: org, contact_name: name }))
              setStep(1)
            }} />
          ) : step === 1 ? (
            <StepVerifyOtp
              sessionToken={sessionToken}
              email={email}
              orgName={orgName}
              onBack={() => setStep(0)}
              onNext={(vt, pre) => {
                setVerifiedToken(vt)
                setPrefilled((f: any) => ({ ...f, ...pre }))
                setStep(2)
              }}
            />
          ) : (
            <StepComplete
              verifiedToken={verifiedToken}
              prefilled={prefilled}
              email={email}
              onDone={(appId, org) => setDone({ appId, orgName: org })}
            />
          )}
        </div>

        {!done && (
          <p className="text-center text-xs text-slate-400 mt-6">
            Already onboarded?{' '}
            <button onClick={() => navigate('/org/login')} className="text-indigo-600 hover:underline">
              Sign in to your portal
            </button>
          </p>
        )}
      </div>
    </div>
  )
}
