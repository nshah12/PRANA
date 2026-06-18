import { useQuery } from '@tanstack/react-query'
import { Download, TrendingUp, TrendingDown } from 'lucide-react'
import { api } from '@/lib/api'

export function MonthlySummary() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['chro-monthly'],
    queryFn: () => api.get('/v1/chro/digest/monthly').then(r => r.data),
  })

  if (isLoading) return (
    <div className="space-y-6 max-w-2xl animate-pulse">
      <div className="h-6 w-44 bg-slate-200 rounded" />
      <div className="grid grid-cols-2 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-slate-100 rounded-xl" />)}
      </div>
      <div className="h-48 bg-slate-100 rounded-xl" />
    </div>
  )
  if (isError) return (
    <div className="flex flex-col items-center justify-center py-20 text-slate-400">
      <p className="text-sm">Failed to load monthly summary.</p>
      <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">Retry</button>
    </div>
  )

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Monthly Summary</h1>
        <button className="flex items-center gap-2 px-4 py-2 border border-slate-200
                           rounded-lg text-sm font-medium text-slate-600 hover:bg-canvas2">
          <Download size={14}/> Download PDF
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {[
          { label: 'Vault health', current: data?.vault_health_current, prev: data?.vault_health_prev, unit: '%' },
          { label: 'Docs pushed', current: data?.docs_pushed, prev: data?.docs_pushed_prev, unit: '' },
          { label: 'Active employees', current: data?.active_employees, prev: null, unit: '' },
          { label: 'Open exceptions', current: data?.open_exceptions, prev: null, unit: '' },
        ].map(card => {
          const delta = card.prev != null && card.current != null ? card.current - card.prev : null
          return (
            <div key={card.label} className="stat-card">
              <p className="text-2xl font-bold font-mono text-slate-800">
                {card.current ?? '—'}{card.unit}
              </p>
              <p className="text-xs text-slate-500 mt-1">{card.label}</p>
              {delta != null && (
                <p className={`text-xs mt-1 flex items-center gap-1 font-medium ${delta >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                  {delta >= 0 ? <TrendingUp size={11}/> : <TrendingDown size={11}/>}
                  {delta > 0 ? '+' : ''}{delta}{card.unit} vs last month
                </p>
              )}
            </div>
          )
        })}
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <h2 className="font-medium text-slate-800 mb-4">Statutory compliance</h2>
        <div className="space-y-2">
          {data?.compliance_items?.map((item: any, i: number) => (
            <div key={i} className="flex items-center gap-3 py-2 border-b border-slate-50 last:border-0">
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${item.compliant ? 'bg-emerald-500' : 'bg-red-500'}`}/>
              <p className="text-sm text-slate-700 flex-1">{item.obligation}</p>
              <span className={`badge ${item.compliant ? 'badge-emerald' : 'badge-red'}`}>
                {item.compliant ? 'Compliant' : 'Gap'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
