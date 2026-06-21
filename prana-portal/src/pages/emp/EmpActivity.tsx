import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

const DOT: Record<string, string> = {
  VIEW: 'bg-sky-400', DOWNLOAD: 'bg-sky-500',
  PUSH: 'bg-emerald-400', SHARE: 'bg-violet-400',
  REVOKE: 'bg-slate-400',
}

function dot(type: string) {
  return DOT[type?.toUpperCase()] ?? 'bg-slate-300'
}

function fmtTs(ts: string | null) {
  if (!ts) return '—'
  return new Date(ts).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function EmpActivity() {
  const { data, isLoading } = useQuery({
    queryKey: ['emp-activity'],
    queryFn: () => api.get('/v1/vault/activity').then(r => r.data),
  })

  const accessLog: any[]   = data?.access_log ?? []
  const pushes: any[]      = data?.pipeline_pushes ?? []

  // Merge and sort by time descending
  const events = [
    ...accessLog.map(e => ({ ...e, kind: 'access', ts: e.accessed_at })),
    ...pushes.map(e => ({ ...e, kind: 'push', ts: e.pushed_at })),
  ].sort((a, b) => new Date(b.ts ?? 0).getTime() - new Date(a.ts ?? 0).getTime())

  function eventLabel(e: any) {
    if (e.kind === 'push') return `${e.employer_name} pushed ${e.doc_type.replace(/_/g,' ')}${e.doc_period ? ' · ' + e.doc_period : ''} to your vault`
    if (e.via_share) return `Share recipient ${e.access_type.toLowerCase()}ed ${e.doc_type?.replace(/_/g,' ') ?? 'document'} via your share link`
    return `You ${e.access_type?.toLowerCase() ?? 'accessed'} ${e.doc_type?.replace(/_/g,' ') ?? 'document'}`
  }

  return (
    <div className="p-6 max-w-2xl">
      <h1 className="text-xl font-semibold text-slate-800 mb-1">Activity Log</h1>
      <p className="text-sm text-slate-500 mb-5">Every document event — pushes, accesses, shares, and revocations</p>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {[...Array(6)].map((_,i) => <div key={i} className="h-10 bg-slate-100 animate-pulse rounded"/>)}
          </div>
        ) : events.length === 0 ? (
          <div className="py-16 text-center text-slate-400">
            <div className="text-3xl mb-3">📋</div>
            <p className="font-medium text-slate-600">No activity yet</p>
            <p className="text-sm mt-1">Events appear here as documents are pushed and accessed.</p>
          </div>
        ) : events.map((e, i) => (
          <div key={i} className={`flex items-start gap-3 px-4 py-3.5 ${i < events.length - 1 ? 'border-b border-slate-100' : ''}`}>
            <div className={`mt-1 w-2.5 h-2.5 rounded-full shrink-0 ${dot(e.kind === 'push' ? 'PUSH' : e.access_type)}`} />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-800">{eventLabel(e)}</p>
              {e.employer_name && e.kind !== 'push' && (
                <p className="text-[11px] text-slate-400 font-mono mt-0.5">{e.employer_name}</p>
              )}
            </div>
            <span className="text-[11px] text-slate-400 shrink-0 font-mono">{fmtTs(e.ts)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
