import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

function Toggle({ on, onChange }: { on: boolean; onChange: () => void }) {
  return (
    <button onClick={onChange}
      className={`relative inline-flex w-9 h-5 rounded-full transition-colors shrink-0 ${on ? 'bg-emerald-500' : 'bg-slate-200'}`}>
      <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${on ? 'translate-x-4' : 'translate-x-0'}`}/>
    </button>
  )
}

function ToggleRow({ label, sub, on, onChange }: { label: string; sub: string; on: boolean; onChange: () => void }) {
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-slate-100 last:border-0">
      <div className="flex-1">
        <p className="text-sm font-medium text-slate-800">{label}</p>
        <p className="text-xs text-slate-400">{sub}</p>
      </div>
      <Toggle on={on} onChange={onChange} />
    </div>
  )
}

export function EmpSettings() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['emp-vault-profile'],
    queryFn: () => api.get('/v1/vault/profile').then(r => r.data),
  })

  if (isLoading) return (
    <div className="p-6 max-w-3xl animate-pulse space-y-4">
      <div className="h-6 w-44 bg-slate-200 rounded" />
      <div className="grid grid-cols-2 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="h-48 bg-slate-100 rounded-xl" />)}
      </div>
    </div>
  )
  if (isError) return (
    <div className="p-6 flex flex-col items-center justify-center py-20 text-slate-400">
      <p className="text-sm">Failed to load profile.</p>
      <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">Retry</button>
    </div>
  )

  const employers: any[] = data?.employers ?? []
  const vaultUrl = data?.vault_url ?? 'prana.in/vault/—'
  const mobile   = data?.mobile ?? '—'

  const [mfa, setMfa] = useState({ totp: true, sms: true, loginAlert: true, accessAlert: true })
  const [notif, setNotif] = useState({ newDoc: true, shareAccessed: true, shareExpiry: false })

  const ORG_COLORS = ['bg-sky-500','bg-violet-500','bg-emerald-500','bg-amber-500']

  function fmtDate(d: string | null) {
    if (!d) return 'Present'
    return new Date(d).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-xl font-semibold text-slate-800 mb-1">Profile & Settings</h1>
      <p className="text-sm text-slate-500 mb-5">Your vault identity and preferences</p>

      <div className="grid grid-cols-2 gap-4">
        {/* Vault Identity */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Vault Identity</p>
          {[
            { label: 'Mobile (Login)', val: mobile, badge: true },
            { label: 'NIK (PAN) — Stored Encrypted', val: 'tok:' + (data?.employee_user_id ?? '').replace(/-/g,'').slice(0,6) + '…' + (data?.employee_user_id ?? '').replace(/-/g,'').slice(-4), mono: true, sub: 'Plaintext PAN never displayed or stored' },
            { label: 'Vault URL', val: vaultUrl, mono: true },
          ].map(row => (
            <div key={row.label}>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 font-mono mb-0.5">{row.label}</p>
              <div className="flex items-center gap-2">
                <p className={`text-sm ${row.mono ? 'font-mono text-sky-600' : 'text-slate-800'}`}>{row.val}</p>
                {row.badge && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">✓ Verified</span>}
              </div>
              {row.sub && <p className="text-[10px] text-slate-400 mt-0.5">{row.sub}</p>}
            </div>
          ))}
        </div>

        {/* MFA Settings */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-3">MFA Settings</p>
          <ToggleRow label="TOTP Authenticator" sub="Google Authenticator / Authy" on={mfa.totp} onChange={() => setMfa(p => ({...p, totp: !p.totp}))} />
          <ToggleRow label="SMS OTP fallback" sub="Used when TOTP unavailable" on={mfa.sms} onChange={() => setMfa(p => ({...p, sms: !p.sms}))} />
          <ToggleRow label="Login notifications" sub="Alert on every new login" on={mfa.loginAlert} onChange={() => setMfa(p => ({...p, loginAlert: !p.loginAlert}))} />
          <ToggleRow label="Document access alerts" sub="Alert when shared doc is accessed" on={mfa.accessAlert} onChange={() => setMfa(p => ({...p, accessAlert: !p.accessAlert}))} />
        </div>

        {/* Linked Employers */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-3">Linked Employers</p>
          {employers.length === 0 ? <p className="text-sm text-slate-400">No employers linked yet.</p> : (
            <div className="space-y-2">
              {employers.map((e: any, i: number) => {
                const isActive = !(e.dol ?? e.to)
                return (
                  <div key={e.tenant_id ?? i} className="flex items-center gap-3 p-2.5 rounded-lg bg-slate-50">
                    <div className={`w-2 h-2 rounded-full shrink-0 ${isActive ? ORG_COLORS[i % ORG_COLORS.length] : 'bg-slate-300'}`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-800 truncate">{e.tenant_name ?? e.name}</p>
                      <p className="text-[10px] text-slate-400 font-mono">
                        {fmtDate(e.doj ?? e.from)} – {fmtDate(e.dol ?? e.to)}
                      </p>
                    </div>
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${isActive ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-slate-100 text-slate-500 border-slate-200'}`}>
                      {isActive ? 'Active' : 'Alumni'}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Notification Preferences */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-3">Notification Preferences</p>
          <ToggleRow label="New document pushed" sub="When employer pushes a document" on={notif.newDoc} onChange={() => setNotif(p => ({...p, newDoc: !p.newDoc}))} />
          <ToggleRow label="Share link accessed" sub="When recipient opens your link" on={notif.shareAccessed} onChange={() => setNotif(p => ({...p, shareAccessed: !p.shareAccessed}))} />
          <ToggleRow label="Share expiry reminder" sub="24hrs before a share expires" on={notif.shareExpiry} onChange={() => setNotif(p => ({...p, shareExpiry: !p.shareExpiry}))} />
        </div>
      </div>
    </div>
  )
}
