import { useQuery } from '@tanstack/react-query'
import { ShieldCheck, AlertCircle, CheckCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

const RISK_COLORS: Record<string, string> = {
  LOW:    'bg-emerald-50 text-emerald-700',
  MEDIUM: 'bg-amber-50 text-amber-700',
  HIGH:   'bg-red-50 text-red-700',
}

export function CompliancePosture() {
  const { data } = useQuery({
    queryKey: ['chro-compliance-posture'],
    queryFn: () => api.get('/v1/chro/compliance-posture').then(r => r.data),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Compliance Posture</h1>
          <p className="text-xs text-slate-400 mt-0.5">DPDP Act 2023 · 7-year audit retention</p>
        </div>
        <div className="flex items-center gap-2">
          <ShieldCheck size={20} className={
            data?.overall_risk === 'LOW' ? 'text-emerald-500' :
            data?.overall_risk === 'MEDIUM' ? 'text-amber-500' : 'text-red-500'
          } />
          <span className={`text-sm font-semibold px-3 py-1 rounded-full ${RISK_COLORS[data?.overall_risk ?? 'LOW'] ?? ''}`}>
            {data?.overall_risk ?? 'LOW'} risk
          </span>
        </div>
      </div>

      {/* Score cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Consent coverage',   value: data?.consent_pct != null ? `${data.consent_pct}%` : '—', target: '100%' },
          { label: 'Vault completeness', value: data?.vault_completeness_pct != null ? `${data.vault_completeness_pct}%` : '—', target: '90%' },
          { label: 'Erasure SLA met',    value: data?.erasure_sla_pct != null ? `${data.erasure_sla_pct}%` : '—', target: '100%' },
          { label: 'Grievance resolved', value: data?.grievance_resolved_pct != null ? `${data.grievance_resolved_pct}%` : '—', target: '95%' },
        ].map(c => (
          <div key={c.label} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <p className="text-2xl font-bold font-mono text-slate-800">{c.value}</p>
            <p className="text-xs text-slate-500 mt-1">{c.label}</p>
            <p className="text-xs text-slate-300 mt-0.5">target {c.target}</p>
          </div>
        ))}
      </div>

      {/* DPDP checklist */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <h2 className="font-medium text-slate-800 mb-4">DPDP Act 2023 checklist</h2>
        <div className="space-y-2">
          {(data?.checklist ?? []).map((item: any, i: number) => (
            <div key={i} className="flex items-start gap-3 py-2 border-b border-slate-50 last:border-0">
              {item.status === 'COMPLIANT'
                ? <CheckCircle size={15} className="text-emerald-500 mt-0.5 shrink-0" />
                : <AlertCircle size={15} className="text-amber-500 mt-0.5 shrink-0" />}
              <div className="flex-1">
                <p className="text-sm font-medium text-slate-700">{item.requirement}</p>
                {item.statutory_ref && (
                  <p className="text-xs text-slate-400 mt-0.5 font-mono">{item.statutory_ref}</p>
                )}
                {item.note && <p className="text-xs text-slate-500 mt-0.5">{item.note}</p>}
              </div>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${
                item.status === 'COMPLIANT' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
              }`}>{item.status}</span>
            </div>
          ))}
          {!data?.checklist?.length && (
            <p className="text-sm text-slate-400 text-center py-4">Checklist loading…</p>
          )}
        </div>
      </div>

      {/* Open action items */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-medium text-slate-800">Open action items</h2>
        </div>
        <div className="divide-y divide-slate-50">
          {(data?.action_items ?? []).map((a: any, i: number) => (
            <div key={i} className="px-5 py-3 flex items-center gap-4">
              <AlertCircle size={14} className="text-amber-500 shrink-0" />
              <span className="flex-1 text-sm text-slate-700">{a.description}</span>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${RISK_COLORS[a.risk] ?? ''}`}>{a.risk}</span>
              <span className="text-xs text-slate-400 font-mono whitespace-nowrap">Due {fmtDateTime(a.due_date)}</span>
            </div>
          ))}
          {!data?.action_items?.length && (
            <p className="px-5 py-8 text-sm text-slate-400 text-center">No open action items.</p>
          )}
        </div>
      </div>
    </div>
  )
}
