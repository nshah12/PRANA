import { useNavigate } from 'react-router-dom'

const GRAD = 'linear-gradient(135deg, #6366F1 0%, #22D3EE 55%, #34D399 100%)'

const FOOTER_LINKS = {
  Product: [
    ['My Vault', '/'],
    ['C-Share', '/'],
    ['Career Timeline', '/'],
    ['DPDP Rights Centre', '/'],
    ['Vault Health Score', '/'],
    ['Share Bundles', '/'],
    ['Ask PRANA AI', '/'],
  ],
  'For Organisations': [
    ['Register your org', '/register'],
    ['HRMS API integration', '/'],
    ['CHRO Dashboard', '/org/login'],
    ['CFO Analytics', '/org/login'],
    ['CISO Security View', '/org/login'],
    ['OA Portal login', '/org/login'],
    ['Platform Admin', '/admin/login'],
  ],
  Company: [
    ['About PRANA', '/'],
    ['Security architecture', '/legal/privacy#security'],
    ['DPDP compliance', '/legal/privacy#dpdp'],
    ['Request a demo', '/'],
    ['Blog', '/'],
  ],
  Legal: [
    ['Privacy policy',            '/legal/privacy'],
    ['Terms of use',              '/legal/terms'],
    ['Data Processing Agreement', '/legal/dpa'],
    ['Cookie policy',             '/legal/cookies'],
    ['Grievance Redressal',       '/legal/grievance'],
    ['API Terms',                 '/legal/api-terms'],
  ],
}

function LegalFooter() {
  return (
    <footer className="bg-slate-950 text-slate-400 pt-14 pb-8 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-10 mb-12">
          <div className="col-span-2 sm:col-span-1">
            <a href="/" className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: GRAD }}>
                <span className="text-white font-bold text-sm">P</span>
              </div>
              <span className="font-mono font-bold text-white text-lg tracking-tight">
                PRANA<span className="text-indigo-400">·</span>
              </span>
            </a>
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

          {Object.entries(FOOTER_LINKS).map(([heading, links]) => (
            <div key={heading}>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">{heading}</p>
              <ul className="space-y-2.5">
                {links.map(([label, href]) => (
                  <li key={label}><a href={href} className="text-xs hover:text-white transition-colors">{label}</a></li>
                ))}
              </ul>
            </div>
          ))}
        </div>

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
  )
}

interface Props {
  title: string
  subtitle?: string
  badge?: string
  children: React.ReactNode
}

export function LegalLayout({ title, subtitle, badge = 'Legal', children }: Props) {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-white flex flex-col">
      {/* Minimal nav */}
      <nav className="sticky top-0 z-50 bg-white/95 backdrop-blur border-b border-slate-100">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <button onClick={() => navigate('/')} className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: GRAD }}>
              <span className="text-white font-bold text-xs">P</span>
            </div>
            <span className="font-mono font-bold text-slate-900">PRANA<span className="text-indigo-500">·</span></span>
          </button>
          <button onClick={() => navigate('/')}
            className="text-xs text-slate-500 hover:text-slate-800 flex items-center gap-1">
            ← Back to home
          </button>
        </div>
      </nav>

      {/* Page header */}
      <div className="bg-slate-50 border-b border-slate-100 py-10 px-6">
        <div className="max-w-3xl mx-auto">
          <span className="text-[10px] font-bold text-indigo-500 uppercase tracking-widest">{badge}</span>
          <h1 className="text-3xl font-extrabold text-slate-900 mt-2 mb-2">{title}</h1>
          {subtitle && <p className="text-slate-500 text-sm">{subtitle}</p>}
        </div>
      </div>

      {/* Content */}
      <main className="flex-1 max-w-3xl mx-auto w-full px-6 py-10">
        <div className="prose prose-sm prose-slate max-w-none">
          {children}
        </div>
      </main>

      <LegalFooter />
    </div>
  )
}
