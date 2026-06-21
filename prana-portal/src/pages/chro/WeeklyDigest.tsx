import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Send, Mail, TrendingUp, TrendingDown, AlertTriangle, Users, FileText, Settings } from 'lucide-react'
import { api } from '@/lib/api'
import { Link } from 'react-router-dom'
import { DigestDatePicker, type DateWindow } from '@/components/digest/DigestDatePicker'

function todayISO() { return new Date().toISOString().split('T')[0] }
function daysAgoISO(n: number) {
  const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().split('T')[0]
}

export function WeeklyDigest() {
  const [window, setWindow] = useState<DateWindow>({ from: daysAgoISO(7), to: todayISO() })

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['chro-digest', window.from, window.to],
    queryFn:  () => api.get(`/v1/chro/digest/weekly?from=${window.from}&to=${window.to}`)
                       .then(r => r.data.digest),
    enabled: !!window.from && !!window.to,
  })

  const sendTest = useMutation({
    mutationFn: () => api.post('/v1/chro/digest/weekly/send-test'),
  })

  // Header + date picker always visible — not gated behind loading/error
  const header = (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">CHRO Digest</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {data ? `${data.from} → ${data.to}` : 'Loading…'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/org/digest-settings"
                className="flex items-center gap-1.5 text-sm text-slate-500 border border-slate-200
                           px-3 py-1.5 rounded-lg hover:bg-canvas2">
            <Settings size={13}/> Settings
          </Link>
          <button onClick={() => sendTest.mutate()}
                  disabled={sendTest.isPending}
                  className="flex items-center gap-1.5 text-sm font-medium text-indigo-600
                             border border-indigo-200 px-3 py-1.5 rounded-lg hover:bg-indigo-50">
            <Send size={13}/> {sendTest.isPending ? 'Sending…' : 'Send test'}
          </button>
        </div>
      </div>
      <DigestDatePicker
        accentColor="bg-indigo-600"
        accentText="text-indigo-600"
        accentBorder="border-indigo-600"
        onChange={setWindow}
      />
    </div>
  )

  if (isLoading) return (
    <div className="space-y-6 max-w-2xl">
      {header}
      <div className="animate-pulse space-y-4">
        <div className="grid grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-slate-100 rounded-xl" />)}
        </div>
        <div className="h-48 bg-slate-100 rounded-xl" />
      </div>
    </div>
  )

  if (isError) return (
    <div className="space-y-6 max-w-2xl">
      {header}
      <div className="flex flex-col items-center justify-center py-20 text-slate-400">
        <p className="text-sm">Failed to load digest.</p>
        <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">Retry</button>
      </div>
    </div>
  )

  const stats = [
    { label: 'Docs processed',     value: data?.docs_processed ?? '—',         up: true  },
    { label: 'Vault completeness', value: data?.vault_completeness_pct != null ? `${data.vault_completeness_pct}%` : '—', up: true },
    { label: 'Exceptions open',    value: data?.exceptions_open ?? '—',         up: false },
    { label: 'Alumni self-served', value: data?.alumni_self_served ?? '—',      up: true  },
  ]

  return (
    <div className="space-y-6 max-w-2xl">
      {header}

      <div className="grid grid-cols-4 gap-3">
        {stats.map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-100 shadow-sm p-4">
            <p className="text-xs text-slate-400">{s.label}</p>
            <p className="text-xl font-bold font-mono text-slate-800 mt-1">{s.value}</p>
            <div className={`flex items-center gap-1 mt-1 text-xs font-medium ${s.up ? 'text-emerald-600' : 'text-red-500'}`}>
              {s.up ? <TrendingUp size={10}/> : <TrendingDown size={10}/>}
              {s.up ? 'up' : 'needs action'}
            </div>
          </div>
        ))}
      </div>

      {(data?.docs_by_type?.length ?? 0) > 0 && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
          <div className="flex items-center gap-2 mb-4">
            <FileText size={14} className="text-slate-400"/>
            <h2 className="text-sm font-medium text-slate-700">Documents processed</h2>
          </div>
          <div className="space-y-2.5">
            {data.docs_by_type.map((row: any) => {
              const total = data.docs_by_type.reduce((s: number, r: any) => s + r.count, 0) || 1
              const pct = Math.round((row.count / total) * 100)
              return (
                <div key={row.doc_type} className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 w-28 text-right flex-shrink-0">
                    {row.doc_type.replace(/_/g, ' ')}
                  </span>
                  <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="text-xs text-slate-700 w-8 text-right font-mono">{row.count}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {(data?.vault_by_department?.length ?? 0) > 0 && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
          <div className="flex items-center gap-2 mb-4">
            <Users size={14} className="text-slate-400"/>
            <h2 className="text-sm font-medium text-slate-700">Vault completeness by department</h2>
          </div>
          <div className="space-y-2.5">
            {data.vault_by_department.map((row: any) => (
              <div key={row.department} className="flex items-center gap-3">
                <span className="text-xs text-slate-500 w-28 text-right flex-shrink-0">{row.department}</span>
                <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full"
                       style={{ width: `${row.score}%`, background: row.score >= 90 ? '#10b981' : row.score >= 75 ? '#6366f1' : '#f59e0b' }} />
                </div>
                <span className={`text-xs font-mono w-8 text-right font-medium
                  ${row.score >= 90 ? 'text-emerald-600' : row.score >= 75 ? 'text-indigo-600' : 'text-amber-600'}`}>
                  {row.score}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(data?.exceptions_open ?? 0) > 0 && (
        <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
          <AlertTriangle size={15} className="text-amber-500 mt-0.5 flex-shrink-0"/>
          <div>
            <p className="text-sm font-medium text-amber-800">
              {data.exceptions_open} open exception{data.exceptions_open !== 1 ? 's' : ''} need attention
            </p>
            <p className="text-xs text-amber-600 mt-0.5">
              Documents stuck in RESOLVING — OA-Admin identity match needed
            </p>
          </div>
        </div>
      )}

      <div className="border border-slate-200 rounded-xl overflow-hidden">
        <div className="bg-slate-50 px-4 py-2.5 flex items-center gap-2 border-b border-slate-200">
          <Mail size={13} className="text-slate-400"/>
          <span className="text-xs text-slate-400 font-mono">Email preview — sent to configured recipients</span>
        </div>
        <div className="px-4 py-3">
          <p className="text-xs text-slate-400">
            Configure recipients and schedule in{' '}
            <Link to="/org/digest-settings" className="text-indigo-600 hover:underline">Digest Settings</Link>.
          </p>
        </div>
      </div>
    </div>
  )
}
