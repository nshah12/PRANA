import { useQuery } from '@tanstack/react-query'
import { TrendingDown, Users, Clock } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { api } from '@/lib/api'

export function AttritionCost() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['cfo-attrition'],
    queryFn: () => api.get('/v1/cfo/attrition').then(r => r.data),
  })

  if (isLoading) return (
    <div className="space-y-6 animate-pulse">
      <div className="h-6 w-40 bg-slate-200 rounded" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-slate-100 rounded-xl" />)}
      </div>
      <div className="h-56 bg-slate-100 rounded-xl" />
    </div>
  )
  if (isError) return (
    <div className="flex flex-col items-center justify-center py-20 text-slate-400">
      <p className="text-sm">Failed to load attrition data.</p>
      <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">Retry</button>
    </div>
  )

  const summary = [
    { label: 'Exits QTD', value: data?.exits_qtd ?? '—', icon: Users, color: 'text-red-600' },
    { label: 'Attrition rate', value: data?.attrition_rate_pct != null ? `${data.attrition_rate_pct}%` : '—', icon: TrendingDown, color: 'text-amber-600' },
    { label: 'Avg tenure at exit', value: data?.avg_tenure_months != null ? `${data.avg_tenure_months}m` : '—', icon: Clock, color: 'text-sky-600' },
    { label: 'Replacement cost (index)', value: data?.replacement_cost_label ?? '—', icon: TrendingDown, color: 'text-indigo-600' },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Attrition Cost</h1>
        <p className="text-xs text-indigo-600 bg-indigo-50 rounded-md px-2 py-1 mt-1 inline-block">
          Aggregated metrics only — no individual salary figures
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {summary.map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <s.icon size={18} className={`${s.color} mb-2`} />
            <p className="text-2xl font-bold font-mono text-slate-800">{s.value}</p>
            <p className="text-xs text-slate-500 mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <h2 className="font-medium text-slate-800 mb-4">Monthly exits (rolling 12m)</h2>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data?.monthly_exits ?? []}>
            <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94A3B8' }} />
            <YAxis tick={{ fontSize: 11, fill: '#94A3B8' }} />
            <Tooltip />
            <Bar dataKey="exits" fill="#F87171" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <h2 className="font-medium text-slate-800 mb-4">Exit reasons (category split)</h2>
        <div className="space-y-3">
          {(data?.exit_reasons ?? []).map((r: any) => (
            <div key={r.reason} className="flex items-center gap-3">
              <span className="w-36 text-sm text-slate-600 shrink-0">{r.reason}</span>
              <div className="flex-1 bg-slate-100 rounded-full h-2">
                <div className="bg-red-400 h-2 rounded-full" style={{ width: `${r.pct}%` }} />
              </div>
              <span className="text-xs font-mono text-slate-500 w-10 text-right">{r.pct}%</span>
            </div>
          ))}
          {!data?.exit_reasons?.length && (
            <p className="text-sm text-slate-400 text-center py-4">No exit data for this period.</p>
          )}
        </div>
      </div>
    </div>
  )
}
