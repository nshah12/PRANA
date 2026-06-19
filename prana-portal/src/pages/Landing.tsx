import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'

// ── Gradient helpers ──────────────────────────────────────────────────────────
const GRAD = 'linear-gradient(135deg, #6366F1 0%, #22D3EE 55%, #34D399 100%)'

function GradText({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={className}
      style={{ background: GRAD, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>
      {children}
    </span>
  )
}

function GradBtn({ children, onClick, type = 'button', className = '' }: {
  children: React.ReactNode; onClick?: () => void; type?: 'button' | 'submit'; className?: string
}) {
  return (
    <button type={type} onClick={onClick}
      style={{ background: GRAD }}
      className={`text-white font-semibold rounded-xl px-6 py-3 text-sm hover:opacity-90 transition-opacity ${className}`}>
      {children}
    </button>
  )
}

// ── Content data ──────────────────────────────────────────────────────────────

const HIW_STEPS = [
  { n: '01', icon: '🏢', title: 'Employer onboards', desc: 'HR registers on PRANA portal in 15 min. Domain-verified. KEK-provisioned. Ready.' },
  { n: '02', icon: '📥', title: 'Documents arrive', desc: 'Salary slips, Form 16, offer letters — pushed automatically via portal or HRMS API.' },
  { n: '03', icon: '🤖', title: 'AI extracts insights', desc: '6-stage pipeline: OCR → classification → extraction → resolution → routing. Raw ₹ never stored.' },
  { n: '04', icon: '🗄', title: 'Vault activated', desc: 'One permanent vault. Every employer adds to the same vault — across your entire career.' },
  { n: '05', icon: '↗', title: 'You share securely', desc: 'Pick documents, set expiry, generate a watermarked C-Share link. Banks receive in seconds.' },
  { n: '06', icon: '✓', title: 'Recipient verifies', desc: 'QR scan confirms authenticity. Cryptographic proof. No phone calls to HR needed.' },
]

const EMPLOYEE_FEATURES = [
  { icon: '🗄',  title: 'My Vault',           desc: 'All documents, all employers, one place. The core promise.',                          accent: '#6366F1', bg: '#EEF2FF' },
  { icon: '↗',  title: 'C-Share',             desc: 'Create, revoke, watermark, set expiry, view count. You control every share.',         accent: '#0EA5E9', bg: '#F0F9FF' },
  { icon: '📋',  title: 'Activity log',        desc: 'Every access, push, and share event. Full transparency. No black boxes.',             accent: '#8B5CF6', bg: '#F5F3FF' },
  { icon: '🔔',  title: 'Smart alerts',        desc: 'Document arrived, accessed, share expiring. The vault that watches out for you.',     accent: '#F59E0B', bg: '#FFFBEB' },
  { icon: '⚖',  title: 'DPDP Rights Centre',  desc: 'Access, Correction, Erasure, Grievance, Nomination, Consent — all 6 rights.',        accent: '#EF4444', bg: '#FEF2F2' },
  { icon: '📅',  title: 'Career Timeline',     desc: 'Auto-assembled from verified documents. AI built your career story.',                 accent: '#10B981', bg: '#ECFDF5' },
  { icon: '📊',  title: 'Vault Health Score',  desc: 'Document completeness %. Shows gaps you never knew existed. Actionable.',            accent: '#06B6D4', bg: '#ECFEFF' },
  { icon: '📦',  title: 'Share Bundles',       desc: 'Named collections for loan, BGV, visa. One link. Everything the recipient needs.',    accent: '#EC4899', bg: '#FDF2F8' },
]

const CHRO_FEATURES = [
  { icon: '📊', title: 'Vault Health Dashboard', desc: 'Document completeness per department, grade, location — refreshed daily from verified pushes.' },
  { icon: '📅', title: 'Compliance Calendar',    desc: 'Form 16 deadlines, PF/ESIC obligations, DPDP consent review cycles — never miss a date.' },
  { icon: '📧', title: 'Weekly & Monthly Digest',desc: 'Vault completeness trends, new joiners, missing documents — delivered automatically.' },
  { icon: '🔔', title: 'Alert Config',           desc: 'Set thresholds on completeness, anomalies, consent drop-off. Proactive, not reactive.' },
]

const CFO_FEATURES = [
  { icon: '💰', title: 'Payroll Intelligence',   desc: 'Aggregate compensation analytics from verified salary slips. No individual salary ever visible. Min 30-person cohort.' },
  { icon: '📉', title: 'Attrition Cost',         desc: 'Replacement cost modelling from verified exit data. ₹ per exit, by department.' },
  { icon: '🔍', title: 'Anomaly Detection',      desc: 'Discrepancies between salary slips and appointment letters caught by AI — before they become liabilities.' },
  { icon: '📋', title: 'Compliance Posture',     desc: 'DPDP exposure, obligation tracking, consent coverage. Estimated penalty risk surfaced proactively.' },
]

const CISO_LAYERS = [
  { n: '1', label: 'STRUCTURAL',     title: 'Vault ownership transfers on routing',       desc: 'Employer cannot open, download, share, or delete. Ownership moved structurally.' },
  { n: '2', label: 'CRYPTOGRAPHIC',  title: 'One person. One key. One vault.',             desc: 'Each employee has their own DEK. A colleague\'s key cannot decrypt yours.' },
  { n: '3', label: 'ZERO-KNOWLEDGE', title: 'The system doesn\'t know who you are.',       desc: 'PAN → HMAC in 2ms. Plaintext destroyed. No row links PAN to name.' },
  { n: '4', label: 'CONSENT-GATED',  title: 'Sharing requires your action. Always.',      desc: 'Only you create share tokens. Named, time-limited, revocable, watermarked.' },
  { n: '5', label: 'RLS ENFORCED',   title: 'Portal Admin cannot read documents.',         desc: 'Zero SELECT on document rows. PostgreSQL RLS. The query is refused at DB level.' },
  { n: '6', label: 'TRANSPARENT',    title: 'Every access visible to the document owner.', desc: 'Actor, timestamp, action — in the employee\'s activity log. No black boxes.' },
  { n: '7', label: 'PORTABLE',       title: 'Your vault follows you — not your employer.', desc: 'When you leave, your vault stays yours. New employer pushes to the same vault.' },
]

const CISO_STATS = [
  { value: '1',      label: 'Person exposed per DEK compromise' },
  { value: '0',      label: 'Plaintext PAN in any DB row' },
  { value: '2ms',    label: 'PAN lifetime in memory' },
  { value: '₹150Cr', label: 'Max DPDP penalty — misuse structurally impossible' },
]

const ORG_FEATURES = [
  { icon: '⬆',  role: 'OA-Operator', title: 'Bulk upload with AI governance',   desc: 'Content policy, contamination detection, independent AI classification on every push.' },
  { icon: '👥',  role: 'OA-Admin',    title: 'User management & elevations',      desc: 'Self-managed org. Minimum-1-admin enforced. Elevation approvals with full audit trail.' },
  { icon: '🔌',  role: 'IT / DevOps', title: 'HRMS API integration',             desc: 'OpenAPI-compatible. X-PRANA-Key-ID + HMAC-SHA256. 500 rpm. Push millions of docs automatically.' },
  { icon: '🔑',  role: 'Security',    title: 'Platform-managed KEK/DEK',         desc: 'AWS KMS (ap-south-1). Tenant KEK + per-employee DEK. Blast radius = 1 person.' },
]

const TRUST_STATS = [
  { value: '6-stage', label: 'AI pipeline' },
  { value: 'DPDP',    label: 'Act 2023 ready' },
  { value: '0 raw ₹', label: 'ever stored' },
  { value: 'AES-256', label: 'at rest + transit' },
  { value: '7-year',  label: 'audit retention' },
  { value: 'DEK/KEK', label: 'per-employee encryption' },
]

const PERSONAS = [
  { id: 'employee', label: 'For Employees',       icon: '👤', color: '#0EA5E9' },
  { id: 'chro',     label: 'For CHRO / HR Heads', icon: '📊', color: '#10B981' },
  { id: 'cfo',      label: 'For CFO / Finance',   icon: '💰', color: '#6366F1' },
  { id: 'ciso',     label: 'For Infosec / DPO',   icon: '🛡', color: '#EF4444' },
]

// ── Contact modal ─────────────────────────────────────────────────────────────
function ContactModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({ name: '', email: '', org: '', enquiry_type: 'Organisation onboarding', message: '' })
  const [sent, setSent] = useState(false)
  const sf = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))
  const mutation = useMutation({
    mutationFn: () => api.post('/public/contact', form),
    onSuccess: () => setSent(true),
  })
  const inp = "w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" />
      <div className="relative bg-white rounded-3xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-8 pt-7 pb-5 border-b border-slate-100">
          <div>
            <p className="text-xs font-bold text-indigo-500 tracking-widest uppercase mb-0.5">Get in touch</p>
            <h2 className="text-xl font-extrabold text-slate-900">Contact PRANA</h2>
          </div>
          <button onClick={onClose}
            className="w-8 h-8 rounded-xl bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-500 transition-colors">
            ✕
          </button>
        </div>

        <div className="px-8 py-6">
          {sent ? (
            <div className="text-center py-8">
              <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 text-3xl"
                style={{ background: 'linear-gradient(135deg, #10B981, #22D3EE)' }}>
                ✓
              </div>
              <h3 className="text-lg font-bold text-slate-800 mb-2">Message sent!</h3>
              <p className="text-slate-500 text-sm mb-6">We'll reply within 24 hours at <strong>{form.email}</strong>.</p>
              <button onClick={onClose}
                className="text-sm font-semibold text-indigo-600 border border-indigo-100 rounded-xl px-5 py-2.5 hover:bg-indigo-50 transition-colors">
                Close
              </button>
            </div>
          ) : (
            <form onSubmit={e => { e.preventDefault(); mutation.mutate() }} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Full name <span className="text-red-400">*</span></label>
                  <input className={inp} required value={form.name} onChange={sf('name')} placeholder="Priya Sharma" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Work email <span className="text-red-400">*</span></label>
                  <input className={inp} required type="email" value={form.email} onChange={sf('email')} placeholder="priya@company.in" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Organisation</label>
                  <input className={inp} value={form.org} onChange={sf('org')} placeholder="TechCorp Solutions Pvt Ltd" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Enquiry type</label>
                  <select className={inp} value={form.enquiry_type} onChange={sf('enquiry_type')}>
                    {['Organisation onboarding', 'Product demo', 'Partnership', 'HRMS integration', 'General / Support'].map(o => <option key={o}>{o}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">Message</label>
                <textarea className={`${inp} resize-none h-24`} value={form.message} onChange={sf('message')} placeholder="Tell us what you need…" />
              </div>
              {mutation.isError && <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">Failed to send. Please try again.</p>}
              <GradBtn type="submit" className="w-full !rounded-xl !py-3.5">
                {mutation.isPending ? 'Sending…' : 'Send message — we reply within 24 hours →'}
              </GradBtn>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export function Landing() {
  const navigate = useNavigate()
  const [activeStep, setActiveStep] = useState(0)
  const [hoveredStep, setHoveredStep] = useState<number | null>(null)
  const [persona, setPersona] = useState('employee')
  const [loginOpen, setLoginOpen] = useState(false)
  const [contactOpen, setContactOpen] = useState(false)
  const loginRef = useRef<HTMLDivElement>(null)
  const contactRef = useRef<HTMLDivElement>(null)
  const hiwRef = useRef<HTMLDivElement>(null)
  const personaRef = useRef<HTMLDivElement>(null)
  const openContact = useCallback(() => setContactOpen(true), [])

  useEffect(() => {
    const t = setInterval(() => setActiveStep(s => (s + 1) % 6), 2800)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    function h(e: MouseEvent) {
      if (loginRef.current && !loginRef.current.contains(e.target as Node)) setLoginOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  function scrollTo(ref: React.RefObject<HTMLDivElement>) {
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="min-h-screen bg-white font-sans">
      {contactOpen && <ContactModal onClose={() => setContactOpen(false)} />}

      {/* ── Navbar ── */}
      <nav className="sticky top-0 z-50 bg-white/90 backdrop-blur border-b border-slate-100">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: GRAD }}>
              <span className="text-white font-bold text-sm">P</span>
            </div>
            <span className="font-mono font-bold text-slate-900 text-lg tracking-tight">
              PRANA<span className="text-indigo-500">·</span>
            </span>
          </div>

          <div className="hidden md:flex items-center gap-8">
            <button onClick={() => scrollTo(hiwRef)} className="text-sm font-semibold text-slate-700 hover:text-indigo-600 transition-colors">How it works</button>
            <button onClick={() => scrollTo(personaRef)} className="text-sm font-semibold text-slate-700 hover:text-indigo-600 transition-colors">Who it's for</button>
            <button onClick={() => navigate('/register')} className="text-sm font-semibold text-slate-700 hover:text-indigo-600 transition-colors">For employers</button>
            <button onClick={openContact}
              className="text-sm font-bold text-white rounded-xl px-4 py-2 transition-opacity hover:opacity-90"
              style={{ background: 'linear-gradient(135deg, #6366F1, #22D3EE)' }}>
              Contact
            </button>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative" ref={loginRef}>
              <button onClick={() => setLoginOpen(o => !o)}
                className="text-sm font-medium text-slate-700 border border-slate-200 rounded-xl px-4 py-2
                           hover:bg-slate-50 flex items-center gap-1.5">
                Login
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
              {loginOpen && (
                <div className="absolute right-0 mt-2 w-64 bg-white border border-slate-200 rounded-2xl shadow-xl py-2 overflow-hidden">
                  <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider px-3 pb-1 pt-1">Sign in as</p>

                  {/* Employee — primary audience */}
                  <button onClick={() => navigate('/emp/login')}
                    className="w-full px-4 py-2.5 text-left hover:bg-sky-50 flex items-center gap-3 border-b border-slate-100">
                    <div className="w-7 h-7 rounded-lg bg-sky-100 flex items-center justify-center">
                      <span className="text-sky-600 text-xs">👤</span>
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-800">Employee</p>
                      <p className="text-[10px] text-slate-400">Access your career vault</p>
                    </div>
                  </button>

                  <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider px-3 pt-2 pb-1">Employer / Admin</p>
                  <button onClick={() => navigate('/org/login')}
                    className="w-full px-4 py-2.5 text-left hover:bg-slate-50 flex items-center gap-3">
                    <div className="w-7 h-7 rounded-lg bg-violet-100 flex items-center justify-center">
                      <span className="text-violet-600 text-xs font-bold">OA</span>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-800">Organisation user</p>
                      <p className="text-[10px] text-slate-400">OA Admin / CHRO / CFO / CISO</p>
                    </div>
                  </button>
                  <button onClick={() => navigate('/admin/login')}
                    className="w-full px-4 py-2.5 text-left hover:bg-slate-50 flex items-center gap-3">
                    <div className="w-7 h-7 rounded-lg bg-amber-100 flex items-center justify-center">
                      <span className="text-amber-600 text-xs font-bold">PA</span>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-800">Platform Admin</p>
                      <p className="text-[10px] text-slate-400">@prana.in accounts only</p>
                    </div>
                  </button>
                </div>
              )}
            </div>
            <GradBtn onClick={() => navigate('/register')} className="!px-5 !py-2 !text-sm hidden sm:block">
              Register your org →
            </GradBtn>
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="max-w-6xl mx-auto px-6 pt-8 pb-12 text-center">
        <div className="inline-flex items-center gap-2 bg-indigo-50 border border-indigo-100 rounded-full px-4 py-1.5 mb-6">
          <span className="text-[10px] font-bold tracking-widest text-indigo-500 uppercase">Now live</span>
          <span className="text-[10px] text-indigo-400">Enterprise pilot-ready · DPDP Act 2023 compliant</span>
        </div>

        <h1 className="text-5xl sm:text-7xl font-extrabold text-slate-900 leading-[1.0] mb-6 tracking-tight">
          One vault. <GradText>Every employer.</GradText> Forever yours.
        </h1>

        <p className="text-slate-500 text-lg max-w-2xl mx-auto leading-relaxed mb-8">
          PRANA gives every Indian worker a permanent, portable career document vault — salary slips,
          Form 16, offer letters — pushed by employers, encrypted per-employee, owned entirely by you,
          and shareable in seconds with cryptographic proof of authenticity.
        </p>

        {/* Persona quick-links — pill cards */}
        <div className="flex flex-wrap justify-center gap-3 mb-8">
          {[
            { id: 'employee', label: 'Employees',     sub: 'One vault across your entire career',        color: '#0EA5E9', bg: '#F0F9FF', border: '#BAE6FD' },
            { id: 'chro',     label: 'CHRO / HR',     sub: 'Vault health & compliance intelligence',     color: '#10B981', bg: '#ECFDF5', border: '#A7F3D0' },
            { id: 'cfo',      label: 'CFO / Finance', sub: 'Aggregate payroll analytics',                color: '#6366F1', bg: '#EEF2FF', border: '#C7D2FE' },
            { id: 'ciso',     label: 'Infosec / DPO', sub: 'Trust architecture, not policy',            color: '#EF4444', bg: '#FEF2F2', border: '#FECACA' },
          ].map(p => (
            <button key={p.id}
              onClick={() => { setPersona(p.id); scrollTo(personaRef) }}
              className="flex flex-col items-start px-4 py-3 rounded-2xl border text-left transition-all hover:shadow-md hover:-translate-y-0.5"
              style={{ background: p.bg, borderColor: p.border }}>
              <span className="text-xs font-bold mb-0.5" style={{ color: p.color }}>{p.label}</span>
              <span className="text-[11px] text-slate-500">{p.sub}</span>
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center justify-center gap-3 mb-12">
          <GradBtn onClick={() => navigate('/register')} className="!px-8 !py-3.5 !text-base">
            Register your organisation →
          </GradBtn>
        </div>

        {/* Trust strip */}
        <div className="flex flex-wrap items-center justify-center gap-6 py-5 border-y border-slate-100">
          {TRUST_STATS.map(s => (
            <div key={s.value} className="text-center">
              <div className="font-extrabold text-xl"
                style={{ background: GRAD, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>
                {s.value}
              </div>
              <div className="text-xs text-slate-400 mt-0.5">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Flow strip ── */}
      <section className="bg-slate-50 border-y border-slate-100 py-8 px-6">
        <div className="max-w-5xl mx-auto">
          <p className="text-center text-xs font-semibold text-slate-400 uppercase tracking-widest mb-6">
            From employer push to verified share — one continuous chain
          </p>
          <div className="flex items-center justify-center gap-3 flex-wrap">
            {[
              { icon: '🏢', label: 'Employer pushes', sub: 'Salary slips, Form 16, letters' },
              { icon: '🗄', label: 'PRANA vault',      sub: 'Encrypted, DEK per employee' },
              { icon: '↗',  label: 'You share',        sub: 'Watermarked, time-limited' },
              { icon: '✓',  label: 'Recipient verifies', sub: 'Bank scans QR. Document proves itself.' },
            ].map((n, i, arr) => (
              <div key={i} className="flex items-center gap-3">
                <div className="bg-white border border-slate-200 rounded-2xl px-5 py-4 text-center min-w-[130px]">
                  <div className="text-2xl mb-2">{n.icon}</div>
                  <div className="text-xs font-semibold text-slate-800">{n.label}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">{n.sub}</div>
                </div>
                {i < arr.length - 1 && <span style={{ color: '#CBD5E1', fontSize: 22 }}>→</span>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section ref={hiwRef} className="max-w-6xl mx-auto px-6 pt-14 pb-10">
        <div className="text-center mb-12">
          <p className="text-xs font-bold text-indigo-500 tracking-widest uppercase mb-3">How it works</p>
          <h2 className="text-4xl font-extrabold text-slate-900 mb-3">
            Six steps, <GradText>fully automated</GradText>
          </h2>
          <p className="text-slate-500 text-base max-w-md mx-auto">
            From first document push to verified share. PRANA handles everything in between.
          </p>
        </div>

        <div className="flex justify-center gap-2 mb-8">
          {HIW_STEPS.map((_, i) => (
            <button key={i} onClick={() => setActiveStep(i)}
              className={`h-1.5 rounded-full transition-all duration-300 ${i === activeStep ? 'w-8' : 'w-2 bg-slate-200'}`}
              style={i === activeStep ? { background: GRAD, width: 32 } : {}} />
          ))}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-10">
          {HIW_STEPS.map((s, i) => {
            const isActive = i === activeStep
            return (
              <div key={i}
                onClick={() => setActiveStep(i)}
                onMouseEnter={() => setHoveredStep(i)}
                onMouseLeave={() => setHoveredStep(null)}
                className="rounded-2xl border p-5 cursor-pointer transition-all duration-300"
                style={isActive || hoveredStep === i
                  ? { borderColor: '#C7D2FE', background: 'linear-gradient(135deg, #EEF2FF 0%, #F0FDFA 100%)', boxShadow: '0 4px 16px rgba(99,102,241,0.14)' }
                  : { borderColor: '#E2E8F0', background: '#F8FAFC' }}>
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0 transition-all duration-200"
                    style={isActive || hoveredStep === i ? { background: GRAD, color: '#fff' } : { background: '#CBD5E1', color: '#64748B' }}>
                    {s.n}
                  </div>
                  <span className="text-xl">{s.icon}</span>
                </div>
                <h3 className={`font-semibold text-sm mb-1.5 transition-colors ${isActive || hoveredStep === i ? 'text-slate-900' : 'text-slate-600'}`}>{s.title}</h3>
                <p className="text-xs text-slate-400 leading-relaxed">{s.desc}</p>
              </div>
            )
          })}
        </div>

        {/* 3 perspective video placeholders */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-4xl mx-auto">
          {[
            { label: 'For CHROs', sublabel: 'Vault health · compliance · zero manual work', color: '#6366F1', glow: '#6366F1' },
            { label: 'For InfoSec', sublabel: 'Audit trail · access control · anomaly alerts', color: '#0EA5E9', glow: '#22D3EE' },
            { label: 'For Employees', sublabel: 'Own your docs · share securely · ask PRANA', color: '#10B981', glow: '#10B981' },
          ].map(v => (
            <div key={v.label} className="bg-slate-900 rounded-2xl overflow-hidden border border-slate-700 aspect-video
                            flex flex-col items-center justify-center gap-3 relative cursor-pointer group">
              <div className="absolute inset-0 opacity-20 group-hover:opacity-30 transition-opacity"
                style={{ background: `radial-gradient(circle at 50% 50%, ${v.glow}, transparent 70%)` }} />
              <div className="relative z-10 flex flex-col items-center gap-2 px-4 text-center">
                <div className="w-11 h-11 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform"
                  style={{ background: v.color }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="white"><path d="M8 5v14l11-7z"/></svg>
                </div>
                <p className="text-white text-xs font-semibold">{v.label}</p>
                <p className="text-slate-400 text-[10px] leading-relaxed">{v.sublabel}</p>
                <span className="text-[9px] font-medium px-2 py-0.5 rounded-full mt-1"
                  style={{ background: `${v.color}22`, color: v.color }}>60 sec · coming soon</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Persona tabs: Employee / CHRO / CFO / CISO ── */}
      <section ref={personaRef} className="bg-slate-50 border-y border-slate-100 pt-12 pb-16 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-10">
            <p className="text-xs font-bold text-indigo-500 tracking-widest uppercase mb-3">Who it's for</p>
            <h2 className="text-4xl font-extrabold text-slate-900">
              <GradText>Built for everyone</GradText> in the document chain
            </h2>
          </div>

          {/* Persona selector tabs */}
          <div className="flex flex-wrap justify-center gap-2 mb-8">
            {PERSONAS.map(p => (
              <button key={p.id} onClick={() => setPersona(p.id)}
                className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold
                            transition-all border ${persona === p.id
                              ? 'text-white border-transparent shadow-sm'
                              : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'}`}
                style={persona === p.id ? { background: p.color } : {}}>
                {p.icon} {p.label}
              </button>
            ))}
          </div>

          {/* ── Employee ── */}
          {persona === 'employee' && (
            <div>
              <div className="text-center mb-6">
                <h3 className="text-2xl font-bold text-slate-900 mb-2">Your vault. Your rules. Always.</h3>
                <p className="text-slate-500 text-sm max-w-xl mx-auto">
                  Every employer you work for pushes documents to the same permanent vault.
                  No more chasing HR. Share in seconds with cryptographic proof that banks, recruiters, and agencies trust.
                </p>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
                {EMPLOYEE_FEATURES.map(f => (
                  <div key={f.title}
                    className="bg-white rounded-2xl border border-slate-100 p-4 cursor-default
                               transition-all duration-200
                               hover:shadow-lg hover:-translate-y-1 hover:border-transparent"
                    style={{ borderTopColor: f.accent, borderTopWidth: 3 }}
                    onMouseEnter={e => {
                      const el = e.currentTarget
                      el.style.boxShadow = `0 8px 24px ${f.accent}28`
                      el.style.borderColor = f.accent
                    }}
                    onMouseLeave={e => {
                      const el = e.currentTarget
                      el.style.boxShadow = ''
                      el.style.borderColor = ''
                      el.style.borderTopColor = f.accent
                      el.style.borderTopWidth = '3px'
                    }}>
                    <div className="flex items-center gap-2.5 mb-2.5">
                      <div className="w-9 h-9 rounded-xl flex items-center justify-center text-lg flex-shrink-0
                                      transition-transform duration-200 hover:scale-110"
                        style={{ background: f.bg }}>
                        {f.icon}
                      </div>
                      <h4 className="font-bold text-slate-900 text-sm leading-tight">{f.title}</h4>
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed font-medium">{f.desc}</p>
                  </div>
                ))}
              </div>
              <div className="bg-sky-50 border border-sky-100 rounded-2xl p-5 flex items-start gap-4">
                <span className="text-2xl">💬</span>
                <div>
                  <p className="text-sm font-semibold text-slate-800 mb-1">Ask PRANA — AI Vault Assistant <span className="text-xs text-sky-500 font-normal">(Phase II)</span></p>
                  <p className="text-sm text-slate-500">
                    "What was my salary in March 2022?" Natural language queries on your own verified documents.
                    Answers derived from insights only — raw figures never leave your encrypted vault.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* ── CHRO ── */}
          {persona === 'chro' && (
            <div>
              <div className="text-center mb-6">
                <h3 className="text-2xl font-bold text-slate-900 mb-2">People intelligence from verified documents.</h3>
                <p className="text-slate-500 text-sm max-w-xl mx-auto">
                  Stop chasing employees for documents. PRANA tells you exactly which vault is incomplete,
                  which compliance deadline is coming, and which documents are missing — before they become audit findings.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4 mb-5">
                {CHRO_FEATURES.map(f => (
                  <div key={f.title} className="bg-white rounded-2xl border border-slate-100 p-5 hover:shadow-sm transition-shadow">
                    <div className="text-2xl mb-3">{f.icon}</div>
                    <h4 className="font-semibold text-slate-800 text-sm mb-1">{f.title}</h4>
                    <p className="text-xs text-slate-400 leading-relaxed">{f.desc}</p>
                  </div>
                ))}
              </div>
              <div className="bg-emerald-50 border border-emerald-100 rounded-2xl p-5 grid grid-cols-3 gap-4 text-center">
                {[
                  { v: '87%', l: 'Vault completeness (sample)' },
                  { v: '500', l: 'Active employees tracked' },
                  { v: '63',  l: 'Incomplete vaults flagged' },
                ].map(s => (
                  <div key={s.l}>
                    <div className="text-2xl font-extrabold text-emerald-700">{s.v}</div>
                    <div className="text-xs text-emerald-600">{s.l}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── CFO ── */}
          {persona === 'cfo' && (
            <div>
              <div className="text-center mb-6">
                <h3 className="text-2xl font-bold text-slate-900 mb-2">Aggregate payroll intelligence. No individual salary ever visible.</h3>
                <p className="text-slate-500 text-sm max-w-xl mx-auto">
                  Every figure is aggregated across a minimum of <strong>30 consenting employees</strong>.
                  Source: AI-extracted fields from employer-pushed salary slips — not self-reported data.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4 mb-5">
                {CFO_FEATURES.map(f => (
                  <div key={f.title} className="bg-white rounded-2xl border border-slate-100 p-5 hover:shadow-sm transition-shadow">
                    <div className="text-2xl mb-3">{f.icon}</div>
                    <h4 className="font-semibold text-slate-800 text-sm mb-1">{f.title}</h4>
                    <p className="text-xs text-slate-400 leading-relaxed">{f.desc}</p>
                  </div>
                ))}
              </div>
              <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-5 flex items-start gap-3">
                <span className="text-xl mt-0.5">🔒</span>
                <div>
                  <p className="text-sm font-semibold text-indigo-800 mb-1">Consent-first. Always.</p>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    All intelligence is derived exclusively from employees who have opted in to anonymous data sharing in their vault Settings.
                    487 of 500 employees (97.4%) consented in a reference deployment. Aggregates surface only when cohort ≥ 30.
                    Individual values are never shown, never derivable.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* ── CISO / Infosec ── */}
          {persona === 'ciso' && (
            <div>
              <div className="text-center mb-6">
                <h3 className="text-2xl font-bold text-slate-900 mb-2">Not policy. Architecture.</h3>
                <p className="text-slate-500 text-sm max-w-xl mx-auto">
                  Misuse is structurally impossible. Controls fail when credentials are compromised.
                  PRANA's architecture prevents misuse regardless of who has the keys.
                </p>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
                {CISO_STATS.map(s => (
                  <div key={s.value} className="bg-white border border-red-100 rounded-2xl p-4 text-center">
                    <div className="text-2xl font-extrabold text-red-600 mb-1">{s.value}</div>
                    <div className="text-[10px] text-slate-400 leading-tight">{s.label}</div>
                  </div>
                ))}
              </div>

              <div className="space-y-2 mb-5">
                {CISO_LAYERS.map((l, i) => (
                  <div key={i} className="bg-white rounded-2xl border border-slate-100 px-5 py-4 flex items-start gap-4">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-extrabold flex-shrink-0"
                      style={{ background: GRAD }}>
                      {l.n}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="text-[10px] font-bold text-red-500 bg-red-50 border border-red-100 rounded-full px-2 py-0.5">
                          {l.label}
                        </span>
                        <span className="text-sm font-semibold text-slate-800">{l.title}</span>
                      </div>
                      <p className="text-xs text-slate-400 leading-relaxed">{l.desc}</p>
                    </div>
                  </div>
                ))}
              </div>

              <div className="bg-slate-900 rounded-2xl p-5 border-l-4 border-l-red-500">
                <p className="text-slate-300 text-sm italic">
                  "We built the system so that even we cannot misuse your data. The Portal Admin cannot read a single document —
                  not because of a policy, but because the database refuses the query."
                </p>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ── Trust Architecture (universal) ── */}
      <section className="bg-slate-900 py-16 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-10">
            <p className="text-xs font-bold text-indigo-400 tracking-widest uppercase mb-3">Security by design</p>
            <h2 className="text-3xl font-extrabold text-white mb-3">
              7-layer trust architecture — <span style={{ background: GRAD, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>applies to everyone</span>
            </h2>
            <p className="text-slate-400 text-sm max-w-xl mx-auto">
              Misuse is structurally impossible. These controls work regardless of who has the credentials —
              employer, admin, or PRANA itself.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 gap-3 mb-8">
            {CISO_LAYERS.map((l) => (
              <div key={l.n} className="flex items-start gap-4 bg-white/5 border border-white/10 rounded-2xl px-5 py-4">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-extrabold flex-shrink-0"
                  style={{ background: GRAD }}>
                  {l.n}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-[10px] font-bold rounded-full px-2 py-0.5" style={{ color: '#818CF8', background: 'rgba(99,102,241,0.15)' }}>
                      {l.label}
                    </span>
                    <span className="text-sm font-semibold text-white">{l.title}</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">{l.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
            {CISO_STATS.map(s => (
              <div key={s.value} className="bg-white/5 border border-white/10 rounded-2xl p-4 text-center">
                <div className="text-2xl font-extrabold mb-1"
                  style={{ background: GRAD, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>
                  {s.value}
                </div>
                <div className="text-[10px] text-slate-400 leading-tight">{s.label}</div>
              </div>
            ))}
          </div>

          <div className="border-l-4 border-l-indigo-500 bg-white/5 rounded-r-2xl px-6 py-4">
            <p className="text-slate-300 text-sm italic">
              "We built the system so that even we cannot misuse your data. The Portal Admin cannot read a single document —
              not because of a policy, but because the database refuses the query."
            </p>
            <p className="text-indigo-400 text-xs mt-2 font-semibold">— PRANA Architecture Principle</p>
          </div>
        </div>
      </section>

      {/* ── What's Live + What's Coming ── */}
      <section className="max-w-5xl mx-auto px-6 py-16">
        <div className="text-center mb-10">
          <p className="text-xs font-bold text-indigo-500 tracking-widest uppercase mb-3">Product roadmap</p>
          <h2 className="text-3xl font-extrabold text-slate-900 mb-3">
            <GradText>Phase I live.</GradText> Phase II — the intelligent vault.
          </h2>
          <p className="text-slate-400 text-sm max-w-lg mx-auto">
            Great product companies show you where they are and where they're going.
            Phase I is complete. Phase II makes it extraordinary.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 gap-6">
          {/* Phase I */}
          <div className="rounded-3xl border-2 border-emerald-200 bg-emerald-50/40 p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-xl bg-emerald-500 flex items-center justify-center">
                <span className="text-white text-sm font-bold">✓</span>
              </div>
              <div>
                <p className="font-bold text-slate-900 text-base">Phase I — Live Now</p>
                <p className="text-xs text-emerald-600">Enterprise pilot-ready · DPDP Act 2023 compliant</p>
              </div>
            </div>
            <div className="space-y-2.5">
              {[
                { icon: '🗄',  label: 'My Vault',              sub: 'All documents, all employers, one place' },
                { icon: '↗',  label: 'C-Share',               sub: 'Cryptographic verification. Bank scans QR.' },
                { icon: '📋',  label: 'Activity Log',           sub: 'Every access, push, and share event' },
                { icon: '🔔',  label: 'Smart Alerts',           sub: 'Proactive, not passive' },
                { icon: '⚖',  label: 'DPDP Rights Centre',     sub: 'All 6 rights, properly implemented' },
                { icon: '📅',  label: 'Career Timeline',        sub: 'AI built your career story' },
                { icon: '📊',  label: 'Vault Health Score',     sub: 'Document completeness %' },
                { icon: '📦',  label: 'Share Bundles',          sub: 'Loan, BGV, visa — one link' },
                { icon: '📨',  label: 'Document Request Flow',  sub: 'Ask your employer for missing docs' },
                { icon: '🔍',  label: 'Privacy Cockpit',        sub: 'DPDP S.11 — every field, every access' },
                { icon: '⬆',  label: 'Bulk Upload + AI Screen', sub: 'Content policy, contamination detection' },
                { icon: '📊',  label: 'CHRO Vault Dashboard',   sub: 'Completeness, compliance calendar, digest' },
                { icon: '💰',  label: 'CFO Payroll Intelligence',sub: 'Aggregate only. Consent-based. ≥30 cohort' },
              ].map(f => (
                <div key={f.label} className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-emerald-100 border border-emerald-300 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-emerald-600 text-[9px] font-bold">✓</span>
                  </div>
                  <div>
                    <span className="text-xs font-semibold text-slate-800">{f.icon} {f.label}</span>
                    <span className="text-[10px] text-slate-400 ml-1.5">{f.sub}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Phase II */}
          <div className="rounded-3xl border-2 border-indigo-100 bg-indigo-50/30 p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: GRAD }}>
                <span className="text-white text-sm font-bold">→</span>
              </div>
              <div>
                <p className="font-bold text-slate-900 text-base">Phase II — The Intelligent Vault</p>
                <p className="text-xs text-indigo-500">Phase I is complete without this. Phase II makes it extraordinary.</p>
              </div>
            </div>
            <div className="space-y-2.5">
              {[
                { icon: '🪪',  label: 'Career Passport',           sub: 'One public link. Recruiter scans QR — verified instantly.', tag: 'Employee' },
                { icon: '🔎',  label: 'Employer Intelligence',     sub: 'Slip says "Engineer." Letter says "Senior Engineer." PRANA catches it.', tag: 'Employee' },
                { icon: '🧾',  label: 'Tax Document Organiser',    sub: 'Gross income, total TDS, annual summary. Ready for your CA.', tag: 'Employee' },
                { icon: '💬',  label: 'AI Vault Assistant',        sub: '"What was my salary in March 2022?" Natural language queries.', tag: 'Employee' },
                { icon: '📱',  label: 'Native Mobile App',         sub: 'iOS and Android. Web-first Phase I. Native after PMF.', tag: 'Employee' },
                { icon: '🤝',  label: 'Gig Worker Mode',           sub: '50M+ gig workers. Self-upload + AI extraction + career record.', tag: 'Employee' },
                { icon: '📈',  label: 'Full Salary Benchmarking',  sub: 'Verified cross-org bands. Needs 50+ orgs. Consent-based.', tag: 'CFO' },
                { icon: '🤖',  label: 'CHRO AI Assistant',         sub: '"What’s our Form-16 issuance rate for Q2?" — answered instantly.', tag: 'CHRO' },
                { icon: '💬',  label: 'WhatsApp + DigiLocker + EPFO', sub: 'India-first channels. Government API linkage.', tag: 'Platform' },
                { icon: '🔗',  label: 'Third-party Verification API', sub: 'Banks, NBFCs, BGV firms. Replaces the phone call to HR.', tag: 'Platform' },
              ].map(f => (
                <div key={f.label} className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-indigo-100 border border-indigo-200 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-indigo-400 text-[9px] font-bold">→</span>
                  </div>
                  <div>
                    <span className="text-xs font-semibold text-slate-800">{f.icon} {f.label}</span>
                    <span className="text-[9px] font-bold text-indigo-400 bg-indigo-100 rounded-full px-1.5 py-0.5 ml-1.5">{f.tag}</span>
                    <p className="text-[10px] text-slate-400 mt-0.5 leading-relaxed">{f.sub}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── For Organisations ── */}
      <section className="max-w-6xl mx-auto px-6 pt-10 pb-16">
        <div className="text-center mb-10">
          <p className="text-xs font-bold text-indigo-500 tracking-widest uppercase mb-3">For organisations</p>
          <h2 className="text-4xl font-extrabold text-slate-900">
            Every role in your org, <GradText>covered</GradText>
          </h2>
          <p className="text-slate-400 text-sm mt-3 max-w-lg mx-auto">
            Onboard in 15 minutes. No IT integration required to start. HRMS API available for automated pushes.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 gap-4 mb-8">
          {ORG_FEATURES.map(f => (
            <div key={f.title} className="bg-slate-50 border border-slate-100 rounded-2xl p-5 flex items-start gap-4">
              <div className="text-2xl">{f.icon}</div>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h4 className="font-semibold text-slate-800 text-sm">{f.title}</h4>
                  <span className="text-[10px] font-bold text-slate-400 bg-white border border-slate-200 rounded-full px-2 py-0.5">
                    {f.role}
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="grid sm:grid-cols-2 gap-6">
          <div className="bg-white rounded-3xl border border-slate-200 p-8">
            <div className="w-12 h-12 rounded-2xl bg-indigo-100 flex items-center justify-center text-2xl mb-5">🏢</div>
            <h3 className="text-xl font-bold text-slate-900 mb-2">Register your organisation</h3>
            <p className="text-slate-500 text-sm leading-relaxed mb-6">
              Push salary slips, Form 16, and HR letters to employee vaults automatically.
              Connects via portal upload or HRMS API. Onboard in 15 minutes.
            </p>
            <GradBtn onClick={() => navigate('/register')} className="w-full !py-3 !rounded-xl">
              Register now →
            </GradBtn>
          </div>
          <div className="bg-white rounded-3xl border border-slate-200 p-8">
            <div className="w-12 h-12 rounded-2xl bg-sky-100 flex items-center justify-center text-2xl mb-5">📱</div>
            <h3 className="text-xl font-bold text-slate-900 mb-2">For employees</h3>
            <p className="text-slate-500 text-sm leading-relaxed mb-6">
              Your vault activates the moment your employer joins PRANA and pushes your first document.
              Access your career vault on the web or download the PRANA mobile app.
            </p>
            <div className="flex flex-col gap-2">
              <GradBtn onClick={() => navigate('/emp/login')} className="w-full !py-3 !rounded-xl">
                Access your vault →
              </GradBtn>
              <button className="w-full border border-slate-200 text-slate-600 font-semibold rounded-xl py-2.5 text-sm hover:bg-slate-50 transition-colors">
                Download the PRANA app
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Privacy promise dark section ── */}
      <section className="bg-slate-900 py-16 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="w-14 h-14 rounded-2xl mx-auto mb-6 flex items-center justify-center text-3xl"
            style={{ background: GRAD }}>🔒</div>
          <h2 className="text-3xl font-extrabold text-white mb-3">Privacy by design. Not by policy.</h2>
          <p className="text-slate-500 text-sm mb-10">
            Non-negotiable. Structural. Cannot be switched off by any administrator.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { icon: '🔐', title: 'Zero Raw ₹ Stored',         desc: 'Salary figures never enter our database. AI extracts insights only — not values.' },
              { icon: '🛡', title: 'Per-Employee Encryption',    desc: 'Every person has their own encryption key. One breach = one person. Never the org.' },
              { icon: '👁', title: 'Zero Platform Access',       desc: 'Platform Admin cannot read a single document. The database refuses the query.' },
              { icon: '📜', title: 'Immutable Audit Event',      desc: 'Every access is logged forever. No UPDATE or DELETE on audit records. Ever.' },
              { icon: '🔏', title: 'Format-Preserving PAN',      desc: 'PAN is tokenised in 2ms and destroyed. No row links your PAN to your name.' },
              { icon: '🇮🇳', title: 'DPDP Act 2023 Compliant',  desc: 'All 6 data principal rights implemented. Consent, Erasure, Grievance, Nomination.' },
              { icon: '📅', title: '7-Year Audit Retention',     desc: 'Regulatory-grade audit trail. Hot storage for 2 years, cold archive for 7.' },
              { icon: '✍', title: 'Consent-First Always',        desc: 'No document reaches an employer dashboard unless the employee has explicitly consented.' },
            ].map(f => (
              <div key={f.title}
                className="bg-white/5 border border-white/10 rounded-2xl p-4 text-left
                           hover:bg-white/10 hover:border-white/20 transition-all duration-200 group">
                <div className="text-2xl mb-3 group-hover:scale-110 transition-transform duration-200 inline-block">{f.icon}</div>
                <p className="text-white font-bold text-sm mb-1.5">{f.title}</p>
                <p className="text-slate-400 text-xs leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div ref={contactRef} />

      {/* ── Footer ── */}
      <footer className="bg-slate-950 text-slate-400 pt-14 pb-8 px-6">
        <div className="max-w-6xl mx-auto">
          {/* Top: brand + columns */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-10 mb-12">
            {/* Brand */}
            <div className="col-span-2 sm:col-span-1">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: GRAD }}>
                  <span className="text-white font-bold text-sm">P</span>
                </div>
                <span className="font-mono font-bold text-white text-lg tracking-tight">
                  PRANA<span className="text-indigo-400">·</span>
                </span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed mb-3">
                Personal Repository &amp; Networked Authentications
              </p>
              <p className="text-[11px] text-slate-600 leading-relaxed">
                Career document vault for every Indian worker. DPDP Act 2023 compliant.
              </p>
              <div className="flex gap-2 mt-4">
                <span className="text-[10px] bg-emerald-900/50 text-emerald-400 border border-emerald-800 rounded-full px-2.5 py-1 font-semibold">Phase I Live</span>
                <span className="text-[10px] bg-indigo-900/50 text-indigo-400 border border-indigo-800 rounded-full px-2.5 py-1 font-semibold">Pilot-Ready</span>
              </div>
            </div>

            {/* Product */}
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">Product</p>
              <ul className="space-y-2.5">
                {[
                  ['My Vault', '#'],
                  ['C-Share', '#'],
                  ['Career Timeline', '#'],
                  ['DPDP Rights Centre', '#'],
                  ['Vault Health Score', '#'],
                  ['Share Bundles', '#'],
                  ['Ask PRANA AI', '#'],
                ].map(([l, h]) => (
                  <li key={l}><a href={h} className="text-xs hover:text-white transition-colors">{l}</a></li>
                ))}
              </ul>
            </div>

            {/* For Organisations */}
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">For Organisations</p>
              <ul className="space-y-2.5">
                {[
                  ['Register your org', '/register'],
                  ['HRMS API integration', '#'],
                  ['CHRO Dashboard', '#'],
                  ['CFO Analytics', '#'],
                  ['CISO Security View', '#'],
                  ['Employee vault login', '/emp/login'],
                  ['OA Portal login', '/org/login'],
                  ['Platform Admin', '/admin/login'],
                ].map(([l, h]) => (
                  <li key={l}><a href={h} className="text-xs hover:text-white transition-colors">{l}</a></li>
                ))}
              </ul>
            </div>

            {/* Company */}
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">Company</p>
              <ul className="space-y-2.5">
                {[
                  ['About PRANA', '#'],
                  ['Security architecture', '/legal/privacy#security'],
                  ['DPDP compliance', '/legal/privacy#dpdp'],
                  ['Request a demo', '#'],
                  ['Blog', '#'],
                ].map(([l, h]) => (
                  <li key={l}><a href={h} className="text-xs hover:text-white transition-colors">{l}</a></li>
                ))}
              </ul>
            </div>

            {/* Legal */}
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">Legal</p>
              <ul className="space-y-2.5">
                {[
                  ['Privacy policy',            '/legal/privacy'],
                  ['Terms of use',              '/legal/terms'],
                  ['Data Processing Agreement', '/legal/dpa'],
                  ['Cookie policy',             '/legal/cookies'],
                  ['Grievance Redressal',       '/legal/grievance'],
                  ['API Terms',                 '/legal/api-terms'],
                ].map(([l, h]) => (
                  <li key={l}><a href={h} className="text-xs hover:text-white transition-colors">{l}</a></li>
                ))}
              </ul>
            </div>
          </div>

          {/* Divider */}
          <div className="border-t border-white/5 pt-6 flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-[11px] text-slate-600">© 2025 PRANA Technologies Pvt Ltd. All rights reserved. Built for India.</p>
            <div className="flex items-center gap-4">
              {['AES-256', 'DPDP 2023', 'AWS KMS', 'YugabyteDB'].map(t => (
                <span key={t} className="text-[10px] text-slate-600 border border-white/5 rounded px-2 py-0.5">{t}</span>
              ))}
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
