import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function CfoDashboard() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['cfo-dashboard'],
    queryFn: () => api.get('/cfo/dashboard').then(r => r.data),
  })

  if (isLoading) return (
    <div className="space-y-6 animate-pulse">
      <div className="h-6 w-36 bg-slate-200 rounded" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-slate-100 rounded-xl" />)}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-slate-100 rounded-xl" />)}
      </div>
    </div>
  )
  if (isError) return (
    <div className="flex flex-col items-center justify-center py-20 text-slate-400">
      <p className="text-sm">Failed to load dashboard.</p>
      <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">Retry</button>
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">CFO Dashboard</h1>
        <p className="text-xs text-indigo-600 bg-indigo-50 rounded-md px-2 py-1 mt-1 inline-block">
          Aggregated data only — no individual salary figures or document content
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Payroll spend (month)', value: data?.payroll_spend_label ?? '—', color: 'sky' },
          { label: 'Attrition cost QTD',   value: data?.attrition_cost_label ?? '—', color: 'amber' },
          { label: 'Compliance exposure',  value: data?.compliance_exposure_label ?? '—', color: 'red' },
          { label: 'Consent coverage',     value: data?.consent_coverage_pct != null ? `${data.consent_coverage_pct}%` : '—', color: 'emerald' },
        ].map(card => (
          <div key={card.label} className={`stat-card stat-card-${card.color}`}>
            <p className="text-2xl font-bold font-mono text-slate-800">{card.value}</p>
            <p className="text-xs text-slate-500 mt-1">{card.label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <QuickLinkCard title="Payroll Intelligence" href="/org/payroll"
                       desc="6-month trend, dept breakdown, band distribution" color="indigo" />
        <QuickLinkCard title="Anomaly Alerts" href="/org/anomalies"
                       desc="Active financial pattern flags requiring review" color="red"
                       badge={data?.active_anomalies} />
        <QuickLinkCard title="Attrition Cost" href="/org/attrition"
                       desc="Exit cost QTD/YTD, tenure distribution, replacement cost" color="amber" />
        <QuickLinkCard title="Benchmarking" href="/org/benchmarking"
                       desc="Market P25/P50/P75 vs org median by role category" color="sky" />
      </div>
    </div>
  )
}

function QuickLinkCard({ title, href, desc, color, badge }: {
  title: string; href: string; desc: string; color: string; badge?: number
}) {
  const colors: Record<string, string> = {
    indigo: 'border-indigo-200 hover:border-indigo-400',
    red:    'border-red-200 hover:border-red-400',
    amber:  'border-amber-200 hover:border-amber-400',
    sky:    'border-sky-200 hover:border-sky-400',
  }
  return (
    <a href={href} className={`block bg-white rounded-xl border p-5 shadow-sm transition-colors ${colors[color]}`}>
      <div className="flex items-start justify-between">
        <p className="font-medium text-slate-800">{title}</p>
        {badge ? <span className="badge badge-red">{badge}</span> : null}
      </div>
      <p className="text-xs text-slate-500 mt-1">{desc}</p>
    </a>
  )
}
