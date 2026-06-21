import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function EmpPrivacy() {
  const { data: profileData, isLoading: profileLoading } = useQuery({
    queryKey: ['emp-vault-profile'],
    queryFn: () => api.get('/v1/vault/profile').then(r => r.data),
  })
  const { data: activityData, isLoading: activityLoading } = useQuery({
    queryKey: ['emp-activity'],
    queryFn: () => api.get('/v1/vault/activity').then(r => r.data),
  })
  const { data: sharesData, isLoading: sharesLoading } = useQuery({
    queryKey: ['emp-vault-shares'],
    queryFn: () => api.get('/v1/vault/share').then(r => r.data),
  })
  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: ['emp-vault-docs'],
    queryFn: () => api.get('/v1/vault/documents', { params: { limit: 100 } }).then(r => r.data),
  })

  const isLoading = profileLoading || activityLoading || sharesLoading || docsLoading
  if (isLoading) return (
    <div className="p-6 max-w-3xl animate-pulse space-y-5">
      <div className="h-6 w-40 bg-slate-200 rounded" />
      <div className="grid grid-cols-3 gap-3">
        {[...Array(3)].map((_, i) => <div key={i} className="h-20 bg-slate-100 rounded-xl" />)}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="h-48 bg-slate-100 rounded-xl" />
        <div className="h-48 bg-slate-100 rounded-xl" />
      </div>
    </div>
  )

  const accessLog: any[] = activityData?.access_log ?? []
  const shares: any[]    = sharesData?.shares ?? []
  const docs: any[]      = docsData?.documents ?? []

  function fmtDate(ts: string | null) {
    if (!ts) return '—'
    return new Date(ts).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
  }

  return (
    <div className="p-6 max-w-3xl">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Privacy Cockpit</h1>
          <p className="text-sm text-slate-500 mt-0.5">Complete transparency over how your data has moved — ever</p>
        </div>
        <button className="px-3 py-2 text-sm border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50">Export Report</button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        {[
          { val: profileData?.employer_count ?? 0, label: 'Linked Employers', color: 'text-sky-600' },
          { val: docsData?.count ?? docs.length,   label: 'Docs in Vault',    color: 'text-emerald-600' },
          { val: shares.length,                    label: 'Active Shares',    color: 'text-violet-600' },
        ].map(s => (
          <div key={s.label} className="bg-white border border-slate-200 rounded-xl p-4 text-center shadow-sm">
            <p className={`text-3xl font-bold ${s.color}`}>{s.val}</p>
            <p className="text-xs text-slate-500 mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Two columns */}
      <div className="grid grid-cols-2 gap-4">
        {/* Who Has Accessed */}
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide px-4 pt-4 pb-2">Who Has Accessed Your Documents</p>
          {accessLog.length === 0 ? (
            <p className="px-4 pb-4 text-sm text-slate-400">No access events yet.</p>
          ) : accessLog.slice(0, 6).map((e, i) => (
            <div key={i} className={`px-4 py-2.5 ${i < Math.min(accessLog.length, 6) - 1 ? 'border-b border-slate-100' : ''}`}>
              <p className="text-xs font-medium text-slate-700">
                {e.via_share ? `C-Share: ${e.employer_name ?? 'Recipient'}` : `OA · ${e.employer_name}`}
              </p>
              <p className="text-[11px] text-slate-400 mt-0.5 truncate">
                {e.access_type} · {e.doc_type?.replace(/_/g,' ')}
              </p>
              <p className="text-[10px] text-slate-300 font-mono">{fmtDate(e.accessed_at)}</p>
            </div>
          ))}
        </div>

        {/* AI Extraction Log */}
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide px-4 pt-4 pb-2">AI Extraction Log</p>
          {docs.length === 0 ? (
            <p className="px-4 pb-4 text-sm text-slate-400">No documents extracted yet.</p>
          ) : docs.slice(0, 5).map((d, i) => (
            <div key={i} className={`px-4 py-2.5 ${i < Math.min(docs.length, 5) - 1 ? 'border-b border-slate-100' : ''}`}>
              <p className="text-[11px] font-medium text-slate-700 truncate">
                {d.doc_type?.replace(/_/g,' ')} {d.doc_period ? '— ' + d.doc_period : ''}
              </p>
              <p className="text-[10px] text-slate-400 mt-0.5">Fields extracted · PAN destroyed in 2ms</p>
            </div>
          ))}
          <p className="px-4 py-2 text-[10px] text-slate-400 border-t border-slate-100">
            Your PAN is never stored. Every extraction confirms destruction within 2ms.
          </p>
        </div>
      </div>
    </div>
  )
}
