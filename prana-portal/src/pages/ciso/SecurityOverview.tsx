import { useQuery } from '@tanstack/react-query'
import { Shield, AlertTriangle, Activity } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export function SecurityOverview() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['ciso-overview'],
    queryFn: () => api.get('/v1/ciso/overview').then(r => r.data),
    refetchInterval: 30_000,
  })

  if (isLoading) return (
    <div className="space-y-6 animate-pulse">
      <div className="h-6 w-44 bg-slate-200 rounded" />
      <div className="h-28 bg-slate-100 rounded-xl" />
      <div className="h-48 bg-slate-100 rounded-xl" />
      <div className="h-40 bg-slate-100 rounded-xl" />
    </div>
  )
  if (isError) return (
    <div className="flex flex-col items-center justify-center py-20 text-slate-400">
      <p className="text-sm">Failed to load security overview.</p>
      <button onClick={() => refetch()} className="mt-3 text-xs text-red-600 hover:underline">Retry</button>
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Security Overview</h1>
        <span className="text-xs font-mono text-slate-400">Live · refreshes every 30s</span>
      </div>

      {/* Posture card */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 flex items-center gap-6">
        <Shield size={40} className={data?.posture === 'GREEN' ? 'text-emerald-500' : 'text-red-500'} />
        <div>
          <p className="text-sm font-medium text-slate-500">Security posture</p>
          <p className={`text-2xl font-bold ${data?.posture === 'GREEN' ? 'text-emerald-600' : 'text-red-600'}`}>
            {data?.posture ?? '—'}
          </p>
        </div>
        <div className="ml-auto grid grid-cols-3 gap-4">
          {[
            { label: 'Threats (24h)', value: data?.threats_24h ?? 0, color: 'text-red-600' },
            { label: 'Anomalies', value: data?.anomalies_open ?? 0, color: 'text-amber-600' },
            { label: 'Auth events', value: data?.auth_events_24h ?? 0, color: 'text-sky-600' },
          ].map(stat => (
            <div key={stat.label} className="text-center">
              <p className={`text-xl font-bold font-mono ${stat.color}`}>{stat.value}</p>
              <p className="text-xs text-slate-400 mt-0.5">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* 7-day event timeline */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <h2 className="font-medium text-slate-800 mb-4">7-day security events</h2>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data?.event_timeline ?? []}>
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94A3B8' }} />
            <YAxis tick={{ fontSize: 11, fill: '#94A3B8' }} />
            <Tooltip />
            <Line type="monotone" dataKey="events" stroke="#EF4444" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Live threat feed */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
          <Activity size={14} className="text-red-500 animate-pulse" />
          <h2 className="font-medium text-slate-800">Live threat feed</h2>
        </div>
        <div className="divide-y divide-slate-50">
          {data?.threats?.length === 0 && (
            <p className="px-5 py-8 text-sm text-slate-400 text-center">No active threats.</p>
          )}
          {data?.threats?.map((t: any, i: number) => (
            <div key={i} className="px-5 py-3 flex items-center gap-4">
              <AlertTriangle size={14} className={t.severity === 'HIGH' ? 'text-red-500' : 'text-amber-500'} />
              <span className="flex-1 text-sm text-slate-700">{t.description}</span>
              <span className="text-xs text-slate-400 font-mono whitespace-nowrap">{fmtDateTime(t.detected_at)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
