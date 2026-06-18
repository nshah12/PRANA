import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle, Clock } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export function ConsentDashboard() {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: ['consent-dashboard'],
    queryFn: () => api.get('/org/consent').then(r => r.data),
  })

  const exportMut = useMutation({
    mutationFn: () => api.post('/org/consent/export', {}).then(r => r.data),
  })

  const stats = [
    { label: 'Consent granted', value: data?.granted ?? '—', icon: CheckCircle, color: 'text-emerald-600' },
    { label: 'Consent pending', value: data?.pending ?? '—', icon: Clock,        color: 'text-amber-600' },
    { label: 'Consent refused', value: data?.refused ?? '—', icon: XCircle,      color: 'text-red-600' },
    { label: 'Coverage',        value: data?.coverage_pct != null ? `${data.coverage_pct}%` : '—', icon: CheckCircle, color: 'text-indigo-600' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Consent Dashboard</h1>
          <p className="text-xs text-slate-400 mt-0.5">DPDP Act 2023 — employee consent status across your organisation</p>
        </div>
        <button
          onClick={() => exportMut.mutate()}
          disabled={exportMut.isPending}
          className="text-xs bg-indigo-600 text-white rounded-lg px-4 py-2 hover:bg-indigo-700 disabled:opacity-50"
        >
          {exportMut.isPending ? 'Exporting…' : 'Export CSV'}
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <s.icon size={18} className={`${s.color} mb-2`} />
            <p className="text-2xl font-bold font-mono text-slate-800">{s.value}</p>
            <p className="text-xs text-slate-500 mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-medium text-slate-800">Recent consent events</h2>
        </div>
        <div className="divide-y divide-slate-50">
          {(data?.events ?? []).map((e: any, i: number) => (
            <div key={i} className="px-5 py-3 flex items-center gap-4">
              {e.action === 'GRANTED' && <CheckCircle size={14} className="text-emerald-500 shrink-0" />}
              {e.action === 'REFUSED'  && <XCircle    size={14} className="text-red-500 shrink-0" />}
              {e.action === 'REVOKED'  && <XCircle    size={14} className="text-amber-500 shrink-0" />}
              <span className="flex-1 text-sm text-slate-700">{e.employee_name}</span>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                e.action === 'GRANTED' ? 'bg-emerald-50 text-emerald-700' :
                e.action === 'REFUSED' ? 'bg-red-50 text-red-700' :
                'bg-amber-50 text-amber-700'
              }`}>{e.action}</span>
              <span className="text-xs text-slate-400 font-mono whitespace-nowrap">{fmtDateTime(e.occurred_at)}</span>
            </div>
          ))}
          {!data?.events?.length && (
            <p className="px-5 py-8 text-sm text-slate-400 text-center">No consent events yet.</p>
          )}
        </div>
      </div>
    </div>
  )
}
