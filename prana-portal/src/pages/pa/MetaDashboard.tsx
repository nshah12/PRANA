import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Building2, Users, HardDrive, AlertTriangle } from 'lucide-react'

export function MetaDashboard() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['pa-meta-dashboard'],
    queryFn: () => api.get('/admin/meta-dashboard').then(r => r.data),
    refetchInterval: 5 * 60 * 1000,   // 5 min per platform_config
  })

  if (isLoading) return (
    <div className="space-y-6 animate-pulse">
      <div className="h-6 w-44 bg-slate-200 rounded" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-slate-100 rounded-xl" />)}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="h-48 bg-slate-100 rounded-xl" />
        <div className="h-48 bg-slate-100 rounded-xl" />
      </div>
    </div>
  )
  if (isError) return (
    <div className="flex flex-col items-center justify-center py-20 text-slate-400">
      <p className="text-sm">Failed to load platform dashboard.</p>
      <button onClick={() => refetch()} className="mt-3 text-xs text-amber-600 hover:underline">Retry</button>
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Platform Dashboard</h1>
        <p className="text-xs text-amber-600 bg-amber-50 rounded-md px-2 py-1 mt-1 inline-block">
          Portal Admin — zero access to document rows or employee PII
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Active tenants',    value: data?.active_tenants ?? '—',    icon: <Building2 size={18}/>,   color: 'sky' },
          { label: 'Total employees',   value: data?.total_employees ?? '—',   icon: <Users size={18}/>,       color: 'emerald' },
          { label: 'Storage used',      value: data?.storage_used_label ?? '—',icon: <HardDrive size={18}/>,   color: 'violet' },
          { label: 'Open exceptions',   value: data?.open_exceptions ?? '—',   icon: <AlertTriangle size={18}/>,color: 'red' },
        ].map(card => (
          <div key={card.label} className={`stat-card stat-card-${card.color}`}>
            <div className="flex justify-between mb-3">
              <span className="text-slate-400">{card.icon}</span>
            </div>
            <p className="text-2xl font-bold font-mono text-slate-800">{card.value}</p>
            <p className="text-xs text-slate-500 mt-1">{card.label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-3">
          <h2 className="font-medium text-slate-800">Pipeline health</h2>
          {['QUEUED','ENCRYPTING','SCANNING','EXTRACTING','RESOLVING'].map(stage => {
            const counts = data?.pipeline_counts ?? {}
            const stageCount = counts[stage] ?? 0
            const maxCount = Math.max(1, ...Object.values(counts).map(Number))
            const pct = Math.round((stageCount / maxCount) * 100)
            return (
              <div key={stage} className="flex items-center gap-3">
                <span className="text-xs font-mono text-slate-500 w-28">{stage}</span>
                <div className="flex-1 bg-slate-100 rounded-full h-2">
                  <div className="bg-violet-500 h-2 rounded-full" style={{ width: `${pct}%` }} />
                </div>
                <span className="text-xs font-mono text-slate-400 w-8 text-right">{stageCount}</span>
              </div>
            )
          })}
        </div>

        <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
          <h2 className="font-medium text-slate-800 mb-3">Recent tenant activity</h2>
          <div className="space-y-2">
            {data?.recent_tenant_activity?.map((ev: any, i: number) => (
              <div key={i} className="flex items-center gap-3 text-sm">
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  ev.type === 'PROVISIONED' ? 'bg-emerald-500' :
                  ev.type === 'SUSPENDED'   ? 'bg-red-500' : 'bg-sky-500'
                }`}/>
                <span className="flex-1 text-slate-700 truncate">{ev.tenant_name}</span>
                <span className="text-xs text-slate-400 font-mono whitespace-nowrap">{ev.type}</span>
              </div>
            )) ?? <p className="text-sm text-slate-400">No recent activity.</p>}
          </div>
        </div>
      </div>
    </div>
  )
}
