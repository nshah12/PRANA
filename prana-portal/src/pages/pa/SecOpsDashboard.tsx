import { useQuery } from '@tanstack/react-query'
import { ShieldAlert, Activity, Lock, Globe } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export function SecOpsDashboard() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['pa-secops'],
    queryFn: () => api.get('/admin/secops').then(r => r.data),
    refetchInterval: 30_000,
  })

  if (isLoading) return (
    <div className="space-y-6 animate-pulse">
      <div className="h-6 w-44 bg-slate-200 rounded" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-slate-100 rounded-xl" />)}
      </div>
      <div className="h-64 bg-slate-100 rounded-xl" />
      <div className="h-40 bg-slate-100 rounded-xl" />
    </div>
  )
  if (isError) return (
    <div className="flex flex-col items-center justify-center py-20 text-slate-400">
      <p className="text-sm">Failed to load SecOps dashboard.</p>
      <button onClick={() => refetch()} className="mt-3 text-xs text-red-600 hover:underline">Retry</button>
    </div>
  )

  const stats = [
    { label: 'Active threats',    value: data?.active_threats ?? 0,   color: 'text-red-600',    icon: ShieldAlert },
    { label: 'Locked accounts',   value: data?.locked_accounts ?? 0,  color: 'text-amber-600',  icon: Lock },
    { label: 'Auth events (1h)',  value: data?.auth_events_1h ?? 0,   color: 'text-sky-600',    icon: Activity },
    { label: 'Foreign IPs (24h)', value: data?.foreign_ips_24h ?? 0,  color: 'text-purple-600', icon: Globe },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">SecOps Dashboard</h1>
        <span className="text-xs font-mono text-slate-400">Platform Admin · refreshes every 30s</span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <s.icon size={18} className={`${s.color} mb-2`} />
            <p className={`text-2xl font-bold font-mono ${s.color}`}>{s.value}</p>
            <p className="text-xs text-slate-500 mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Tenant posture table */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-medium text-slate-800">Tenant security posture</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs text-slate-400 uppercase tracking-wide">
                <th className="px-5 py-3 text-left font-medium">Tenant</th>
                <th className="px-5 py-3 text-center font-medium">Posture</th>
                <th className="px-5 py-3 text-right font-medium">Locked</th>
                <th className="px-5 py-3 text-right font-medium">Anomalies</th>
                <th className="px-5 py-3 text-right font-medium">Last threat</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {(data?.tenants ?? []).map((t: any) => (
                <tr key={t.tenant_id} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3 font-medium text-slate-700">{t.tenant_name}</td>
                  <td className="px-5 py-3 text-center">
                    <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full ${
                      t.posture === 'GREEN'  ? 'bg-emerald-50 text-emerald-700' :
                      t.posture === 'AMBER'  ? 'bg-amber-50 text-amber-700' :
                      'bg-red-50 text-red-700'
                    }`}>{t.posture}</span>
                  </td>
                  <td className="px-5 py-3 text-right font-mono text-slate-700">{t.locked_count ?? 0}</td>
                  <td className="px-5 py-3 text-right font-mono text-slate-700">{t.anomaly_count ?? 0}</td>
                  <td className="px-5 py-3 text-right text-xs text-slate-400 font-mono">
                    {t.last_threat_at ? fmtDateTime(t.last_threat_at) : 'None'}
                  </td>
                </tr>
              ))}
              {!data?.tenants?.length && (
                <tr>
                  <td colSpan={5} className="px-5 py-8 text-center text-sm text-slate-400">No tenant data.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Live alert feed */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
          <Activity size={14} className="text-red-500 animate-pulse" />
          <h2 className="font-medium text-slate-800">Live alert feed</h2>
        </div>
        <div className="divide-y divide-slate-50">
          {(data?.alerts ?? []).map((a: any, i: number) => (
            <div key={i} className="px-5 py-3 flex items-center gap-4">
              <ShieldAlert size={14} className={a.severity === 'HIGH' ? 'text-red-500' : 'text-amber-500'} />
              <span className="flex-1 text-sm text-slate-700">{a.description}</span>
              <span className="text-xs text-slate-400 font-mono">{a.tenant_name}</span>
              <span className="text-xs text-slate-400 font-mono whitespace-nowrap">{fmtDateTime(a.occurred_at)}</span>
            </div>
          ))}
          {!data?.alerts?.length && (
            <p className="px-5 py-8 text-sm text-slate-400 text-center">No active alerts.</p>
          )}
        </div>
      </div>
    </div>
  )
}
